from . import models, wizard


def _post_init_hook(env):
    companies = env['res.company'].search([('chart_template', '=', 'ao')])
    companies._l10n_ao_asset_create_default_categories()
