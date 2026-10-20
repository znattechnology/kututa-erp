"""20.0.1.2.0: contas de valores em trânsito também nos diários de caixa (retenções em recebimentos em numerário)."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env['res.company'].search([('chart_template', '=', 'ao')]):
        journals = env['account.journal'].search([('company_id', '=', company.id), ('type', 'in', ('bank', 'cash'))])
        journals._l10n_ao_assign_outstanding_accounts('inbound')
        journals._l10n_ao_assign_outstanding_accounts('outbound')
