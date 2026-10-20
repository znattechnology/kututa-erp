"""20.0.1.3.0: conta de existências (26.1) e custo médio por omissão nas empresas AO já criadas."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env['res.company'].search([('chart_template', '=', 'ao'), ('parent_id', '=', False)]):
        template = env['account.chart.template'].with_company(company)
        chart_data = template._get_chart_template_data('ao')
        template._load_data({'account.account': {'ao_26_1': chart_data['account.account']['ao_26_1']}})
        account = template.ref('ao_26_1', raise_if_not_found=False)
        if account and not company.account_stock_valuation_id:
            company.account_stock_valuation_id = account
        has_stock = 'stock.move' in env and env['stock.move'].sudo().search_count(
            [('company_id', '=', company.id)], limit=1
        )
        if not has_stock:
            company.cost_method = 'average'
