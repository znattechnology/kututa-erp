from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao')
class TestL10nAoTaxes(AccountTestInvoicingCommon):
    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.partner_ao = cls.env['res.partner'].create(
            {'name': 'Cliente AO', 'country_id': cls.env.ref('base.ao').id, 'vat': '5000000002'}
        )
        cls.partner_pt = cls.env['res.partner'].create({'name': 'Cliente PT', 'country_id': cls.env.ref('base.pt').id})

    def _tax(self, xmlid):
        return self.env.ref(f'account.{self.company.id}_{xmlid}')

    def _fpos(self, xmlid):
        return self.env.ref(f'account.{self.company.id}_{xmlid}')

    def _invoice(self, move_type, partner, taxes, *, price=1000.0, fiscal_position=None, post=True):
        vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': '2026-10-20',
            'invoice_line_ids': [
                Command.create(
                    {'name': 'Linha', 'quantity': 1, 'price_unit': price, 'tax_ids': [Command.set(taxes.ids)]}
                )
            ],
        }
        if fiscal_position:
            vals['fiscal_position_id'] = fiscal_position.id
        move = self.env['account.move'].create(vals)
        if post:
            move.action_post()
        return move

    def _tax_lines(self, move):
        return {line.account_id.code: line.balance for line in move.line_ids.filtered('tax_line_id')}

    def test_credit_note_reverses_vat_on_same_account(self):
        invoice = self._invoice('out_invoice', self.partner_ao, self._tax('ao_iva_sale_14'))
        refund = invoice._reverse_moves([{'invoice_date': invoice.invoice_date}], cancel=False)
        refund.action_post()
        self.assertEqual(self._tax_lines(invoice), {'34.2.2': -140.0})
        self.assertEqual(self._tax_lines(refund), {'34.2.2': 140.0})
        tag = refund.line_ids.filtered('tax_line_id').tax_tag_ids
        # As etiquetas não têm sinal: a nota de crédito anula a factura no relatório pelo saldo das linhas.
        self.assertEqual(tag.mapped('name'), ['IL14'])
        tagged_lines = (invoice + refund).line_ids.filtered(lambda line: tag in line.tax_tag_ids)
        self.assertEqual(sum(tagged_lines.mapped('balance')), 0.0)

    def test_vendor_bill_deductible_vat(self):
        bill = self._invoice('in_invoice', self.partner_ao, self._tax('ao_iva_purchase_14'), price=500.0)
        self.assertEqual(self._tax_lines(bill), {'34.2.3': 70.0})
        expense = bill.invoice_line_ids.account_id
        self.assertEqual(expense.code, '75.2.39', 'Sem conta no produto, a factura de fornecedor vai a FST')
        self.assertEqual(expense.account_type, 'expense')
        self.assertEqual(
            bill.line_ids.filtered(lambda line: line.display_type == 'payment_term').account_id.code, '32.1.2.1'
        )

    def test_non_deductible_vat_is_a_cost(self):
        bill = self._invoice('in_invoice', self.partner_ao, self._tax('ao_iva_purchase_14_nd'), price=500.0)
        self.assertEqual(bill.amount_total, 570.0)
        tax_line = bill.line_ids.filtered('tax_line_id')
        self.assertEqual(tax_line.account_id.code, '75.2.39', 'O IVA não dedutível vai para a conta de custo da linha')

    def test_reverse_charge_nets_to_zero(self):
        bill = self._invoice('in_invoice', self.partner_pt, self._tax('ao_iva_purchase_14_rc'))
        self.assertEqual(bill.amount_total, 1000.0)
        self.assertEqual(self._tax_lines(bill), {'34.2.3': 140.0, '34.2.2': -140.0})

    def _product_invoice(self, move_type, partner, product, fiscal_position=None):
        """Factura com imposto vindo do produto: é aqui que a posição fiscal faz o mapeamento."""
        vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': '2026-10-20',
            'invoice_line_ids': [Command.create({'product_id': product.id, 'quantity': 1, 'price_unit': 100})],
        }
        if fiscal_position:
            vals['fiscal_position_id'] = fiscal_position.id
        return self.env['account.move'].create(vals)

    def test_fiscal_positions_keep_universal_taxes(self):
        """Uma posição fiscal substitui o que mapeia e mantém o resto (não pode apagar impostos das linhas)."""
        Product = self.env['product.product']
        service = Product.create({'name': 'Serviço', 'taxes_id': [Command.set(self._tax('ao_iva_sale_14').ids)]})
        tuition = Product.create({'name': 'Propina', 'taxes_id': [Command.set(self._tax('ao_iva_sale_ise_m21').ids)]})
        supply = Product.create(
            {'name': 'Compra', 'supplier_taxes_id': [Command.set(self._tax('ao_iva_purchase_7').ids)]}
        )

        export = self._product_invoice('out_invoice', self.partner_pt, service)
        self.assertEqual(export.fiscal_position_id, self._fpos('ao_fp_export'))
        self.assertEqual(export.invoice_line_ids.tax_ids.mapped('name'), ['IVA Isento M30 (Exportação de bens)'])

        domestic = self._product_invoice('out_invoice', self.partner_ao, service)
        self.assertEqual(domestic.fiscal_position_id, self._fpos('ao_fp_domestic'))
        self.assertEqual(domestic.invoice_line_ids.tax_ids.mapped('name'), ['IVA 14%'])

        for fpos in ('ao_fp_cabinda', 'ao_fp_export'):
            move = self._product_invoice('out_invoice', self.partner_ao, tuition, fiscal_position=self._fpos(fpos))
            self.assertEqual(move.invoice_line_ids.tax_ids.mapped('name'), ['IVA Isento M21 (Ensino)'], fpos)
        bill = self._product_invoice('in_invoice', self.partner_pt, supply, fiscal_position=self._fpos('ao_fp_export'))
        self.assertEqual(bill.invoice_line_ids.tax_ids.mapped('name'), ['IVA 7% dedutível'])

        cabinda = self._product_invoice(
            'out_invoice', self.partner_ao, service, fiscal_position=self._fpos('ao_fp_cabinda')
        )
        self.assertEqual(cabinda.invoice_line_ids.tax_ids.mapped('name'), ['IVA 1% Cabinda'])
        self.assertEqual(cabinda.amount_tax, 1.0)

    def test_exempt_taxes_carry_legal_mention(self):
        tax = self._tax('ao_iva_sale_ise_m21')
        self.assertIn('alínea l) do nº1 do artigo 12.º do CIVA', tax.invoice_legal_notes)

    def test_agt_constraints(self):
        Tax = self.env['account.tax']
        base = {
            'amount': 0.0,
            'type_tax_use': 'sale',
            'country_id': self.env.ref('base.ao').id,
            'tax_group_id': self._tax('tax_group_iva_isento').id,
        }
        m21 = self.env.ref('l10n_ao.exemption_m21').id
        s01 = self.env.ref('l10n_ao.exemption_s01').id
        with self.assertRaises(ValidationError, msg='ISE sem motivo'):
            Tax.create({**base, 'name': 'A', 'l10n_ao_tax_type': 'IVA', 'l10n_ao_tax_code': 'ISE'})
        with self.assertRaises(ValidationError, msg='ISE com taxa diferente de 0'):
            Tax.create(
                {
                    **base,
                    'name': 'B',
                    'amount': 14.0,
                    'l10n_ao_tax_type': 'IVA',
                    'l10n_ao_tax_code': 'ISE',
                    'l10n_ao_exemption_id': m21,
                }
            )
        with self.assertRaises(ValidationError, msg='NOR com motivo de isenção'):
            Tax.create(
                {
                    **base,
                    'name': 'C',
                    'amount': 14.0,
                    'l10n_ao_tax_type': 'IVA',
                    'l10n_ao_tax_code': 'NOR',
                    'l10n_ao_exemption_id': m21,
                }
            )
        with self.assertRaises(ValidationError, msg='IVA sem código'):
            Tax.create({**base, 'name': 'D', 'amount': 14.0, 'l10n_ao_tax_type': 'IVA'})
        with self.assertRaises(ValidationError, msg='NS com código'):
            Tax.create(
                {**base, 'name': 'E', 'l10n_ao_tax_type': 'NS', 'l10n_ao_tax_code': 'ISE', 'l10n_ao_exemption_id': m21}
            )
        with self.assertRaises(ValidationError, msg='motivo de IS num imposto de IVA'):
            Tax.create(
                {**base, 'name': 'F', 'l10n_ao_tax_type': 'IVA', 'l10n_ao_tax_code': 'ISE', 'l10n_ao_exemption_id': s01}
            )
        ok = Tax.create(
            {**base, 'name': 'G', 'l10n_ao_tax_type': 'IS', 'l10n_ao_tax_code': 'ISE', 'l10n_ao_exemption_id': s01}
        )
        self.assertEqual(ok.l10n_ao_tax_region, 'AO')
        foreign = Tax.create(
            {
                'name': 'H',
                'amount': 23.0,
                'type_tax_use': 'sale',
                'country_id': self.env.ref('base.pt').id,
                'tax_group_id': self.env['account.tax.group']
                .create({'name': 'IVA PT', 'country_id': self.env.ref('base.pt').id})
                .id,
            }
        )
        self.assertFalse(foreign.l10n_ao_tax_region, 'Os campos AGT não se aplicam a impostos de outros países')

    def test_bank_fees_model_uses_bank_services_account(self):
        model = self.env['account.reconcile.model'].search(
            [('company_id', '=', self.company.id), ('name', 'ilike', 'Bank Fees')], limit=1
        )
        self.assertTrue(model)
        self.assertEqual(model.line_ids.account_id.code, '76.7')

    def test_many_bank_journals_and_foreign_currency(self):
        usd = self.env.ref('base.USD')
        usd.active = True
        codes = []
        for i in range(10):
            journal = self.env['account.journal'].create(
                {'name': f'Banco {i}', 'type': 'bank', 'company_id': self.company.id}
            )
            codes.append(journal.default_account_id.code)
        self.assertTrue(all(code.startswith('43.1.') and len(code) == 7 for code in codes), codes)
        self.assertEqual(len(set(codes)), 10)
        foreign = self.env['account.journal'].create(
            {'name': 'Banco USD', 'type': 'bank', 'company_id': self.company.id, 'currency_id': usd.id}
        )
        self.assertTrue(foreign.default_account_id.code.startswith('43.2.'), foreign.default_account_id.code)
        self.assertEqual(foreign.default_account_id.parent_id.code, '43.2')
        cash = self.env['account.journal'].create({'name': 'Caixa 2', 'type': 'cash', 'company_id': self.company.id})
        self.assertTrue(cash.default_account_id.code.startswith('45.1.'), cash.default_account_id.code)
