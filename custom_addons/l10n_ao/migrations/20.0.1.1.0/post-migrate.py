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
        journals = env['account.journal'].search([('company_id', '=', company.id), ('type', 'in', ('bank', 'cash'))])
        journals._l10n_ao_assign_outstanding_accounts('inbound')
        journals._l10n_ao_assign_outstanding_accounts('outbound')
