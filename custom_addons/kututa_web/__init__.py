from . import controllers, models


def _post_init_hook(env):
    env['res.company'].search([('external_report_layout_id', '=', False)])._kututa_set_default_layout()
