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
    def _queue_fields(self):
        """Modelos com documentos AGT na fila de envio, pela ordem de envio, e o campo do pedido que os liga.

        Cada modelo implementa ``l10n_ao_edi_state``, ``company_id``, ``_l10n_ao_edi_number()``,
        ``_l10n_ao_edi_ready_to_send()`` e ``_l10n_ao_edi_document_values()``.
        """
        return {'account.move': 'move_ids', 'account.payment': 'payment_ids'}

    @api.model
    def _cron_send(self):
        recordsets = []
        for model in self._queue_fields():
            # A fila inclui documentos de outras aplicações (ex.: talões do POS) a que o utilizador pode não ter
            # acesso; quando o tem, os registos mantêm o utilizador (autor das alterações de estado no histórico).
            records = self.env[model].sudo().search([('l10n_ao_edi_state', '=', 'to_send')], order='company_id, id')
            recordsets.append(records.sudo(False) if self.env[model].has_access('write') else records)
        self._send_records(*recordsets)

    @api.model
    def _send_moves(self, moves):
        self._send_records(moves)

    @api.model
    def _send_records(self, *recordsets):
        """Envia documentos pendentes (facturas, recibos, talões...), por empresa e em lotes de 30.

        Não envia nada das empresas em contingência, nem documentos cujos documentos de origem
        ainda não foram aceites na recepção da AGT (seriam rejeitados por referência desconhecida).
        """
        # Os pedidos são registos técnicos de auditoria: criados com privilégios de sistema.
        self = self.sudo()  # noqa: PLW0642
        # Os documentos mantêm o utilizador original (autor das alterações de estado no histórico).
        order = list(self._queue_fields())
        records = sorted(
            (
                record
                for recordset in recordsets
                for record in recordset
                if record.l10n_ao_edi_state == 'to_send' and record._l10n_ao_edi_ready_to_send()
            ),
            key=lambda r: (order.index(r._name), r.id),
        )
        companies = self.env['res.company'].union(*(r.company_id for r in records))
        for company in companies.filtered(lambda c: not c.l10n_ao_edi_contingency):
            company_records = [r for r in records if r.company_id == company]
            for start in range(0, len(company_records), AGT_BATCH_SIZE):
                batch = company_records[start : start + AGT_BATCH_SIZE]
                self._send_batch(company, batch)
                if not self.env.context.get('l10n_ao_edi_no_commit'):
                    # Cada chamada à AGT fica gravada antes da seguinte (o efeito externo já aconteceu).
                    self.env['ir.cron']._commit_progress(processed=len(batch))

    @api.model
    def _split_records(self, records):
        """{campo do pedido: registos} para ligar os documentos de um lote ao pedido."""
        return {
            field: self.env[model].union(*[r for r in records if r._name == model])
            for model, field in self._queue_fields().items()
        }

    def _queued_records(self):
        self.ensure_one()
        return [record for field in self._queue_fields().values() for record in self[field]]

    @api.model
    def _send_batch(self, company, records):
        company._l10n_ao_edi_check_configuration()
        linked = self._split_records(records)
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
                **{field: [fields.Command.set(linked_records.ids)] for field, linked_records in linked.items()},
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
            for field in self._queue_fields().values():
                self[field].write({'l10n_ao_edi_state': 'to_send'})
            return

        statuses = {item.get('documentNo'): item for item in body.get('documentStatusList') or []}
        for record in self._queued_records():
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
