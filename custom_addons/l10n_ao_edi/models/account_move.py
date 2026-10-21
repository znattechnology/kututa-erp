import json
from urllib.parse import quote

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL, float_round

from .l10n_ao_edi_series import AGT_DOCUMENT_TYPES
from .res_partner import FINAL_CONSUMER_NIF

AGT_QR_URL = 'https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe'
EDI_LOCKED_STATES = ('to_send', 'sent', 'valid')
# Tipos AGT permitidos em cada tipo de movimento do Odoo.
DOCUMENT_TYPES_BY_MOVE_TYPE = {'out_invoice': ('FT', 'FR', 'FA', 'ND'), 'out_refund': ('NC',)}
# Campos que definem o documento comunicado: não mudam depois da emissão (art. 8.º do DP n.º 71/25).
LOCKED_FIELDS = (
    'name',
    'l10n_ao_document_type',
    'l10n_ao_edi_series_id',
    'partner_id',
    'commercial_partner_id',
    'invoice_date',
    'currency_id',
    'l10n_ao_edi_reason',
    'move_type',
)


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ao_edi_required = fields.Boolean(compute='_compute_l10n_ao_edi_required')
    l10n_ao_document_type = fields.Selection(
        AGT_DOCUMENT_TYPES,
        string='Tipo de documento (AGT)',
        compute='_compute_l10n_ao_document_type',
        store=True,
        readonly=False,
        copy=False,
    )
    l10n_ao_edi_series_id = fields.Many2one('l10n_ao_edi.series', string='Série AGT', readonly=True, copy=False)
    l10n_ao_edi_state = fields.Selection(
        selection=[
            ('to_send', 'A enviar à AGT'),
            ('sent', 'Enviado (a aguardar validação)'),
            ('valid', 'Válido na AGT'),
            ('invalid', 'Rejeitado pela AGT'),
        ],
        string='Estado AGT',
        readonly=True,
        copy=False,
        tracking=True,
    )
    l10n_ao_edi_error = fields.Text(string='Erros AGT', readonly=True, copy=False)
    l10n_ao_edi_system_entry_date = fields.Datetime(string='Data de registo (AGT)', readonly=True, copy=False)
    l10n_ao_edi_rejected_payloads = fields.Text(
        string='Documentos rejeitados (JSON)',
        readonly=True,
        copy=False,
        help='Documentos AGT anteriores deste registo, rejeitados e substituídos: ficam no SAF-T como anulados.',
    )
    l10n_ao_edi_rejected_document_no = fields.Char(
        string='Documento rejeitado corrigido',
        readonly=True,
        copy=False,
        help='Número do documento rejeitado pela AGT que este documento corrige (documentStatus «C»).',
    )
    l10n_ao_edi_reason = fields.Char(
        string='Motivo (AGT)',
        copy=False,
        help='Motivo da nota de crédito ou de débito comunicado à AGT (anulação ou rectificação, até 60 caracteres).',
    )
    l10n_ao_edi_document_ids = fields.Many2many(
        'l10n_ao_edi.document',
        'l10n_ao_edi_document_move_rel',
        'move_id',
        'document_id',
        string='Pedidos AGT',
        readonly=True,
        copy=False,
    )
    l10n_ao_edi_qr_url = fields.Char(compute='_compute_l10n_ao_edi_qr_url')
    l10n_ao_edi_contingency = fields.Boolean(
        string='Emitido em contingência',
        readonly=True,
        copy=False,
        help='Emitido numa série de contingência (art. 18.º).',
    )
    l10n_ao_edi_payload = fields.Text(
        string='Documento AGT (JSON)',
        readonly=True,
        copy=False,
        help='Dados do documento tal como emitido; é isto que é enviado à AGT, mesmo que o cliente ou os '
        'artigos mudem depois.',
    )
    l10n_ao_edi_print_count = fields.Integer(
        string='Impressões do documento AGT',
        readonly=True,
        copy=False,
        help='Cada PDF gerado conta como impressão: o primeiro é o «Original», os seguintes levam «2.ª via».',
    )
    # Facturas recebidas (fornecedores): confirmação/rejeição na AGT (serviço validarDocumento).
    l10n_ao_edi_vendor_document_no = fields.Char(
        string='N.º AGT do documento do fornecedor',
        copy=False,
        help='Número do documento electrónico emitido pelo fornecedor (ex.: «FT FT26S1/123»).',
    )
    l10n_ao_edi_vendor_state = fields.Selection(
        selection=[('confirmed', 'Confirmado na AGT'), ('rejected', 'Rejeitado na AGT')],
        string='Validação AGT (fornecedor)',
        readonly=True,
        copy=False,
        tracking=True,
    )

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------

    @api.depends('company_id.l10n_ao_edi_enabled', 'move_type', 'journal_id.type')
    def _compute_l10n_ao_edi_required(self):
        for move in self:
            move.l10n_ao_edi_required = (
                move.company_id.l10n_ao_edi_enabled
                and move.move_type in ('out_invoice', 'out_refund')
                and move.journal_id.type == 'sale'
                and not move._l10n_ao_edi_is_internal_move()
            )

    def _l10n_ao_edi_is_internal_move(self):
        """Movimentos de vendas que não são documentos de facturação (ex.: fecho de sessão do POS, cujas vendas
        já foram comunicadas nos talões). Ponto de extensão para outros módulos."""
        return False

    @api.constrains('l10n_ao_document_type', 'move_type', 'debit_origin_id')
    def _check_l10n_ao_document_type(self):
        for move in self.filtered('l10n_ao_document_type'):
            allowed = DOCUMENT_TYPES_BY_MOVE_TYPE.get(move.move_type, ())
            if move.l10n_ao_document_type not in allowed or (move.l10n_ao_document_type == 'ND') != bool(
                move.debit_origin_id and move.move_type == 'out_invoice'
            ):
                raise ValidationError(
                    self.env._(
                        'O tipo de documento AGT %(type)s não é válido para este documento. '
                        'Facturas: FT, FR ou FA; notas de débito: ND; notas de crédito: NC.',
                        type=move.l10n_ao_document_type,
                    )
                )

    @api.depends('move_type', 'debit_origin_id')
    def _compute_l10n_ao_document_type(self):
        for move in self:
            if move.move_type == 'out_refund':
                move.l10n_ao_document_type = 'NC'
            elif move.move_type == 'out_invoice':
                if move.debit_origin_id:
                    move.l10n_ao_document_type = 'ND'
                elif move.l10n_ao_document_type not in ('FT', 'FR', 'FA'):
                    move.l10n_ao_document_type = 'FT'
            else:
                move.l10n_ao_document_type = False

    @api.depends('name', 'company_id.vat', 'l10n_ao_edi_state')
    def _compute_l10n_ao_edi_qr_url(self):
        for move in self:
            if move.l10n_ao_edi_series_id and move.name and move.name != '/':
                emitter = move.company_id.partner_id._l10n_ao_normalize_nif(move.company_id.vat)
                move.l10n_ao_edi_qr_url = f'{AGT_QR_URL}?emissor={emitter}&document={quote(move.name, safe="/")}'
            else:
                move.l10n_ao_edi_qr_url = False

    def _l10n_ao_edi_copy_label(self):
        """Menção da impressão em curso (o contador já inclui a impressão que está a ser gerada)."""
        self.ensure_one()
        return 'Original' if self.l10n_ao_edi_print_count <= 1 else '2.ª via'

    def _l10n_ao_edi_document_title(self):
        self.ensure_one()
        return {
            'FT': 'Factura',
            'FR': 'Factura/Recibo',
            'FA': 'Factura de Adiantamento',
            'NC': 'Nota de Crédito',
            'ND': 'Nota de Débito',
        }.get(self.l10n_ao_document_type, dict(AGT_DOCUMENT_TYPES).get(self.l10n_ao_document_type, ''))

    # -------------------------------------------------------------------------
    # Numeração AGT («FT <série>/<n.º>», sem zeros à esquerda e sem reinício anual)
    # -------------------------------------------------------------------------

    @api.depends('l10n_ao_document_type', 'invoice_date', 'company_id.l10n_ao_edi_enabled')
    def _compute_name_placeholder(self):
        result = super()._compute_name_placeholder()
        Series = self.env['l10n_ao_edi.series']
        for move in self.filtered(lambda m: m.l10n_ao_edi_required and m.state == 'draft' and m.l10n_ao_document_type):
            date = move.invoice_date or fields.Date.context_today(move)
            series = Series._l10n_ao_edi_find(move.company_id, move.l10n_ao_document_type, date.year)
            move.name_placeholder = (
                f'{move.l10n_ao_document_type} {series.code}/{series.next_number}' if series else False
            )
        return result

    def _l10n_ao_edi_number(self):
        self.ensure_one()
        return self.name

    def _l10n_ao_edi_ready_to_send(self):
        """Uma NC/ND só segue depois de a AGT ter recebido o documento de origem."""
        self.ensure_one()
        origin = self.reversed_entry_id if self.move_type == 'out_refund' else self.debit_origin_id
        return self.state == 'posted' and (not origin or origin.l10n_ao_edi_state in ('sent', 'valid'))

    def _get_last_sequence_domain(self, relaxed=False):
        # Os documentos AGT têm numeração própria (série AGT): os outros movimentos do diário de vendas
        # (ex.: fecho de sessão do POS) não podem continuar essa numeração nem ocupar números da série.
        condition = super()._get_last_sequence_domain(relaxed)
        if self.l10n_ao_edi_series_id:
            return condition
        return SQL('%s AND l10n_ao_edi_series_id IS NULL', condition)

    def _l10n_ao_edi_uses_agt_numbering(self):
        self.ensure_one()
        return bool(self.l10n_ao_edi_series_id)

    def _deduce_sequence_number_reset(self, name):
        if self and len(self) == 1 and self._l10n_ao_edi_uses_agt_numbering():
            return 'never'
        return super()._deduce_sequence_number_reset(name)

    def _sequence_matches_date(self):
        if self._l10n_ao_edi_uses_agt_numbering():
            return True
        return super()._sequence_matches_date()

    def _must_check_constrains_date_sequence(self):
        if self._l10n_ao_edi_uses_agt_numbering():
            return False
        return super()._must_check_constrains_date_sequence()

    def _l10n_ao_edi_assign_number(self):
        self.ensure_one()
        date = self.invoice_date or fields.Date.context_today(self)
        series, number = self.env['l10n_ao_edi.series']._l10n_ao_edi_next_number(
            self.company_id, self.l10n_ao_document_type, date.year
        )
        self.write(
            {
                'l10n_ao_edi_series_id': series.id,
                'l10n_ao_edi_contingency': series.contingency,
                'name': f'{self.l10n_ao_document_type} {series.code}/{number}',
            }
        )

    # -------------------------------------------------------------------------
    # Validação antes da emissão (DP n.º 71/25)
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_check_before_post(self):
        self.ensure_one()
        errors = []
        partner = self.commercial_partner_id
        is_foreign = partner.country_id and partner.country_id.code != 'AO'
        if partner.vat and not partner._l10n_ao_is_valid_nif(partner.vat) and not is_foreign:
            errors.append(self.env._('O NIF do cliente %s é inválido.', partner.display_name))
        if is_foreign and not partner.vat:
            # O NIF genérico 999999999 só é admitido para adquirentes domésticos (customerTaxID).
            errors.append(self.env._('Indique a identificação fiscal do cliente estrangeiro %s.', partner.display_name))
        if not self.invoice_date:
            errors.append(self.env._('Indique a data da factura.'))
        elif self.invoice_date > fields.Date.context_today(self):
            errors.append(self.env._('A data da factura não pode ser posterior à data de emissão.'))
        else:
            last = self.search(
                [
                    ('company_id', '=', self.company_id.id),
                    ('l10n_ao_document_type', '=', self.l10n_ao_document_type),
                    ('l10n_ao_edi_series_id', '!=', False),
                    ('state', '=', 'posted'),
                    ('invoice_date', '>', self.invoice_date),
                    ('id', '!=', self.id),
                ],
                limit=1,
            )
            if last:
                errors.append(
                    self.env._(
                        'A data da factura (%(date)s) é anterior à do documento %(last)s já emitido: '
                        'a numeração tem de seguir a ordem cronológica.',
                        date=self.invoice_date,
                        last=last.name,
                    )
                )
        for line in self.invoice_line_ids.filtered(lambda aml: aml.display_type == 'product'):
            agt_taxes = line.tax_ids.filtered('l10n_ao_tax_type')
            if not agt_taxes:
                errors.append(
                    self.env._(
                        'A linha «%s» não tem imposto com classificação AGT (IVA, isento ou não sujeito).', line.name
                    )
                )
            if line.price_subtotal < 0 or line.quantity < 0 or line.price_unit < 0:
                # A AGT não aceita valores negativos nas linhas (mínimo 0).
                errors.append(
                    self.env._(
                        'A linha «%s» tem valor negativo: use o desconto (%%) da linha ou emita uma nota de crédito.',
                        line.name,
                    )
                )
        reason_required = self.move_type == 'out_refund' or self.l10n_ao_document_type == 'ND'
        if reason_required and not self._l10n_ao_edi_reason_text():
            errors.append(
                self.env._('Indique o motivo (AGT) da nota de crédito ou de débito (art. 8.º do DP n.º 71/25).')
            )
        if self.move_type == 'out_refund':
            origin = self.reversed_entry_id
            if not origin:
                errors.append(
                    self.env._('A nota de crédito tem de referir a factura de origem (art. 8.º do DP n.º 71/25).')
                )
            elif origin.l10n_ao_edi_state not in ('sent', 'valid'):
                errors.append(self.env._('A factura de origem %s não foi aceite pela AGT.', origin.name))
            elif self._l10n_ao_edi_credited_amount(origin) > origin.amount_total + origin.currency_id.rounding / 2:
                errors.append(
                    self.env._(
                        'As notas de crédito excedem o valor da factura de origem %(origin)s (%(total)s).',
                        origin=origin.name,
                        total=origin.currency_id.format(origin.amount_total),
                    )
                )
        if self.l10n_ao_document_type == 'ND' and self.debit_origin_id.l10n_ao_edi_state not in ('sent', 'valid'):
            errors.append(self.env._('O documento de origem da nota de débito não foi aceite pela AGT.'))
        if errors:
            raise UserError(self.env._('Documento %s:\n', self.display_name) + '\n'.join(f'• {e}' for e in errors))

    def _l10n_ao_edi_credited_amount(self, origin):
        """Total das notas de crédito AGT emitidas sobre ``origin``, incluindo esta."""
        credit_notes = self.search(
            [
                ('reversed_entry_id', '=', origin.id),
                ('move_type', '=', 'out_refund'),
                ('l10n_ao_edi_state', 'in', EDI_LOCKED_STATES),
                ('id', '!=', self.id),
            ]
        )
        return sum(credit_notes.mapped('amount_total')) + self.amount_total

    def _post(self, soft=True):
        if self.env.company.l10n_ao_edi_enabled or any(self.company_id.mapped('l10n_ao_edi_enabled')):
            receipts = self.filtered(lambda m: m.move_type == 'out_receipt' and m.company_id.l10n_ao_edi_enabled)
            if receipts:
                raise UserError(
                    self.env._(
                        'Os recibos de venda do Odoo não são documentos AGT: emita uma Factura/Recibo (FR) '
                        'numa factura de cliente.'
                    )
                )
        to_number = self.filtered(lambda m: m.l10n_ao_edi_required and m.state == 'draft')
        for move in to_number:
            if not move.invoice_date:
                # Como o Odoo faz ao confirmar: a data da factura é a data de emissão.
                move.invoice_date = fields.Date.context_today(move)
            move.company_id._l10n_ao_edi_check_configuration()
            move.company_id._l10n_ao_edi_check_communication_lock()
            move._l10n_ao_edi_check_before_post()
            if move.l10n_ao_edi_state == 'invalid':
                # Correcção de um documento rejeitado: novo número, com referência ao rejeitado (documentStatus «C»).
                move.l10n_ao_edi_rejected_document_no = move.name
                move._l10n_ao_edi_archive_rejected_payload()
                move.write({'name': '/', 'l10n_ao_edi_series_id': False, 'l10n_ao_edi_print_count': 0})
            if not move.l10n_ao_edi_series_id:
                move._l10n_ao_edi_assign_number()
        posted = super()._post(soft=soft)
        to_send = posted.filtered(lambda m: m.l10n_ao_edi_required and m.l10n_ao_edi_series_id)
        if to_send:
            to_send.write(
                {
                    'l10n_ao_edi_state': 'to_send',
                    'l10n_ao_edi_error': False,
                    'l10n_ao_edi_system_entry_date': fields.Datetime.now(),
                }
            )
            # O documento fica fixado na emissão: é este o enviado, mesmo que o cliente ou os artigos mudem.
            for move in to_send:
                move.l10n_ao_edi_payload = json.dumps(move._l10n_ao_edi_document_values(), ensure_ascii=False)
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_send').sudo()._trigger()
        return posted

    def _l10n_ao_edi_archive_rejected_payload(self):
        """Guarda o documento rejeitado antes de o substituir pelo de correcção (histórico para o SAF-T)."""
        for record in self.filtered('l10n_ao_edi_payload'):
            history = json.loads(record.l10n_ao_edi_rejected_payloads or '[]')
            history.append(json.loads(record.l10n_ao_edi_payload))
            record.l10n_ao_edi_rejected_payloads = json.dumps(history, ensure_ascii=False)

    def _l10n_ao_edi_payload_values(self):
        """Documento a enviar: o fixado na emissão (ou calculado agora, para documentos anteriores)."""
        self.ensure_one()
        return json.loads(self.l10n_ao_edi_payload) if self.l10n_ao_edi_payload else self._l10n_ao_edi_document_values()

    def _l10n_ao_edi_value_changes(self, field_name, value):
        field = self._fields[field_name]
        return field.convert_to_record(field.convert_to_cache(value, self), self) != self[field_name]

    def write(self, vals):
        if locked_fields := [field for field in LOCKED_FIELDS if field in vals]:
            for move in self._l10n_ao_edi_locked():
                changed = [field for field in locked_fields if move._l10n_ao_edi_value_changes(field, vals[field])]
                if changed:
                    raise UserError(
                        self.env._(
                            'O documento %(doc)s já foi emitido e comunicado à AGT: não é possível alterar %(fields)s. '
                            'Emita uma nota de crédito.',
                            doc=move.name,
                            fields=', '.join(move._fields[field].string for field in changed),
                        )
                    )
        return super().write(vals)

    # -------------------------------------------------------------------------
    # Bloqueios: um documento comunicado à AGT só se corrige por nota de crédito
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_locked(self):
        return self.filtered(lambda m: m.l10n_ao_edi_state in EDI_LOCKED_STATES)

    def button_draft(self):
        if locked := self._l10n_ao_edi_locked():
            raise UserError(
                self.env._(
                    'Os documentos %s já foram comunicados à AGT: não podem voltar a rascunho. '
                    'Emita uma nota de crédito (art. 8.º do DP n.º 71/25).',
                    ', '.join(locked.mapped('name')),
                )
            )
        return super().button_draft()

    def button_cancel(self):
        if locked := self._l10n_ao_edi_locked():
            raise UserError(
                self.env._(
                    'Os documentos %s já foram comunicados à AGT: anule-os com uma nota de crédito.',
                    ', '.join(locked.mapped('name')),
                )
            )
        return super().button_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_l10n_ao_edi(self):
        if self.filtered('l10n_ao_edi_series_id'):
            raise UserError(self.env._('Não é possível apagar documentos com numeração AGT.'))

    # -------------------------------------------------------------------------
    # Facturas de fornecedor: confirmar / rejeitar na AGT (validarDocumento)
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_vendor_deduct_all(self):
        """AD: todo o IVA da factura é dedutível; ND: nenhum (deductAllVAT)."""
        self.ensure_one()
        deductible_account = (
            self.env['account.chart.template'].with_company(self.company_id).ref('ao_34_2_3', raise_if_not_found=False)
        )
        tax_lines = self.line_ids.filtered('tax_line_id')
        return 'AD' if tax_lines and all(line.account_id == deductible_account for line in tax_lines) else 'ND'

    def _l10n_ao_edi_vendor_validate(self, action):
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund') or move.state != 'posted':
                raise UserError(self.env._('Só se validam na AGT facturas de fornecedor confirmadas.'))
            document_no = (move.l10n_ao_edi_vendor_document_no or move.ref or '').strip()
            if not document_no:
                raise UserError(self.env._('Indique o n.º AGT do documento do fornecedor.'))
            company = move.company_id
            company._l10n_ao_edi_check_configuration()
            nif = company.partner_id._l10n_ao_normalize_nif(company.vat)
            payload = {
                **company._l10n_ao_edi_request_envelope(),
                'jwsSignature': company._l10n_ao_edi_sign({'taxRegistrationNumber': nif, 'documentNo': document_no}),
                'documentNo': document_no,
                'action': action,
            }
            if action == 'C':
                payload['deductAllVAT'] = move._l10n_ao_edi_vendor_deduct_all()
            status, body = company._l10n_ao_edi_call('validarDocumento', payload)
            body = body if isinstance(body, dict) else {}
            result = body.get('confirmRejectResult') or {}
            ok = status == 200 and result.get('actionResultCode') == f'{action}_OK'
            self.env['l10n_ao_edi.document']._log_call(
                company, 'validarDocumento', payload, status, body, ok=ok, records=move
            )
            if not ok:
                errors = self.env['l10n_ao_edi.document']._format_errors(
                    result.get('errorList') or (body or {}).get('errorList') or [], code_key='errorCode'
                )
                raise UserError(
                    self.env._('A AGT não aceitou a validação: %s', errors or result.get('actionResultCode') or status)
                )
            move.write(
                {
                    'l10n_ao_edi_vendor_document_no': document_no,
                    'l10n_ao_edi_vendor_state': 'confirmed' if action == 'C' else 'rejected',
                }
            )
        return True

    def action_l10n_ao_edi_vendor_confirm(self):
        return self._l10n_ao_edi_vendor_validate('C')

    def action_l10n_ao_edi_vendor_reject(self):
        return self._l10n_ao_edi_vendor_validate('R')

    def action_l10n_ao_edi_send_now(self):
        if self.company_id.filtered('l10n_ao_edi_contingency'):
            raise UserError(
                self.env._(
                    'A empresa está em modo de contingência: os documentos são enviados quando o modo for desligado.'
                )
            )
        self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._send_moves(self)
        return True

    # -------------------------------------------------------------------------
    # Estrutura de dados do documento (Anexo I do DE n.º 683/25, serviço registarFactura)
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_reason_text(self):
        # Só o motivo escrito pelo utilizador: a referência do Odoo («Estorno de: …») não é um motivo.
        return (self.l10n_ao_edi_reason or '').strip()

    def _l10n_ao_edi_customer_tax_id(self):
        return self.commercial_partner_id._l10n_ao_edi_customer_tax_id()

    def _get_document_partner_ident_line(self):
        # DP 71/25: o documento identifica sempre o adquirente; sem NIF, é o consumidor final (o mesmo que vai à AGT).
        if not self.l10n_ao_edi_series_id or not self.partner_id:
            return super()._get_document_partner_ident_line()
        tax_id = self._l10n_ao_edi_customer_tax_id()
        return self.env._('NIF: Consumidor final') if tax_id == FINAL_CONSUMER_NIF else self.env._('NIF: %s', tax_id)

    @api.model
    def _l10n_ao_edi_round_up(self, amount):
        return float_round(amount, precision_digits=2, rounding_method='UP')

    def _l10n_ao_edi_line_values(self, line, line_number, base_line):
        """Linha do documento. Preços sem imposto; o imposto de cada taxa é o da própria linha no Odoo
        (base arredondada x taxa, por excesso), para que os totais coincidam com os do documento."""
        is_refund = self.move_type == 'out_refund'
        quantity = abs(line.quantity)
        amount = abs(line.price_subtotal)
        unit_price = amount / quantity if quantity else 0.0
        unit_price_base = line.tax_ids.compute_all(
            line.price_unit, self.currency_id, 1.0, product=line.product_id, partner=self.partner_id
        )['total_excluded']
        tax_amounts = {
            tax_data['tax'].id: abs(tax_data['raw_tax_amount_currency'])
            for tax_data in base_line['tax_details']['taxes_data']
            if not tax_data.get('is_reverse_charge')
        }
        taxes = []
        for tax in line.tax_ids.filtered('l10n_ao_tax_type'):
            tax_values = {
                'taxType': tax.l10n_ao_tax_type,
                'taxCountryRegion': tax.l10n_ao_tax_region or 'AO',
            }
            if tax.l10n_ao_tax_code:
                tax_values['taxCode'] = tax.l10n_ao_tax_code
            tax_values['taxPercentage'] = tax.amount if tax.amount_type == 'percent' else 0.0
            tax_values['taxContribution'] = round(tax_amounts.get(tax.id, 0.0), 2)
            if tax.l10n_ao_exemption_id:
                tax_values['taxExemptionCode'] = tax.l10n_ao_exemption_id.code
            taxes.append(tax_values)
        values = {
            'lineNumber': line_number,
            'operationType': line.l10n_ao_operation_type or 'SG',
            'productCode': (line.product_id.default_code or str(line.product_id.id or 'SERV'))[:60],
            'productDescription': (line.name or line.product_id.display_name or '-')[:200],
            'quantity': quantity,
            'unitOfMeasure': (line.product_uom_id.name or 'UN')[:20],
            'unitPriceBase': float_round(unit_price_base, precision_digits=2),
            'unitPrice': float_round(unit_price, precision_digits=2),
            'debitAmount' if is_refund else 'creditAmount': amount,
            'taxes': taxes,
            'settlementAmount': max(float_round(quantity * unit_price_base - amount, precision_digits=2), 0.0),
        }
        origin = self.reversed_entry_id if is_refund else self.debit_origin_id
        if origin:
            values['referenceInfo'] = {'reference': origin.name, 'reason': self._l10n_ao_edi_reason_text()[:60]}
        return values

    def _l10n_ao_edi_document_values(self):
        """Documento a enviar no registarFactura."""
        self.ensure_one()
        company = self.company_id
        product_lines = self.invoice_line_ids.filtered(lambda aml: aml.display_type == 'product')
        base_lines = [self._prepare_product_base_line_for_taxes_computation(line) for line in product_lines]
        self.env['account.tax']._add_tax_details_in_base_lines(base_lines, company)
        lines = [
            self._l10n_ao_edi_line_values(line, index, base_line)
            for index, (line, base_line) in enumerate(zip(product_lines, base_lines, strict=True), start=1)
        ]
        tax_payable = round(sum(tax['taxContribution'] for line in lines for tax in line['taxes']), 2)
        net_total = round(sum(line.get('creditAmount', line.get('debitAmount', 0.0)) for line in lines), 2)
        totals = {'taxPayable': tax_payable, 'netTotal': net_total, 'grossTotal': round(net_total + tax_payable, 2)}
        if self.currency_id != company.currency_id:
            # Contravalor em Kz: grossTotal x exchangeRate (câmbio do documento), arredondado às centésimas
            # por arredondamento matemático (0,005 sobe).
            rate = 1.0 / self.invoice_currency_rate if self.invoice_currency_rate else 1.0
            totals['currency'] = {
                'currencyCode': self.currency_id.name,
                'currencyAmount': float_round(
                    totals['grossTotal'] * rate, precision_digits=2, rounding_method='HALF-UP'
                ),
                'exchangeRate': float_round(rate, precision_digits=6),
            }
        customer_tax_id = self._l10n_ao_edi_customer_tax_id()
        customer_country = self.commercial_partner_id.country_id.code or 'AO'
        company_name = (self.commercial_partner_id.name or '')[:200]
        document_date = fields.Date.to_string(self.invoice_date)
        signed = {
            'documentNo': self.name,
            'taxRegistrationNumber': company.partner_id._l10n_ao_normalize_nif(company.vat),
            'documentType': self.l10n_ao_document_type,
            'documentDate': document_date,
            'customerTaxID': customer_tax_id,
            'customerCountry': customer_country,
            'companyName': company_name,
            'documentTotals': totals,
        }
        values = {
            'documentNo': self.name,
            'documentStatus': 'C' if self.l10n_ao_edi_rejected_document_no else 'N',
        }
        if self.l10n_ao_edi_rejected_document_no:
            values['rejectedDocumentNo'] = self.l10n_ao_edi_rejected_document_no
        values.update(
            {
                'jwsDocumentSignature': company._l10n_ao_edi_sign(signed),
                'documentDate': document_date,
                'documentType': self.l10n_ao_document_type,
            }
        )
        if company.l10n_ao_cae_id:
            values['eacCode'] = company.l10n_ao_cae_id.code
        entry_date = fields.Datetime.context_timestamp(
            self.with_context(tz='Africa/Luanda'), self.l10n_ao_edi_system_entry_date or fields.Datetime.now()
        )
        values.update(
            {
                'systemEntryDate': entry_date.strftime('%Y-%m-%dT%H:%M:%S'),
                'customerTaxID': customer_tax_id,
                'customerCountry': customer_country,
                'companyName': company_name,
                'lines': lines,
                'documentTotals': totals,
            }
        )
        return values
