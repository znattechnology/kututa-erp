import json
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

AGT_BATCH_SIZE = 30  # máximo de documentos por chamada a registarFactura
POLL_DELAYS = (1, 2, 5, 10, 30, 60)  # minutos entre consultas de estado (o último repete-se)


class L10nAoEdiDocument(models.Model):
    """Pedido de registo de documentos na AGT (registarFactura) e respectiva validação (obterEstado).

    O modelo é assíncrono: a AGT devolve um requestID e valida depois; a validação consulta-se por polling.
    Fica também como registo de auditoria das comunicações (Anexo III do DE n.º 683/25).
    """

    _name = 'l10n_ao_edi.document'
    _description = 'Pedido AGT'
    _order = 'id desc'
    _rec_name = 'request_id'

    company_id = fields.Many2one('res.company', required=True, index=True)
    move_ids = fields.Many2many(
        'account.move', 'l10n_ao_edi_document_move_rel', 'document_id', 'move_id', string='Documentos', readonly=True
    )
    payment_ids = fields.Many2many(
        'account.payment',
        'l10n_ao_edi_document_payment_rel',
        'document_id',
        'payment_id',
        string='Recibos',
        readonly=True,
    )
    request_id = fields.Char(string='requestID', readonly=True, index=True)
    submission_uuid = fields.Char(string='submissionUUID', readonly=True)
    state = fields.Selection(
        selection=[
            ('sent', 'Enviado (a aguardar validação)'),
            ('done', 'Processado'),
            ('error', 'Erro'),
        ],
        default='sent',
        required=True,
        readonly=True,
    )
    result_code = fields.Char(string='resultCode', readonly=True)
    payload = fields.Text(string='Pedido (JSON)', readonly=True)
    response = fields.Text(string='Última resposta (JSON)', readonly=True)
    error_message = fields.Text(string='Erros', readonly=True)
    poll_count = fields.Integer(readonly=True)
    next_poll = fields.Datetime(string='Próxima consulta', readonly=True)

    # -------------------------------------------------------------------------
    # Envio
    # -------------------------------------------------------------------------

    @api.model
    def _cron_send(self):
        moves = self.env['account.move'].search(
            [('l10n_ao_edi_state', '=', 'to_send'), ('state', '=', 'posted')], order='company_id, id'
        )
        payments = self.env['account.payment'].search([('l10n_ao_edi_state', '=', 'to_send')], order='company_id, id')
        self._send_records(moves, payments)

    @api.model
    def _send_moves(self, moves):
        self._send_records(moves, self.env['account.payment'])

    @api.model
    def _send_records(self, moves, payments):
        """Envia documentos pendentes (facturas e recibos), por empresa e em lotes de 30.

        Não envia nada das empresas em contingência, nem recibos cujos documentos de origem
        ainda não foram aceites na recepção da AGT (seriam rejeitados por referência desconhecida).
        """
        # Os pedidos são registos técnicos de auditoria: criados com privilégios de sistema.
        self = self.sudo()  # noqa: PLW0642
        # Os documentos mantêm o utilizador original (autor das alterações de estado no histórico).
        moves = moves.filtered(lambda m: m.l10n_ao_edi_state == 'to_send').sorted('id')
        payments = payments.filtered(lambda p: p.l10n_ao_edi_state == 'to_send' and p._l10n_ao_edi_sources_sent())
        companies = (moves.company_id | payments.company_id).filtered(lambda c: not c.l10n_ao_edi_contingency)
        for company in companies:
            records = list(moves.filtered(lambda m, c=company: m.company_id == c)) + list(
                payments.filtered(lambda p, c=company: p.company_id == c).sorted('id')
            )
            for start in range(0, len(records), AGT_BATCH_SIZE):
                batch = records[start : start + AGT_BATCH_SIZE]
                self._send_batch(company, batch)
                if not self.env.context.get('l10n_ao_edi_no_commit'):
                    # Cada chamada à AGT fica gravada antes da seguinte (o efeito externo já aconteceu).
                    self.env['ir.cron']._commit_progress(processed=len(batch))

    @api.model
    def _split_records(self, records):
        moves = self.env['account.move'].union(*[r for r in records if r._name == 'account.move'])
        payments = self.env['account.payment'].union(*[r for r in records if r._name == 'account.payment'])
        return moves, payments

    @api.model
    def _send_batch(self, company, records):
        company._l10n_ao_edi_check_configuration()
        moves, payments = self._split_records(records)
        documents = [record._l10n_ao_edi_document_values() for record in records]
        payload = {
            **company._l10n_ao_edi_request_envelope(),
            'numberOfEntries': len(documents),
            'documents': documents,
        }
        status, body = company._l10n_ao_edi_call('registarFactura', payload)
        body = body or {}
        request_id = body.get('requestID')
        errors = body.get('errorList') or []
        document = self.create(
            {
                'company_id': company.id,
                'move_ids': [fields.Command.set(moves.ids)],
                'payment_ids': [fields.Command.set(payments.ids)],
                'request_id': request_id,
                'submission_uuid': payload['submissionUUID'],
                'payload': json.dumps(payload, ensure_ascii=False, indent=1),
                'response': json.dumps(body, ensure_ascii=False, indent=1),
            }
        )
        if status == 200 and request_id and not errors:
            for record in records:
                record.write({'l10n_ao_edi_state': 'sent', 'l10n_ao_edi_error': False})
            document.next_poll = fields.Datetime.now() + timedelta(minutes=POLL_DELAYS[0])
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_poll')._trigger(document.next_poll)
            return document

        # Pedido recusado na recepção (erro de estrutura): os documentos identificados ficam inválidos,
        # os restantes voltam a ser enviados no próximo ciclo.
        message = self._format_errors(errors) or self.env._('Resposta HTTP %s sem requestID.', status)
        document.write({'state': 'error', 'error_message': message})
        by_document = {}
        for error in errors:
            if isinstance(error, dict) and error.get('documentNo'):
                by_document.setdefault(error['documentNo'], []).append(error)
        for record in records:
            number = record._l10n_ao_edi_number()
            if number in by_document:
                record.write(
                    {'l10n_ao_edi_state': 'invalid', 'l10n_ao_edi_error': self._format_errors(by_document[number])}
                )
            else:
                record.l10n_ao_edi_error = message
        return document

    # -------------------------------------------------------------------------
    # Consulta do estado
    # -------------------------------------------------------------------------

    @api.model
    def _cron_poll(self):
        documents = self.sudo().search([('state', '=', 'sent'), ('next_poll', '<=', fields.Datetime.now())])
        for document in documents:
            document._poll()
            if not self.env.context.get('l10n_ao_edi_no_commit'):
                self.env['ir.cron']._commit_progress(processed=1)

    def _poll(self):
        self.ensure_one()
        company = self.company_id
        signed = {
            'taxRegistrationNumber': company.partner_id._l10n_ao_normalize_nif(company.vat),
            'requestID': self.request_id,
        }
        payload = {
            **company._l10n_ao_edi_request_envelope(),
            'jwsSignature': company._l10n_ao_edi_sign(signed),
            'requestID': self.request_id,
        }
        status, body = company._l10n_ao_edi_call('obterEstado', payload)
        body = body or {}
        self.write({'response': json.dumps(body, ensure_ascii=False, indent=1), 'poll_count': self.poll_count + 1})
        result_code = str(body.get('resultCode', ''))
        if status != 200 or result_code in ('7', '8', ''):
            # Ainda em processamento (8), pedido prematuro (7, E97) ou indisponibilidade: volta a consultar mais tarde.
            delay = POLL_DELAYS[min(self.poll_count, len(POLL_DELAYS) - 1)]
            self.next_poll = fields.Datetime.now() + timedelta(minutes=delay)
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_poll')._trigger(self.next_poll)
            return
        if result_code == '9':
            # Processamento cancelado pela AGT: os documentos voltam à fila.
            self.write(
                {
                    'state': 'error',
                    'result_code': result_code,
                    'error_message': self.env._('Processamento cancelado pela AGT.'),
                }
            )
            self.move_ids.write({'l10n_ao_edi_state': 'to_send'})
            self.payment_ids.write({'l10n_ao_edi_state': 'to_send'})
            return

        statuses = {item.get('documentNo'): item for item in body.get('documentStatusList') or []}
        for record in list(self.move_ids) + list(self.payment_ids):
            item = statuses.get(record._l10n_ao_edi_number())
            if not item:
                continue
            if item.get('documentStatus') == 'V':
                record.write({'l10n_ao_edi_state': 'valid', 'l10n_ao_edi_error': False})
            else:
                record.write(
                    {
                        'l10n_ao_edi_state': 'invalid',
                        'l10n_ao_edi_error': self._format_errors(item.get('errorList') or [], code_key='errorCode'),
                    }
                )
        self.write({'state': 'done', 'result_code': result_code})

    @api.model
    def _format_errors(self, errors, code_key='idError'):
        lines = []
        for error in errors:
            if isinstance(error, dict):
                code = error.get(code_key) or error.get('idError') or error.get('errorCode') or ''
                description = error.get('descriptionError') or error.get('errorDescription') or ''
                lines.append(f'{code} {description}'.strip())
            elif error:
                lines.append(str(error))
        return '\n'.join(lines)
