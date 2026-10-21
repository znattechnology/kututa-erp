from . import models, tools


def _post_init_hook(env):
    companies = env['res.company'].search([('partner_id.country_id', '=', env.ref('base.ao').id)])
    companies._l10n_ao_hr_generate_public_holidays()
