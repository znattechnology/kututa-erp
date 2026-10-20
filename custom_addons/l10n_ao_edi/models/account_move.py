from urllib.parse import quote

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round

from .l10n_ao_edi_series import AGT_DOCUMENT_TYPES

AGT_QR_URL = 'https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe'
FINAL_CONSUMER_NIF = '999999999'
EDI_LOCKED_STATES = ('to_send', 'sent', 'valid')


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
        series = self.env['l10n_ao_edi.series']._l10n_ao_edi_find(
            self.company_id, self.l10n_ao_document_type, date.year
        )
        if not series:
            raise UserError(
                self.env._(
                    'Não existe uma série AGT activa para %(type)s em %(year)s (estabelecimento %(est)s). '
                    'Peça a série em Facturação > Configuração > Séries AGT.',
                    type=self.l10n_ao_document_type,
                    year=date.year,
                    est=self.company_id.l10n_ao_edi_establishment or 'SEDE',
                )
            )
        number = series._l10n_ao_edi_reserve_number()
        self.write({'l10n_ao_edi_series_id': series.id, 'name': f'{self.l10n_ao_document_type} {series.code}/{number}'})

    # -------------------------------------------------------------------------
    # Validação antes da emissão (DP n.º 71/25)
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_check_before_post(self):
        self.ensure_one()
        errors = []
        partner = self.commercial_partner_id
        if partner.vat and not partner._l10n_ao_is_valid_nif(partner.vat) and partner.country_id.code in (False, 'AO'):
            errors.append(self.env._('O NIF do cliente %s é inválido.', partner.display_name))
        if not self.invoice_date:
            errors.append(self.env._('Indique a data da factura.'))
        elif self.invoice_date > fields.Date.context_today(self):
            errors.append(self.env._('A data da factura não pode ser posterior à data de emissão.'))
        for line in self.invoice_line_ids.filtered(lambda aml: aml.display_type == 'product'):
            agt_taxes = line.tax_ids.filtered('l10n_ao_tax_type')
            if not agt_taxes:
                errors.append(
                    self.env._(
                        'A linha «%s» não tem imposto com classificação AGT (IVA, isento ou não sujeito).', line.name
                    )
                )
        if self.move_type == 'out_refund':
            origin = self.reversed_entry_id
            if not origin:
                errors.append(
                    self.env._('A nota de crédito tem de referir a factura de origem (art. 8.º do DP n.º 71/25).')
                )
            elif origin.l10n_ao_edi_state not in ('sent', 'valid'):
                errors.append(self.env._('A factura de origem %s não foi aceite pela AGT.', origin.name))
            if not self._l10n_ao_edi_reason_text():
                errors.append(self.env._('Indique o motivo da nota de crédito (anulação ou rectificação).'))
        if self.l10n_ao_document_type == 'ND' and self.debit_origin_id.l10n_ao_edi_state not in ('sent', 'valid'):
            errors.append(self.env._('O documento de origem da nota de débito não foi aceite pela AGT.'))
        if errors:
            raise UserError(self.env._('Documento %s:\n', self.display_name) + '\n'.join(f'• {e}' for e in errors))

    def _post(self, soft=True):
        to_number = self.filtered(lambda m: m.l10n_ao_edi_required and m.state == 'draft')
        for move in to_number:
            if not move.invoice_date:
                # Como o Odoo faz ao confirmar: a data da factura é a data de emissão.
                move.invoice_date = fields.Date.context_today(move)
            move.company_id._l10n_ao_edi_check_configuration()
            move._l10n_ao_edi_check_before_post()
            if move.l10n_ao_edi_state == 'invalid':
                # Correcção de um documento rejeitado: novo número, com referência ao rejeitado (documentStatus «C»).
                move.l10n_ao_edi_rejected_document_no = move.name
                move.write({'name': '/', 'l10n_ao_edi_series_id': False})
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
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_send')._trigger()
        return posted

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

    def action_l10n_ao_edi_send_now(self):
        self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._send_moves(self)
        return True

    # -------------------------------------------------------------------------
    # Estrutura de dados do documento (Anexo I do DE n.º 683/25, serviço registarFactura)
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_reason_text(self):
        return (self.l10n_ao_edi_reason or self.ref or '').strip()

    def _l10n_ao_edi_customer_tax_id(self):
        partner = self.commercial_partner_id
        if partner.country_id and partner.country_id.code != 'AO':
            return (partner.vat or FINAL_CONSUMER_NIF)[:50]
        nif = partner._l10n_ao_normalize_nif(partner.vat)
        return nif if nif and partner._l10n_ao_is_valid_nif(nif) else FINAL_CONSUMER_NIF

    @api.model
    def _l10n_ao_edi_round_up(self, amount):
        return float_round(amount, precision_digits=2, rounding_method='UP')

    def _l10n_ao_edi_line_values(self, line, line_number):
        is_refund = self.move_type == 'out_refund'
        quantity = line.quantity
        unit_price_base = line.price_unit
        unit_price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
        amount = line.price_subtotal
        taxes = []
        for tax in line.tax_ids.filtered('l10n_ao_tax_type'):
            tax_values = {
                'taxType': tax.l10n_ao_tax_type,
                'taxCountryRegion': tax.l10n_ao_tax_region or 'AO',
            }
            if tax.l10n_ao_tax_code:
                tax_values['taxCode'] = tax.l10n_ao_tax_code
            tax_values['taxPercentage'] = tax.amount if tax.amount_type == 'percent' else 0.0
            tax_values['taxContribution'] = self._l10n_ao_edi_round_up(amount * tax_values['taxPercentage'] / 100.0)
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
            'unitPriceBase': unit_price_base,
            'unitPrice': unit_price,
            'debitAmount' if is_refund else 'creditAmount': amount,
            'taxes': taxes,
            'settlementAmount': float_round(quantity * unit_price_base - amount, precision_digits=2),
        }
        origin = self.reversed_entry_id if is_refund else self.debit_origin_id
        if origin:
            values['referenceInfo'] = {'reference': origin.name, 'reason': self._l10n_ao_edi_reason_text()[:60]}
        return values

    def _l10n_ao_edi_document_values(self):
        """Documento a enviar no registarFactura."""
        self.ensure_one()
        company = self.company_id
        lines = [
            self._l10n_ao_edi_line_values(line, index)
            for index, line in enumerate(
                self.invoice_line_ids.filtered(lambda aml: aml.display_type == 'product'), start=1
            )
        ]
        tax_payable = round(sum(tax['taxContribution'] for line in lines for tax in line['taxes']), 2)
        net_total = round(sum(line.get('creditAmount', line.get('debitAmount', 0.0)) for line in lines), 2)
        totals = {'taxPayable': tax_payable, 'netTotal': net_total, 'grossTotal': round(net_total + tax_payable, 2)}
        if self.currency_id != company.currency_id:
            # Contravalor em Kz: grossTotal x exchangeRate, arredondado matematicamente às centésimas.
            rate = abs(self.amount_total_signed / self.amount_total) if self.amount_total else 1.0
            totals['currency'] = {
                'currencyCode': self.currency_id.name,
                'currencyAmount': round(totals['grossTotal'] * rate, 2),
                'exchangeRate': rate,
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
