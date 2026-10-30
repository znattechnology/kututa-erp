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


# Ecrãs de entrada, registo e redefinição da palavra-passe: o pt.po do núcleo traz frases do Brasil.
# Por vista (chave) e termo de origem em inglês; o Odoo guarda-os por idioma no arch_db das vistas.
LOGIN_TERMS = {
    'web.login': {
        'Email': 'E-mail',
        'Enter your email': 'Escreva o seu e-mail',
        'Password': 'Palavra-passe',
        'Enter your password': 'Escreva a sua palavra-passe',
        'Log in': 'Entrar',
        'Login': 'Entrar',
        'Log in as superuser': 'Entrar como superutilizador',
    },
    'web.login_layout': {'Manage Databases': 'Gerir bases de dados'},
    'auth_signup.login': {
        "Don't have an account?": 'Ainda não tem conta?',
        'Reset Password': 'Redefinir palavra-passe',
    },
    'auth_signup.reset_password': {'Email': 'E-mail', 'Back to Login': 'Voltar à entrada'},
    'auth_signup.fields': {'Password': 'Palavra-passe', 'Confirm Password': 'Confirmar palavra-passe'},
    'auth_signup.signup': {'Already have an account?': 'Já tem conta?'},
    'auth_signup.login_successful': {'Registration successful.': 'Registo concluído.'},
}


def _kututa_login_terms(env):
    langs = [code for code, _name in env['res.lang'].get_installed() if code.startswith('pt')]
    for key, terms in LOGIN_TERMS.items():
        for view in env['ir.ui.view'].with_context(active_test=False).search([('key', '=', key)]):
            source = view.with_context(lang='en_US').arch_db or ''
            present = {src: dst for src, dst in terms.items() if f'>{src}<' in source or f'"{src}"' in source}
            if present:
                view.update_field_translations('arch_db', {lang: present for lang in langs})


def _post_init_hook(env):
    env['res.company'].search([('external_report_layout_id', '=', False)])._kututa_set_default_layout()
    _kututa_muk_colors(env)
    _kututa_login_terms(env)
