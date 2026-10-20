"""20.0.1.1.0: contas de retenção sofrida com o tipo AGT, e métodos de pagamento com contas de valores em trânsito.

A actualização do módulo não altera contas já criadas a partir do template (política do Odoo).
"""

from odoo import SUPERUSER_ID, api

WITHHOLDING_TYPES = {'34.1.2': 'II', '34.2.4': 'IVA'}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env['res.company'].search([('chart_template', '=', 'ao')]):
        Account = env['account.account'].with_company(company)
        for code, withholding_type in WITHHOLDING_TYPES.items():
            account = Account.search([*Account._check_company_domain(company), ('code', '=', code)], limit=1)
            if account and not account.l10n_ao_withholding_type:
                account.l10n_ao_withholding_type = withholding_type
        banks = company.bank_journal_ids
        banks._assign_outstanding_account_to_payment_method_lines('inbound', chart_template='ao')
        banks._assign_outstanding_account_to_payment_method_lines('outbound', chart_template='ao')
