from odoo.exceptions import UserError
from odoo.tools import config

VIMEO_NIF = '5003603490'


def pre_init_hook(env):
    """Recusa a instalação fora do CRM interno da Vímeo (as bases dos clientes não têm este módulo)."""
    if config['test_enable'] and not env.context.get('kututa_prospect_testar_guarda'):
        return  # bases de teste novas não têm empresa com NIF; o teste da guarda chama esta função directamente
    if not env['res.company'].sudo().search_count([('vat', '=', VIMEO_NIF)]):
        raise UserError(
            env._(
                'O módulo de prospecção só se instala no Odoo interno da Vímeo (NIF %s). Esta base é de um cliente.',
                VIMEO_NIF,
            )
        )
