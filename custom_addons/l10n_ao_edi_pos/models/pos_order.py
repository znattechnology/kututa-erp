import json
from urllib.parse import quote

from odoo import api, fields, models
from odoo.addons.l10n_ao_edi.models.account_move import AGT_QR_URL, EDI_LOCKED_STATES
from odoo.addons.l10n_ao_edi.models.res_partner import FINAL_CONSUMER_NIF
from odoo.exceptions import UserError
from odoo.tools import float_round

DOCUMENT_TITLES = {
    'TV': 'Talão de Venda',
    'NC': 'Nota de Crédito',
    'FR': 'Factura/Recibo',
    'FT': 'Factura',
}


class PosOrder(models.Model):
    """Talão de Venda (TV) e Nota de Crédito (NC) das vendas não facturadas do POS.

    Uma venda facturada não tem talão: o documento AGT é a própria factura (FR, ou FT se for a crédito).
    """

    _inherit = ['pos.order', 'l10n_ao_edi.guard.mixin']

    l10n_ao_edi_required = fields.Boolean(related='company_id.l10n_ao_edi_enabled')
    l10n_ao_document_type = fields.Selection(
        selection=[('TV', 'TV - Talão de Venda'), ('NC', 'NC - Nota de Crédito')],
        string='Tipo de documento (AGT)',
        readonly=True,
        copy=False,
    )
    l10n_ao_edi_series_id = fields.Many2one('l10n_ao_edi.series', string='Série AGT', readonly=True, copy=False)
    l10n_ao_edi_document_no = fields.Char(string='N.º do documento (AGT)', readonly=True, copy=False, index=True)
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
    l10n_ao_edi_contingency = fields.Boolean(string='Emitido em contingência', readonly=True, copy=False)
    l10n_ao_edi_rejected_payloads = fields.Text(
        string='Documentos rejeitados (JSON)',
        readonly=True,
        copy=False,
        help='Documentos AGT anteriores deste registo, rejeitados e substituídos: ficam no SAF-T como anulados.',
    )
    l10n_ao_edi_rejected_document_no = fields.Char(string='Documento rejeitado corrigido', readonly=True, copy=False)
    l10n_ao_edi_payload = fields.Text(string='Documento AGT (JSON)', readonly=True, copy=False)
    l10n_ao_edi_reason = fields.Char(
        string='Motivo da devolução (AGT)',
        copy=False,
        help='Motivo da nota de crédito comunicado à AGT (art. 8.º do DP n.º 71/25, até 60 caracteres).',
    )
    l10n_ao_edi_print_count = fields.Integer(
        string='Impressões do documento AGT',
        readonly=True,
        copy=False,
        help='A primeira impressão é o «Original»; as seguintes levam a menção «2.ª via».',
    )
    l10n_ao_edi_document_ids = fields.Many2many(
        'l10n_ao_edi.document',
        'l10n_ao_edi_document_pos_order_rel',
        'pos_order_id',
        'document_id',
        string='Pedidos AGT',
        readonly=True,
        copy=False,
    )
    # Documento AGT a imprimir no talão: o do próprio POS (TV/NC) ou a factura gerada (FR/FT/NC).
    l10n_ao_edi_receipt_number = fields.Char(compute='_compute_l10n_ao_edi_receipt')
    l10n_ao_edi_receipt_title = fields.Char(compute='_compute_l10n_ao_edi_receipt')
    l10n_ao_edi_receipt_qr_url = fields.Char(compute='_compute_l10n_ao_edi_receipt')
    l10n_ao_edi_receipt_contingency = fields.Boolean(compute='_compute_l10n_ao_edi_receipt')
    l10n_ao_edi_receipt_pending = fields.Boolean(compute='_compute_l10n_ao_edi_receipt')
    l10n_ao_edi_receipt_reference = fields.Char(compute='_compute_l10n_ao_edi_receipt')

    @api.depends('l10n_ao_edi_document_no', 'l10n_ao_edi_state', 'account_move.name', 'account_move.l10n_ao_edi_state')
    def _compute_l10n_ao_edi_receipt(self):
        for order in self:
            invoice = order.account_move.sudo()
            if order.l10n_ao_edi_document_no:
                number = order.l10n_ao_edi_document_no
                title = DOCUMENT_TITLES[order.l10n_ao_document_type]
                contingency = order.l10n_ao_edi_contingency
                state = order.l10n_ao_edi_state
                reference = order._l10n_ao_edi_origin_number()
                reason = order._l10n_ao_edi_reason_text()
            elif invoice.l10n_ao_edi_series_id:
                number = invoice.name
                title = invoice._l10n_ao_edi_document_title()
                contingency = invoice.l10n_ao_edi_contingency
                state = invoice.l10n_ao_edi_state
                reference = invoice.reversed_entry_id.name
                reason = invoice._l10n_ao_edi_reason_text()
            else:
                order.update(
                    {
                        'l10n_ao_edi_receipt_number': False,
                        'l10n_ao_edi_receipt_title': False,
                        'l10n_ao_edi_receipt_qr_url': False,
                        'l10n_ao_edi_receipt_contingency': False,
                        'l10n_ao_edi_receipt_pending': False,
                        'l10n_ao_edi_receipt_reference': False,
                    }
                )
                continue
            emitter = order.company_id.partner_id._l10n_ao_normalize_nif(order.company_id.vat)
            order.update(
                {
                    'l10n_ao_edi_receipt_number': number,
                    'l10n_ao_edi_receipt_title': title,
                    'l10n_ao_edi_receipt_qr_url': f'{AGT_QR_URL}?emissor={emitter}&document={quote(number, safe="/")}',
                    'l10n_ao_edi_receipt_contingency': contingency,
                    'l10n_ao_edi_receipt_pending': contingency and state != 'valid',
                    'l10n_ao_edi_receipt_reference': (
                        f'{reference} ({reason})' if reference and reason else reference or False
                    ),
                }
            )

    def _l10n_ao_edi_number(self):
        self.ensure_one()
        return self.l10n_ao_edi_document_no

    def _l10n_ao_edi_reason_text(self):
        return (self.l10n_ao_edi_reason or '').strip()

    def _l10n_ao_edi_origin(self):
        """Documento AGT devolvido por esta nota de crédito: o talão ou a factura da venda original."""
        self.ensure_one()
        origin = self.refunded_order_id
        return origin.account_move if origin.account_move.l10n_ao_edi_series_id else origin

    def _l10n_ao_edi_origin_number(self):
        self.ensure_one()
        origin = self._l10n_ao_edi_origin()
        return origin.name if origin._name == 'account.move' else origin.l10n_ao_edi_document_no

    def _l10n_ao_edi_ready_to_send(self):
        """Uma NC só segue depois de a AGT ter recebido o documento de origem."""
        self.ensure_one()
        return self.l10n_ao_document_type != 'NC' or self._l10n_ao_edi_origin().l10n_ao_edi_state in ('sent', 'valid')

    def _l10n_ao_edi_payload_values(self):
        self.ensure_one()
        return json.loads(self.l10n_ao_edi_payload) if self.l10n_ao_edi_payload else self._l10n_ao_edi_document_values()

    # -------------------------------------------------------------------------
    # Emissão
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_check_before_paid(self):
        self.ensure_one()
        errors = []
        if self.currency_id != self.company_id.currency_id:
            errors.append(
                self.env._('O Ponto de Venda tem de vender em %s (moeda da empresa).', self.company_id.currency_id.name)
            )
        methods = self.payment_ids.payment_method_id
        if any(m.type == 'pay_later' for m in methods) and any(m.type != 'pay_later' for m in methods):
            # A crédito emite-se uma Factura (FT) e o recebimento dá um recibo à parte: não se misturam no talão.
            errors.append(self.env._('Não misture «Conta do Cliente» com outros meios de pagamento na mesma venda.'))
        for line in self.lines:
            if line.price_unit < 0 or (line.qty > 0 and line.price_subtotal < 0):
                errors.append(
                    self.env._(
                        'A linha «%s» tem preço negativo: a AGT não aceita valores negativos. Use o desconto (%%) '
                        'da linha.',
                        line.full_product_name or line.product_id.display_name,
                    )
                )
            if not line.tax_ids_after_fiscal_position.filtered('l10n_ao_tax_type'):
                errors.append(
                    self.env._(
                        'O produto «%s» não tem imposto com classificação AGT (IVA, isento ou não sujeito).',
                        line.full_product_name or line.product_id.display_name,
                    )
                )
        refunded = self.refunded_order_id
        if refunded:
            if any(line.qty > 0 for line in self.lines):
                errors.append(self.env._('Uma devolução não pode incluir vendas: registe-as num talão à parte.'))
            if not self._l10n_ao_edi_reason_text():
                errors.append(self.env._('Indique o motivo da devolução (art. 8.º do DP n.º 71/25).'))
            origin = self._l10n_ao_edi_origin()
            origin_number = self._l10n_ao_edi_origin_number()
            for line in self.lines.filtered('refunded_orderline_id'):
                sold = line.refunded_orderline_id
                refunded = sum(sold.refund_orderline_ids.filtered(lambda r: r.order_id.state != 'cancel').mapped('qty'))
                if -refunded > sold.qty:
                    errors.append(
                        self.env._(
                            'Devolução de «%(product)s» acima do vendido (%(sold)s).',
                            product=sold.full_product_name or sold.product_id.display_name,
                            sold=sold.qty,
                        )
                    )
            if not origin_number:
                errors.append(self.env._('A venda devolvida não tem documento AGT.'))
            elif origin.l10n_ao_edi_state == 'invalid':
                errors.append(
                    self.env._('O documento %s foi rejeitado pela AGT: corrija-o antes de o devolver.', origin_number)
                )
            elif origin._name == 'account.move' and not self.to_invoice:
                errors.append(self.env._('A venda %s foi facturada: a devolução tem de ser facturada.', origin_number))
            elif origin._name == 'pos.order' and self.to_invoice:
                errors.append(
                    self.env._(
                        'A venda %s tem talão: a devolução não pode ser facturada (é emitida uma nota de crédito '
                        'ao talão).',
                        origin_number,
                    )
                )
        elif self.amount_total < 0 or any(line.qty < 0 for line in self.lines):
            errors.append(
                self.env._('Quantidades negativas só em devoluções: use «Reembolsar» no talão da venda original.')
            )
        if errors:
            raise UserError(self.env._('Venda %s:\n', self.name) + '\n'.join(f'• {e}' for e in errors))

    def action_pos_order_paid(self):
        # Também cobre as devoluções pagas no backend (pos.make.payment), que não passam pelo sync do POS.
        if self.l10n_ao_edi_required:
            self._l10n_ao_edi_check_before_paid()
        result = super().action_pos_order_paid()
        has_lines = any(line.qty for line in self.lines)
        if self.l10n_ao_edi_required and not self.to_invoice and not self.l10n_ao_edi_document_no and has_lines:
            self._l10n_ao_edi_issue_document()
        return result

    def _l10n_ao_edi_issue_document(self):
        self.ensure_one()
        company = self.company_id
        company._l10n_ao_edi_check_configuration()
        company._l10n_ao_edi_check_communication_lock()
        document_type = 'NC' if self.refunded_order_id else 'TV'
        # A série é a do ano da emissão (uma venda offline de 31/12 sincronizada em Janeiro é emitida em Janeiro).
        year = fields.Date.context_today(self.with_context(tz='Africa/Luanda')).year
        series, number = self.env['l10n_ao_edi.series']._l10n_ao_edi_next_number(company, document_type, year)
        if self.l10n_ao_edi_state == 'invalid' and self.l10n_ao_edi_payload:
            history = json.loads(self.l10n_ao_edi_rejected_payloads or '[]')
            history.append(json.loads(self.l10n_ao_edi_payload))
            self._l10n_ao_edi_set({'l10n_ao_edi_rejected_payloads': json.dumps(history, ensure_ascii=False)})
        self._l10n_ao_edi_set(
            {
                'l10n_ao_edi_rejected_document_no': self.l10n_ao_edi_document_no
                if self.l10n_ao_edi_state == 'invalid'
                else False,
                'l10n_ao_document_type': document_type,
                'l10n_ao_edi_series_id': series.id,
                'l10n_ao_edi_document_no': f'{document_type} {series.code}/{number}',
                'l10n_ao_edi_contingency': series.contingency,
                'l10n_ao_edi_state': 'to_send',
                'l10n_ao_edi_error': False,
                'l10n_ao_edi_system_entry_date': fields.Datetime.now(),
                'l10n_ao_edi_print_count': 0,
            }
        )
        # O documento fica fixado na emissão: é este o enviado à AGT.
        self._l10n_ao_edi_set(
            {'l10n_ao_edi_payload': json.dumps(self._l10n_ao_edi_document_values(), ensure_ascii=False)}
        )
        self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_send').sudo()._trigger()

    def action_l10n_ao_edi_correct(self):
        """Documento rejeitado pela AGT: emite o documento de correcção (novo número, documentStatus «C»)."""
        self._l10n_ao_edi_check_can_communicate('point_of_sale.group_pos_user')
        for order in self.filtered(lambda o: o.l10n_ao_edi_state == 'invalid'):
            order._l10n_ao_edi_issue_document()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        # Os dados da comunicação com a AGT vindos do POS (que reenvia as vendas sincronizadas) são ignorados.
        return super().create([self._l10n_ao_edi_strip_technical(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._l10n_ao_edi_strip_technical(vals))

    def process_saved_payments(self, order, existing_order):
        # Venda já paga e com documento AGT emitido: um novo envio do POS (re-sincronização) não a pode alterar.
        if existing_order.l10n_ao_edi_document_no:
            return None
        return super().process_saved_payments(order, existing_order)

    def action_l10n_ao_edi_send_now(self):
        self._l10n_ao_edi_check_can_communicate('point_of_sale.group_pos_user')
        self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._send_records(self)
        return True

    def l10n_ao_edi_register_print(self):
        """Chamado pelo POS depois de imprimir o documento AGT (a primeira impressão é o «Original»)."""
        for order in self.filtered('l10n_ao_edi_receipt_number'):
            order.sudo().l10n_ao_edi_print_count += 1
        return self.read(['l10n_ao_edi_print_count'])

    # -------------------------------------------------------------------------
    # Facturação no POS: Factura/Recibo (paga no acto) ou Factura (a crédito)
    # -------------------------------------------------------------------------

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        if not self.company_id.l10n_ao_edi_enabled:
            return vals
        if documented := self.filtered('l10n_ao_edi_document_no'):
            raise UserError(
                self.env._(
                    'As vendas %s já têm talão AGT: não podem ser facturadas (o talão é o documento da venda).',
                    ', '.join(documented.mapped('l10n_ao_edi_document_no')),
                )
            )
        if vals['move_type'] == 'out_invoice':
            is_pay_later = any(p.payment_method_id.type == 'pay_later' for p in self.payment_ids)
            vals['l10n_ao_document_type'] = 'FT' if is_pay_later else 'FR'
        elif len(self) == 1:
            vals['l10n_ao_edi_reason'] = self._l10n_ao_edi_reason_text()
        return vals

    # -------------------------------------------------------------------------
    # Bloqueios
    # -------------------------------------------------------------------------

    def action_pos_order_cancel(self):
        if locked := self.filtered(lambda o: o.l10n_ao_edi_state in EDI_LOCKED_STATES):
            raise UserError(
                self.env._(
                    'Os documentos %s já foram comunicados à AGT: devolva a venda (nota de crédito).',
                    ', '.join(locked.mapped('l10n_ao_edi_document_no')),
                )
            )
        return super().action_pos_order_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_l10n_ao_edi(self):
        if self.filtered('l10n_ao_edi_document_no'):
            raise UserError(self.env._('Não é possível apagar vendas com documento AGT.'))

    # -------------------------------------------------------------------------
    # Estrutura de dados do documento (Anexo I do DE n.º 683/25, serviço registarFactura)
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_partner_values(self):
        partner = self.partner_id.commercial_partner_id
        if not partner:
            return FINAL_CONSUMER_NIF, 'AO', 'Consumidor final'
        return partner._l10n_ao_edi_customer_tax_id(), partner.country_id.code or 'AO', (partner.name or '')[:200]

    def _l10n_ao_edi_line_values(self, line, line_number, base_line):
        """Preços sem imposto; o imposto de cada taxa é o da própria linha (base arredondada x taxa, por excesso),
        para que os totais coincidam com os da venda."""
        is_refund = self.l10n_ao_document_type == 'NC'
        taxes_to_apply = line.tax_ids_after_fiscal_position
        quantity = abs(line.qty)
        amount = abs(line.price_subtotal)
        unit_price_base = taxes_to_apply.compute_all(line.price_unit, self.currency_id, 1, line.product_id)[
            'total_excluded'
        ]
        unit_price = amount / quantity if quantity else 0.0
        tax_amounts = {
            tax_data['tax'].id: abs(tax_data['raw_tax_amount_currency'])
            for tax_data in base_line['tax_details']['taxes_data']
            if not tax_data.get('is_reverse_charge')
        }
        taxes = []
        for tax in taxes_to_apply.filtered('l10n_ao_tax_type'):
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
        product = line.product_id
        values = {
            'lineNumber': line_number,
            'operationType': product.l10n_ao_operation_type or ('SG' if product.type == 'service' else 'TB'),
            'productCode': (product.default_code or str(product.id or 'SERV'))[:60],
            'productDescription': (line.full_product_name or product.display_name or '-')[:200],
            'quantity': quantity,
            'unitOfMeasure': (line.product_uom_id.name or 'UN')[:20],
            'unitPriceBase': float_round(unit_price_base, precision_digits=2),
            'unitPrice': float_round(unit_price, precision_digits=2),
            'debitAmount' if is_refund else 'creditAmount': amount,
            'taxes': taxes,
            'settlementAmount': max(float_round(quantity * unit_price_base - amount, precision_digits=2), 0.0),
        }
        if is_refund:
            values['referenceInfo'] = {
                'reference': self._l10n_ao_edi_origin_number(),
                'reason': self._l10n_ao_edi_reason_text()[:60],
            }
        return values

    def _l10n_ao_edi_document_values(self):
        """Talão (TV) ou nota de crédito (NC) a enviar no registarFactura."""
        self.ensure_one()
        company = self.company_id
        order_lines = self.lines.filtered(lambda line: line.qty)
        base_lines = order_lines._prepare_base_lines_for_taxes_computation()
        self.env['account.tax']._add_tax_details_in_base_lines(base_lines, company)
        lines = [
            self._l10n_ao_edi_line_values(line, index, base_line)
            for index, (line, base_line) in enumerate(zip(order_lines, base_lines, strict=True), start=1)
        ]
        tax_payable = round(sum(tax['taxContribution'] for line in lines for tax in line['taxes']), 2)
        net_total = round(sum(line.get('creditAmount', line.get('debitAmount', 0.0)) for line in lines), 2)
        totals = {'taxPayable': tax_payable, 'netTotal': net_total, 'grossTotal': round(net_total + tax_payable, 2)}
        customer_tax_id, customer_country, company_name = self._l10n_ao_edi_partner_values()
        luanda = self.with_context(tz='Africa/Luanda')
        document_date = fields.Date.to_string(fields.Datetime.context_timestamp(luanda, self.date_order).date())
        signed = {
            'documentNo': self.l10n_ao_edi_document_no,
            'taxRegistrationNumber': company.partner_id._l10n_ao_normalize_nif(company.vat),
            'documentType': self.l10n_ao_document_type,
            'documentDate': document_date,
            'customerTaxID': customer_tax_id,
            'customerCountry': customer_country,
            'companyName': company_name,
            'documentTotals': totals,
        }
        values = {
            'documentNo': self.l10n_ao_edi_document_no,
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
            luanda, self.l10n_ao_edi_system_entry_date or fields.Datetime.now()
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
