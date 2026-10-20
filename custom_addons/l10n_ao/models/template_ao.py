from odoo import models
from odoo.addons.account.models.chart_template import template

# Prefixos com dois dígitos finais: o Odoo incrementa só o último grupo numérico, logo
# «43.1.00» permite 99 diários bancários (43.1.01 … 43.1.99); «43.1.0» permitiria 9.
BANK_PREFIX = '43.1.00'
BANK_FOREIGN_PREFIX = '43.2.00'
CASH_PREFIX = '45.1.00'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _l10n_ao_is_ao_template(self, company):
        return 'ao' in self._get_parent_template(company.chart_template)

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
                BANK_PREFIX: 'ao_43_1',
                BANK_FOREIGN_PREFIX: 'ao_43_2',
                CASH_PREFIX: 'ao_45_1',
            }.get(code_prefix)
        return super()._get_account_parent_xmlid(code_prefix, template_code)

    @template('ao', 'res.company')
    def _get_ao_res_company(self):
        return {
            self.env.company.id: {
                'account_fiscal_country_id': 'base.ao',
                # AGT: o imposto é calculado e arredondado linha a linha (taxContribution).
                'tax_calculation_rounding_method': 'round_per_line',
                'bank_account_code_prefix': BANK_PREFIX,
                'cash_account_code_prefix': CASH_PREFIX,
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
                # Por omissão, um produto é um serviço: proveito em 62 e custo em 75.2 (FST).
                # As mercadorias (61 / 21 / 26) configuram-se nas categorias de produtos.
                'income_account_id': 'ao_62_1_1',
                'expense_account_id': 'ao_75_2_39',
                'account_sale_tax_id': 'ao_iva_sale_14',
                'account_purchase_tax_id': 'ao_iva_purchase_14',
            },
        }

    def _create_outstanding_accounts(self, company, bank_prefix, code_digits):
        # PGC: os valores em trânsito ficam na conta 48 (Conta transitória), não nos depósitos à ordem.
        if not self._l10n_ao_is_ao_template(company):
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

    def _get_bank_fees_reco_account(self, company):
        # O Odoo procura uma conta chamada «Bank Fees»; sem ela cairia na primeira conta de custos (72.1).
        if self._l10n_ao_is_ao_template(company):
            return self.with_company(company).ref('ao_76_7')
        return super()._get_bank_fees_reco_account(company)
