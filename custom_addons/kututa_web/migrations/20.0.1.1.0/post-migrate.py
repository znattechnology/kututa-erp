from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['res.company'].search([('external_report_layout_id', '=', False)])._kututa_set_default_layout()
