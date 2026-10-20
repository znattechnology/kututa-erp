from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao')
class TestL10nAoChart(AccountTestInvoicingCommon):
    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()

    def _account(self, code):
        return (
            self.env['account.account']
            .with_context(active_test=False)
            .search(
                [
                    *self.env['account.account']._check_company_domain(self.company_data['company']),
                    ('code', '=', code),
                ]
            )
        )

    def test_company_setup(self):
        company = self.company_data['company']
        self.assertEqual(company.chart_template, 'ao')
        self.assertEqual(company.currency_id, self.env.ref('base.AOA'))
        self.assertEqual(company.account_fiscal_country_id, self.env.ref('base.ao'))

    def test_pgc_codes_are_kept(self):
        """Os códigos pontuados do PGC não podem ser completados com zeros."""
        self.assertEqual(self._account('31.1.2.1').account_type, 'asset_receivable')
        self.assertEqual(self._account('32.1.2.1').account_type, 'liability_payable')
        self.assertEqual(self._account('34.2.2').name, 'IVA liquidado')
        self.assertFalse(self._account('31.1.2').active, 'Uma conta com subcontas é agregadora (inactiva).')
        self.assertEqual(self._account('31.1.2.1').parent_id, self._account('31.1.2'))

    def test_bank_and_cash_accounts_follow_pgc(self):
        company = self.company_data['company']
        journals = self.env['account.journal'].search(
            [
                ('company_id', '=', company.id),
                ('type', 'in', ('bank', 'cash')),
            ]
        )
        for journal in journals:
            prefix = '43.1.' if journal.type == 'bank' else '45.1.'
            self.assertTrue(journal.default_account_id.code.startswith(prefix), journal.default_account_id.code)
            self.assertEqual(journal.default_account_id.parent_id.code, prefix[:-1])
        self.assertEqual(company.transfer_account_id.code, '48.4')
        self.assertEqual(company.default_cash_difference_income_account_id.code, '68.11.9')
        self.assertEqual(company.default_cash_difference_expense_account_id.code, '78.11.9')
        self.assertEqual(company.income_currency_exchange_account_id.code, '66.2.1')
        self.assertEqual(company.account_default_pos_receivable_account_id.code, '31.1.2.9')
        self.assertEqual(company.account_journal_suspense_account_id.code, '48.3')

    def test_invoice_with_vat_14(self):
        invoice = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_a.id,
                'invoice_line_ids': [
                    Command.create(
                        {
                            'name': 'Serviço',
                            'quantity': 1,
                            'price_unit': 1000.0,
                            'tax_ids': [
                                Command.set(
                                    self.env.ref(f'account.{self.company_data["company"].id}_ao_iva_sale_14').ids
                                )
                            ],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        self.assertAlmostEqual(invoice.amount_tax, 140.0)
        tax_line = invoice.line_ids.filtered('tax_line_id')
        self.assertEqual(tax_line.account_id.code, '34.2.2')
        self.assertEqual(
            invoice.line_ids.filtered(lambda line: line.display_type == 'payment_term').account_id.code, '31.1.2.1'
        )

    def test_exempt_tax_carries_agt_reason(self):
        tax = self.env.ref(f'account.{self.company_data["company"].id}_ao_iva_sale_ise_m21')
        self.assertEqual(tax.l10n_ao_tax_code, 'ISE')
        self.assertEqual(tax.l10n_ao_exemption_id.code, 'M21')
        self.assertEqual(tax.amount, 0.0)

    def test_agt_master_data_loaded(self):
        self.assertEqual(self.env['l10n_ao.tax.exemption'].search_count([('tax_type', '=', 'IVA')]), 38)
        self.assertEqual(self.env['l10n_ao.tax.exemption'].search_count([('tax_type', '=', 'IS')]), 3)
        self.assertEqual(self.env['l10n_ao.tax.exemption'].search_count([('tax_type', '=', 'IEC')]), 16)
        self.assertEqual(self.env['l10n_ao.cae'].search_count([]), 574)
        self.assertTrue(self.env.ref('base.AOA').active)

    def test_decree_errata_are_corrected(self):
        """Lapsos de impressão do Decreto 82/01 (tools/data/pgc_correcoes.csv)."""
        self.assertEqual(self._account('18.2').name, 'Imobilizações incorpóreas')
        self.assertEqual(self._account('18.3').name, 'Investimentos financeiros em imóveis')
        self.assertEqual(self._account('18.1.4').parent_id.code, '18.1')
        self.assertFalse(self._account('18.4'), 'As subcontas de 18.1 não podem colidir com os cabeçalhos 18.x')
        self.assertEqual(self._account('56.2.2').name, 'Realização')
        self.assertEqual(self._account('76.6.1.4').name, 'Fundos')
        self.assertEqual(self._account('38.1.3.2').parent_id.code, '38.1.3')
        self.assertEqual(self._account('31.1').name, 'Clientes – correntes')

    def test_second_angolan_company(self):
        """Cada empresa recebe o seu próprio plano, diários e contas de valores em trânsito."""
        company = self.env['res.company'].create({'name': 'Segunda AO', 'country_id': self.env.ref('base.ao').id})
        self.env['account.chart.template'].with_company(company).try_loading('ao', company=company, install_demo=False)
        env = self.env(context=dict(self.env.context, allowed_company_ids=company.ids))
        self.assertEqual(company.chart_template, 'ao')
        self.assertEqual(company.currency_id.name, 'AOA')
        bank = env['account.journal'].search([('company_id', '=', company.id), ('type', '=', 'bank')], limit=1)
        self.assertEqual(bank.default_account_id.with_company(company).code, '43.1.01')
        chart = env['account.chart.template'].with_company(company)
        outstanding = chart.ref('account_journal_payment_debit_account_id')
        self.assertEqual(outstanding.with_company(company).code, '48.1')
        self.assertEqual(outstanding.company_ids, company)
