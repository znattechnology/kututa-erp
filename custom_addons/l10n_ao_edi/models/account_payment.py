import json
from urllib.parse import quote

from odoo import api, fields, models
from odoo.exceptions import UserError

from .account_move import AGT_QR_URL, EDI_LOCKED_STATES

# Documentos que são pagos por recibo (a Factura/Recibo já é o próprio recibo; a NC não é paga).
RECEIPT_SOURCE_TYPES = ('FT', 'FA', 'FG', 'GF', 'ND')
# Recibo de facturas: RG «Recibo Geral», o único tipo com paymentReceipt (o RC é o recibo do regime de caixa do IVA).
RECEIPT_DOCUMENT_TYPE = 'RG'


class AccountPayment(models.Model):
    """Recibo (RG): emitido em cada recebimento de facturas (art. 6.º do DP n.º 71/25)."""

    _inherit = 'account.payment'

    l10n_ao_edi_required = fields.Boolean(compute='_compute_l10n_ao_edi_required')
    l10n_ao_edi_series_id = fields.Many2one('l10n_ao_edi.series', string='Série AGT', readonly=True, copy=False)
    l10n_ao_edi_document_no = fields.Char(string='N.º do recibo (AGT)', readonly=True, copy=False, index=True)
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
    l10n_ao_edi_rejected_document_no = fields.Char(string='Recibo rejeitado corrigido', readonly=True, copy=False)
    l10n_ao_edi_source_move_ids = fields.Many2many(
        'account.move',
        'l10n_ao_edi_payment_source_move_rel',
        'payment_id',
        'move_id',
        string='Documentos pagos (AGT)',
        readonly=True,
        copy=False,
        help='Facturas liquidadas por este recibo, fixadas na emissão.',
    )
    l10n_ao_edi_payload = fields.Text(string='Recibo AGT (JSON)', readonly=True, copy=False)
    l10n_ao_edi_print_count = fields.Integer(
        string='Impressões do documento AGT',
        readonly=True,
        copy=False,
        help='Cada PDF gerado conta como impressão: o primeiro é o «Original», os seguintes levam «2.ª via».',
    )
    l10n_ao_edi_document_ids = fields.Many2many(
        'l10n_ao_edi.document',
        'l10n_ao_edi_document_payment_rel',
        'payment_id',
        'document_id',
        string='Pedidos AGT',
        readonly=True,
        copy=False,
    )
    l10n_ao_edi_qr_url = fields.Char(compute='_compute_l10n_ao_edi_qr_url')

    @api.depends('company_id.l10n_ao_edi_enabled', 'payment_type', 'partner_type')
    def _compute_l10n_ao_edi_required(self):
        for payment in self:
            payment.l10n_ao_edi_required = (
                payment.company_id.l10n_ao_edi_enabled
                and payment.payment_type == 'inbound'
                and payment.partner_type == 'customer'
            )

    @api.depends('l10n_ao_edi_document_no', 'company_id.vat')
    def _compute_l10n_ao_edi_qr_url(self):
        for payment in self:
            if payment.l10n_ao_edi_document_no:
                emitter = payment.company_id.partner_id._l10n_ao_normalize_nif(payment.company_id.vat)
                number = quote(payment.l10n_ao_edi_document_no, safe='/')
                payment.l10n_ao_edi_qr_url = f'{AGT_QR_URL}?emissor={emitter}&document={number}'
            else:
                payment.l10n_ao_edi_qr_url = False

    def _l10n_ao_edi_copy_label(self):
        """Menção da impressão em curso (o contador já inclui a impressão que está a ser gerada)."""
        self.ensure_one()
        return 'Original' if self.l10n_ao_edi_print_count <= 1 else '2.ª via'

    def _l10n_ao_edi_number(self):
        self.ensure_one()
        return self.l10n_ao_edi_document_no

    # -------------------------------------------------------------------------
    # Documentos pagos
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_source_partials(self):
        """[(factura AGT, montante liquidado em Kz)] por este recebimento."""
        self.ensure_one()
        if not self.move_id:
            return []
        partials, _exchange_moves = self.move_id._get_reconciled_invoices_partials()
        amounts = {}
        for partial, _amount, invoice_line in partials:
            invoice = invoice_line.move_id
            if invoice.l10n_ao_edi_series_id and invoice.l10n_ao_document_type in RECEIPT_SOURCE_TYPES:
                amounts[invoice] = amounts.get(invoice, 0.0) + partial.amount
        return sorted(amounts.items(), key=lambda item: item[0].id)

    def _l10n_ao_edi_sources_sent(self):
        """Os documentos de origem já foram recebidos pela AGT (senão o recibo seria rejeitado: E14)."""
        self.ensure_one()
        sources = self.l10n_ao_edi_source_move_ids or self.env['account.move'].union(
            invoice for invoice, _amount in self._l10n_ao_edi_source_partials()
        )
        return bool(sources) and all(invoice.l10n_ao_edi_state in ('sent', 'valid') for invoice in sources)

    def _l10n_ao_edi_ready_to_send(self):
        return self._l10n_ao_edi_sources_sent()

    def _l10n_ao_edi_payload_values(self):
        self.ensure_one()
        return json.loads(self.l10n_ao_edi_payload) if self.l10n_ao_edi_payload else self._l10n_ao_edi_document_values()

    # -------------------------------------------------------------------------
    # Emissão do recibo
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_issue_receipt(self):
        issued = self.browse()
        for payment in self.filtered(
            lambda p: (
                p.l10n_ao_edi_required
                and (not p.l10n_ao_edi_document_no or p.l10n_ao_edi_state == 'invalid')
                and p.state not in ('draft', 'canceled', 'rejected')
            )
        ):
            partials = payment._l10n_ao_edi_source_partials()
            if not partials:
                continue
            company = payment.company_id
            company._l10n_ao_edi_check_configuration()
            company._l10n_ao_edi_check_communication_lock()
            series, number = self.env['l10n_ao_edi.series']._l10n_ao_edi_next_number(
                company, RECEIPT_DOCUMENT_TYPE, payment.date.year
            )
            payment.write(
                {
                    # Correcção de um recibo rejeitado: novo número, com referência ao rejeitado (documentStatus «C»).
                    'l10n_ao_edi_rejected_document_no': payment.l10n_ao_edi_document_no
                    if payment.l10n_ao_edi_state == 'invalid'
                    else False,
                    'l10n_ao_edi_series_id': series.id,
                    'l10n_ao_edi_document_no': f'{RECEIPT_DOCUMENT_TYPE} {series.code}/{number}',
                    'l10n_ao_edi_contingency': series.contingency,
                    'l10n_ao_edi_state': 'to_send',
                    'l10n_ao_edi_error': False,
                    'l10n_ao_edi_system_entry_date': fields.Datetime.now(),
                    'l10n_ao_edi_print_count': 0,
                    'l10n_ao_edi_source_move_ids': [fields.Command.set([invoice.id for invoice, _a in partials])],
                }
            )
            # O recibo fica fixado na emissão (facturas e montantes liquidados), mesmo que a reconciliação mude.
            payment.l10n_ao_edi_payload = json.dumps(payment._l10n_ao_edi_document_values(), ensure_ascii=False)
            issued |= payment
        if issued:
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_send').sudo()._trigger()
        return issued

    def action_l10n_ao_edi_issue_receipt(self):
        issued = self._l10n_ao_edi_issue_receipt()
        if not issued:
            raise UserError(
                self.env._('Não há facturas AGT liquidadas por este pagamento: reconcilie-o primeiro com as facturas.')
            )
        return True

    def action_l10n_ao_edi_send_now(self):
        self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._send_records(self)
        return True

    # -------------------------------------------------------------------------
    # Bloqueios
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_locked(self):
        return self.filtered(lambda p: p.l10n_ao_edi_state in EDI_LOCKED_STATES)

    def action_draft(self):
        if locked := self._l10n_ao_edi_locked():
            raise UserError(
                self.env._(
                    'O recibo %s já foi comunicado à AGT: o pagamento não pode voltar a rascunho.',
                    ', '.join(locked.mapped('l10n_ao_edi_document_no')),
                )
            )
        return super().action_draft()

    def action_cancel(self):
        if locked := self._l10n_ao_edi_locked():
            raise UserError(
                self.env._(
                    'O recibo %s já foi comunicado à AGT: o pagamento não pode ser cancelado.',
                    ', '.join(locked.mapped('l10n_ao_edi_document_no')),
                )
            )
        return super().action_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_l10n_ao_edi(self):
        if self.filtered('l10n_ao_edi_document_no'):
            raise UserError(self.env._('Não é possível apagar pagamentos com recibo AGT.'))

    # -------------------------------------------------------------------------
    # Estrutura de dados do recibo (Anexo I do DE n.º 683/25: paymentReceipt)
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_withholding_values(self):
        """Retenções/cativações sofridas neste recebimento (contas com tipo de retenção AGT)."""
        self.ensure_one()
        totals = {}
        for line in self.move_id.line_ids.filtered(lambda aml: aml.account_id.l10n_ao_withholding_type):
            withholding_type = line.account_id.l10n_ao_withholding_type
            totals[withholding_type] = totals.get(withholding_type, 0.0) + line.balance
        return [
            {
                'withholdingTaxType': withholding_type,
                'withholdingTaxDescription': dict(
                    self.env['account.account']._fields['l10n_ao_withholding_type'].selection
                )[withholding_type][:120],
                'withholdingTaxAmount': round(amount, 2),
            }
            for withholding_type, amount in totals.items()
            if round(amount, 2)
        ]

    def _l10n_ao_edi_previously_receipted(self, invoice):
        """Valor sem imposto já comunicado noutros recibos desta factura."""
        others = self.search(
            [
                ('l10n_ao_edi_source_move_ids', 'in', invoice.ids),
                ('l10n_ao_edi_state', 'in', EDI_LOCKED_STATES),
                ('id', '!=', self.id),
            ]
        )
        total = 0.0
        for other in others:
            for source in other._l10n_ao_edi_payload_values()['paymentReceipt']['sourceDocuments']:
                if source['sourceDocumentID']['OriginatingON'] == invoice.name:
                    total += source['creditAmount']
        return total

    def _l10n_ao_edi_document_values(self):
        self.ensure_one()
        company = self.company_id
        source_documents = []
        net_total = tax_total = 0.0
        for index, (invoice, applied) in enumerate(self._l10n_ao_edi_source_partials(), start=1):
            invoice_total = abs(invoice.amount_total_signed) or 1.0
            invoice_net = abs(invoice.amount_untaxed_signed)
            net = round(invoice_net * applied / invoice_total, 2)
            if invoice.currency_id.is_zero(invoice.amount_residual):
                # Último recibo da factura: o remanescente, para que a soma dos recibos não exceda a factura (E41).
                net = round(invoice_net - self._l10n_ao_edi_previously_receipted(invoice), 2)
            net_total += net
            tax_total += round(applied, 2) - net
            source_documents.append(
                {
                    'lineNo': index,
                    'sourceDocumentID': {
                        'OriginatingON': invoice.name,
                        'documentDate': fields.Date.to_string(invoice.invoice_date),
                    },
                    'creditAmount': net,
                }
            )
        totals = {
            'taxPayable': round(tax_total, 2),
            'netTotal': round(net_total, 2),
            'grossTotal': round(net_total + tax_total, 2),
        }
        partner = self.partner_id.commercial_partner_id
        customer_tax_id = partner._l10n_ao_edi_customer_tax_id()
        customer_country = partner.country_id.code or 'AO'
        company_name = (partner.name or '')[:200]
        document_date = fields.Date.to_string(self.date)
        signed = {
            'documentNo': self.l10n_ao_edi_document_no,
            'taxRegistrationNumber': company.partner_id._l10n_ao_normalize_nif(company.vat),
            'documentType': RECEIPT_DOCUMENT_TYPE,
            'documentDate': document_date,
            'customerTaxID': customer_tax_id,
            'customerCountry': customer_country,
            'companyName': company_name,
            'documentTotals': totals,
        }
        entry_date = fields.Datetime.context_timestamp(
            self.with_context(tz='Africa/Luanda'), self.l10n_ao_edi_system_entry_date or fields.Datetime.now()
        )
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
                'documentType': RECEIPT_DOCUMENT_TYPE,
            }
        )
        if company.l10n_ao_cae_id:
            values['eacCode'] = company.l10n_ao_cae_id.code
        values.update(
            {
                'systemEntryDate': entry_date.strftime('%Y-%m-%dT%H:%M:%S'),
                'customerTaxID': customer_tax_id,
                'customerCountry': customer_country,
                'companyName': company_name,
                'paymentReceipt': {'sourceDocuments': source_documents},
                'documentTotals': totals,
            }
        )
        if withholdings := self._l10n_ao_edi_withholding_values():
            values['withholdingTaxList'] = withholdings
        return values
