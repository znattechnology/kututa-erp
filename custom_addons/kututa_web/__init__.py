from . import controllers, models

# Paleta Kututa para o muk_web_colors (claro e escuro); só substitui as cores de origem do MuK
# ou o verde-azulado da primeira versão da marca, nunca cores escolhidas por uma escola.
KUTUTA_MUK = {
    'light': {
        'color_brand': '#13294B',
        'color_primary': '#1F5FA8',
        'color_success': '#1C7F57',
        'color_info': '#2B78C5',
        'color_warning': '#D9A400',
        'color_danger': '#C2333F',
    },
    'dark': {
        'color_brand': '#1B375F',
        'color_primary': '#5B95D6',
        'color_success': '#3FBF86',
        'color_info': '#7DB3EC',
        'color_warning': '#F0C24B',
        'color_danger': '#F2666F',
    },
}
CORES_A_SUBSTITUIR = {'#243742', '#082f38'}


def _kututa_muk_colors(env):
    if 'muk_web_colors.color_assets_editor' not in env:
        return
    editor = env['muk_web_colors.color_assets_editor']
    for palette, (url, bundle, names) in env['res.config.settings'].COLOR_ASSETS.items():
        brand = editor.read_colors(url, bundle, names).get('color_brand') or ''
        if brand.lower() in CORES_A_SUBSTITUIR:
            editor.write_colors(url, bundle, {n: KUTUTA_MUK[palette][n] for n in names})


def _post_init_hook(env):
    env['res.company'].search([('external_report_layout_id', '=', False)])._kututa_set_default_layout()
    _kututa_muk_colors(env)
