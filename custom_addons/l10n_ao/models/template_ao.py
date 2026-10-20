from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('ao')
    def _get_ao_template_data(self):
        return {
            'name': 'Angola - Plano Geral de Contabilidade (Decreto n.º 82/01)',
            # Os códigos do PGC são pontuados e de comprimento variável: não completar com zeros.
            'code_digits': '1',
        }

    def _get_account_parent_xmlid(self, code_prefix, template_code):
        if template_code == 'ao':
            return {
                '43.1.0': 'ao_43_1',
                '45.1.0': 'ao_45_1',
            }.get(code_prefix)
        return super()._get_account_parent_xmlid(code_prefix, template_code)

    @template('ao', 'res.company')
    def _get_ao_res_company(self):
        return {
            self.env.company.id: {
                'account_fiscal_country_id': 'base.ao',
                'currency_id': 'base.AOA',
                'bank_account_code_prefix': '43.1.0',
                'cash_account_code_prefix': '45.1.0',
                'transfer_account_code_prefix': '48.4',
                'transfer_account_id': 'ao_48_4',
                'account_journal_suspense_account_id': 'ao_48_3',
                'default_cash_difference_income_account_id': 'ao_68_11_9',
                'default_cash_difference_expense_account_id': 'ao_78_11_9',
                'account_default_pos_receivable_account_id': 'ao_31_1_2_9',
                'income_currency_exchange_account_id': 'ao_66_2_1',
                'expense_currency_exchange_account_id': 'ao_76_2_1',
                'account_journal_early_pay_discount_gain_account_id': 'ao_66_3',
                'account_journal_early_pay_discount_loss_account_id': 'ao_76_3',
                'receivable_account_id': 'ao_31_1_2_1',
                'payable_account_id': 'ao_32_1_2_1',
                'income_account_id': 'ao_61_3_1',
                'expense_account_id': 'ao_21_2',
                'account_sale_tax_id': 'ao_iva_sale_14',
                'account_purchase_tax_id': 'ao_iva_purchase_14',
            },
        }

    def _create_outstanding_accounts(self, company, bank_prefix, code_digits):
        # PGC: os valores em trânsito ficam na conta 48 (Conta transitória), não nos depósitos à ordem.
        if company.chart_template != 'ao':
            return super()._create_outstanding_accounts(company, bank_prefix, code_digits)
        self.env['ir.model.data']._update_xmlids(
            [
                {
                    'xml_id': self.company_xmlid(xml_id, company),
                    'record': self.ref(account_xmlid),
                    'noupdate': True,
                }
                for xml_id, account_xmlid in (
                    ('account_journal_payment_debit_account_id', 'ao_48_1'),
                    ('account_journal_payment_credit_account_id', 'ao_48_2'),
                )
            ]
        )
        return None
