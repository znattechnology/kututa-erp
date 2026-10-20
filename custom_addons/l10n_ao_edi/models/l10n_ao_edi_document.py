import json
import logging
from datetime import timedelta

from odoo import api, fields, models, modules
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

AGT_BATCH_SIZE = 30  # máximo de documentos por chamada a registarFactura
POLL_DELAYS = (1, 2, 5, 10, 30, 60)  # minutos entre consultas de estado (o último repete-se)
MAX_POLLS = 200  # cerca de uma semana de consultas: depois, os documentos voltam à fila de envio
# E09: o documento já consta do repositório da AGT (envio repetido, p. ex. depois de um timeout).
ALREADY_REGISTERED_ERRORS = ('E09',)
# Respostas definitivas do obterEstado (pedido inexistente ou mal formado): não adianta voltar a consultar.
DEFINITIVE_POLL_STATUSES = (400, 404, 422)


class L10nAoEdiDocument(models.Model):
    """Comunicações com a AGT.

    O registo de documentos (registarFactura) é assíncrono: a AGT devolve um requestID e valida depois;
    a validação consulta-se por polling (obterEstado). Os restantes serviços (séries, validação de documentos
    de fornecedores) ficam também aqui registados: é o registo de auditoria das comunicações exigido pelo
    Anexo III do DE n.º 683/25.
    """

    _name = 'l10n_ao_edi.document'
    _description = 'Comunicação AGT'
    _order = 'id desc'
    _rec_name = 'request_id'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True, index=True)
    service = fields.Selection(
        selection=[
            ('registarFactura', 'Registo de documentos'),
            ('solicitarSerie', 'Pedido de série'),
            ('listarSeries', 'Listagem de séries'),
            ('validarDocumento', 'Validação de documento de fornecedor'),
        ],
        string='Serviço',
        default='registarFactura',
        required=True,
        readonly=True,
    )
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
        string='Estado',
        default='sent',
        required=True,
        readonly=True,
    )
    result_code = fields.Char(string='resultCode', readonly=True)
    payload = fields.Text(string='Pedido (JSON)', readonly=True)
    response = fields.Text(string='Última resposta (JSON)', readonly=True)
    error_message = fields.Text(string='Erros', readonly=True)
    poll_count = fields.Integer(string='Consultas', readonly=True)
    document_numbers = fields.Char(string='N.º dos documentos', compute='_compute_document_numbers')
    next_poll = fields.Datetime(string='Próxima consulta', readonly=True)

    def _compute_document_numbers(self):
        for document in self:
            document.document_numbers = ', '.join(
                filter(None, (r._l10n_ao_edi_number() for r in document.sudo()._queued_records()))
            )

    # -------------------------------------------------------------------------
    # Registo de auditoria dos outros serviços
    # -------------------------------------------------------------------------

    @api.model
    def _log_call(self, company, service, payload, status, body, *, ok, records=None):
        """Regista uma chamada síncrona à AGT (séries, validação de documentos de fornecedores)."""
        values = {
            'company_id': company.id,
            'service': service,
            'submission_uuid': payload.get('submissionUUID'),
            'payload': json.dumps(payload, ensure_ascii=False, indent=1),
            'response': json.dumps(body or {}, ensure_ascii=False, indent=1),
            'result_code': str((body or {}).get('resultCode', status or '')),
            'state': 'done' if ok else 'error',
            'error_message': False if ok else self._format_errors((body or {}).get('errorList') or []) or str(status),
        }
        if records and records._name in self._queue_fields():
            values[self._queue_fields()[records._name]] = [fields.Command.set(records.ids)]
        if ok or self.env.context.get('l10n_ao_edi_no_commit') or modules.module.current_test:
            return self.sudo().create(values)
        # Chamada recusada: o erro mostrado ao utilizador desfaz a transacção, mas o registo de auditoria fica.
        with self.env.registry.cursor() as cr:
            return self.with_env(self.env(cr=cr, su=True)).create(values).id

    # -------------------------------------------------------------------------
    # Envio
    # -------------------------------------------------------------------------

    @api.model
    def _queue_fields(self):
        """Modelos com documentos AGT na fila de envio, pela ordem de envio, e o campo do pedido que os liga.

        Cada modelo implementa ``l10n_ao_edi_state``, ``company_id``, ``_l10n_ao_edi_number()``,
        ``_l10n_ao_edi_ready_to_send()`` e ``_l10n_ao_edi_payload_values()``.
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
    def _lock_for_sending(self, records):
        """Bloqueia as linhas a enviar; as que outro processo já está a enviar (cron e botão em simultâneo)
        ficam de fora, para não haver dois registarFactura do mesmo documento."""
        locked = []
        by_model = {}
        for record in records:
            by_model.setdefault(record._name, []).append(record)
        for model_records in by_model.values():
            table = model_records[0]._table
            self.env.cr.execute(
                SQL(
                    'SELECT id FROM %s WHERE id IN %s AND l10n_ao_edi_state = %s FOR UPDATE SKIP LOCKED',
                    SQL.identifier(table),
                    tuple(r.id for r in model_records),
                    'to_send',
                )
            )
            ids = {row[0] for row in self.env.cr.fetchall()}
            locked += [r for r in model_records if r.id in ids]
        return locked

    @api.model
    def _send_records(self, *recordsets):
        """Envia documentos pendentes (facturas, recibos, talões...), por empresa e em lotes de 30.

        Não envia nada das empresas em contingência, nem documentos cujos documentos de origem
        ainda não foram aceites na recepção da AGT (seriam rejeitados por referência desconhecida).
        Um lote com erro (configuração, rede) não impede o envio dos outros.
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
        if not records:
            return
        records = self._lock_for_sending(records)
        companies = self.env['res.company'].union(r.company_id for r in records)
        batches = []
        for company in companies.filtered(lambda c: not c.l10n_ao_edi_contingency):
            company_records = [r for r in records if r.company_id == company]
            batches += [
                (company, company_records[start : start + AGT_BATCH_SIZE])
                for start in range(0, len(company_records), AGT_BATCH_SIZE)
            ]
        for index, (company, batch) in enumerate(batches):
            try:
                with self.env.cr.savepoint():
                    self._send_batch(company, batch)
            except Exception as error:  # noqa: BLE001 - um lote com erro não pode bloquear a fila
                _logger.exception('AGT: erro no envio de um lote da empresa %s', company.name)
                for record in batch:
                    record.l10n_ao_edi_error = self.env._('Erro no envio: %s', error)
            if not self.env.context.get('l10n_ao_edi_no_commit'):
                # Cada chamada à AGT fica gravada antes da seguinte (o efeito externo já aconteceu).
                remaining = sum(len(b) for _c, b in batches[index + 1 :])
                if not self.env['ir.cron']._commit_progress(processed=len(batch), remaining=remaining):
                    break  # tempo do cron esgotado: o resto segue no próximo ciclo

    @api.model
    def _split_records(self, records):
        """{campo do pedido: registos} para ligar os documentos de um lote ao pedido."""
        return {
            field: self.env[model].union(r for r in records if r._name == model)
            for model, field in self._queue_fields().items()
        }

    def _queued_records(self):
        self.ensure_one()
        return [record for field in self._queue_fields().values() for record in self[field]]

    @api.model
    def _errors_by_document(self, errors):
        by_document = {}
        for error in errors:
            if isinstance(error, dict) and error.get('documentNo'):
                by_document.setdefault(error['documentNo'], []).append(error)
        return by_document

    @api.model
    def _is_already_registered(self, errors, code_key='idError'):
        codes = {(error.get(code_key) or error.get('idError') or error.get('errorCode')) for error in errors}
        return bool(errors) and codes <= set(ALREADY_REGISTERED_ERRORS)

    @api.model
    def _send_batch(self, company, records):
        company._l10n_ao_edi_check_configuration()
        linked = self._split_records(records)
        documents = [record._l10n_ao_edi_payload_values() for record in records]
        payload = {
            **company._l10n_ao_edi_request_envelope(),
            'numberOfEntries': len(documents),
            'documents': documents,
        }
        status, body = company._l10n_ao_edi_call('registarFactura', payload)
        body = body if isinstance(body, dict) else {}
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
        by_document = self._errors_by_document(errors)
        global_errors = [e for e in errors if not (isinstance(e, dict) and e.get('documentNo'))]
        if status == 200 and request_id and not global_errors:
            # Recebido. Os documentos que a AGT já tinha (E09, envio repetido) contam como recebidos;
            # os que têm outros erros de estrutura ficam rejeitados.
            for record in records:
                record_errors = by_document.get(record._l10n_ao_edi_number())
                if record_errors and not self._is_already_registered(record_errors):
                    record.write(
                        {'l10n_ao_edi_state': 'invalid', 'l10n_ao_edi_error': self._format_errors(record_errors)}
                    )
                else:
                    record.write({'l10n_ao_edi_state': 'sent', 'l10n_ao_edi_error': False})
            document.next_poll = fields.Datetime.now() + timedelta(minutes=POLL_DELAYS[0])
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_poll')._trigger(document.next_poll)
            return document

        # Pedido recusado na recepção: os documentos identificados com erros ficam inválidos (excepto os que a AGT
        # já tinha), os restantes voltam a ser enviados no próximo ciclo.
        message = self._format_errors(errors) or self.env._('Resposta HTTP %s sem requestID.', status)
        document.write({'state': 'error', 'error_message': message})
        for record in records:
            record_errors = by_document.get(record._l10n_ao_edi_number())
            if record_errors and self._is_already_registered(record_errors):
                record.write({'l10n_ao_edi_state': 'sent', 'l10n_ao_edi_error': False})
            elif record_errors:
                record.write({'l10n_ao_edi_state': 'invalid', 'l10n_ao_edi_error': self._format_errors(record_errors)})
            else:
                record.l10n_ao_edi_error = message
        return document

    # -------------------------------------------------------------------------
    # Consulta do estado
    # -------------------------------------------------------------------------

    @api.model
    def _cron_poll(self):
        documents = self.sudo().search(
            [('service', '=', 'registarFactura'), ('state', '=', 'sent'), ('next_poll', '<=', fields.Datetime.now())]
        )
        for document in documents:
            try:
                with self.env.cr.savepoint():
                    document._poll()
            except Exception:  # noqa: BLE001 - uma resposta inesperada não pode bloquear as outras consultas
                _logger.exception('AGT: erro na consulta do pedido %s', document.request_id)
                document.next_poll = fields.Datetime.now() + timedelta(minutes=POLL_DELAYS[-1])
            if not self.env.context.get('l10n_ao_edi_no_commit'):
                if not self.env['ir.cron']._commit_progress(processed=1):
                    break

    def _requeue(self, message):
        """O pedido termina sem resultado: os documentos ainda por validar voltam à fila de envio
        (um reenvio de um documento que a AGT afinal tem é reconhecido pelo erro E09)."""
        self.write({'state': 'error', 'error_message': message})
        for field in self._queue_fields().values():
            self[field].filtered(lambda r: r.l10n_ao_edi_state == 'sent').write({'l10n_ao_edi_state': 'to_send'})

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
        body = body if isinstance(body, dict) else {}
        self.write({'response': json.dumps(body, ensure_ascii=False, indent=1), 'poll_count': self.poll_count + 1})
        result_code = str(body.get('resultCode', ''))
        if status in DEFINITIVE_POLL_STATUSES:
            self._requeue(self._format_errors(body.get('errorList') or []) or self.env._('HTTP %s', status))
            return
        if status != 200 or result_code in ('7', '8', ''):
            if self.poll_count >= MAX_POLLS:
                self._requeue(self.env._('Sem resposta da AGT ao fim de %s consultas.', self.poll_count))
                return
            # Ainda em processamento (8), pedido prematuro (7, E97) ou indisponibilidade: volta a consultar mais tarde.
            delay = POLL_DELAYS[min(self.poll_count, len(POLL_DELAYS) - 1)]
            self.next_poll = fields.Datetime.now() + timedelta(minutes=delay)
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_poll')._trigger(self.next_poll)
            return
        if result_code == '9':
            # Processamento cancelado pela AGT: os documentos voltam à fila.
            self.result_code = result_code
            self._requeue(self.env._('Processamento cancelado pela AGT.'))
            return

        statuses = {item.get('documentNo'): item for item in body.get('documentStatusList') or []}
        missing = []
        for record in self._queued_records():
            if record.l10n_ao_edi_state != 'sent':
                continue
            item = statuses.get(record._l10n_ao_edi_number())
            if not item:
                missing.append(record)
                continue
            item_errors = item.get('errorList') or []
            if item.get('documentStatus') == 'V' or (
                item.get('successRequestID') and self._is_already_registered(item_errors, code_key='errorCode')
            ):
                record.write({'l10n_ao_edi_state': 'valid', 'l10n_ao_edi_error': False})
            else:
                record.write(
                    {
                        'l10n_ao_edi_state': 'invalid',
                        'l10n_ao_edi_error': self._format_errors(item_errors, code_key='errorCode'),
                    }
                )
        for record in missing:
            # A AGT não devolveu estado para o documento: volta à fila (não pode ficar «enviado» para sempre).
            record.write(
                {
                    'l10n_ao_edi_state': 'to_send',
                    'l10n_ao_edi_error': self.env._('Sem estado no pedido %s: será reenviado.', self.request_id),
                }
            )
        self.write(
            {
                'state': 'done',
                'result_code': result_code,
                'error_message': self._format_errors(body.get('requestErrorList') or []) or False,
            }
        )

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
