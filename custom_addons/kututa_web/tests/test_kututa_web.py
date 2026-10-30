from odoo.tests import HttpCase, TransactionCase, tagged

from .. import _kututa_login_terms


@tagged('post_install', '-at_install')
class TestKututaWeb(TransactionCase):
    def test_new_company_has_report_layout(self):
        # Com layout definido, a impressão sai logo em PDF em vez de abrir o assistente do Odoo.
        company = self.env['res.company'].create({'name': 'Escola Nova'})
        self.assertEqual(company.external_report_layout_id, self.env.ref('web.external_layout_standard'))

    def test_preview_action(self):
        report = self.env.ref('web.action_report_externalpreview', raise_if_not_found=False) or self.env[
            'ir.actions.report'
        ].search([], limit=1)
        # Pré-visualização na própria aplicação (HTML), não num separador novo.
        action = report.preview_action([1, 2])
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual((action['report_name'], action['report_type']), (report.report_name, 'qweb-html'))
        self.assertEqual(action['context']['active_ids'], [1, 2])

    def test_no_odoo_onboarding(self):
        # Nem tours de boas-vindas nem a conversa do OdooBot em inglês.
        user = self.env['res.users'].create({'name': 'Secretaria', 'login': 'secretaria_kw'})
        self.assertFalse(user.tour_enabled)
        self.assertFalse(user._init_odoobot())
        self.assertEqual(user.odoobot_state, 'disabled')


@tagged('post_install', '-at_install')
class TestKututaFavicon(HttpCase):
    def test_backend_favicon_is_not_odoo(self):
        # Sem favicon próprio no site (ou sem website), o separador mostra o ícone do Kututa ERP.
        response = self.url_open('/kututa_web/favicon')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.url.endswith('/kututa_web/static/img/favicon.png'))
        self.assertEqual(response.headers['Content-Type'], 'image/png')

    def test_webclient_uses_kututa_favicon(self):
        self.authenticate('admin', 'admin')
        html = self.url_open('/odoo').text
        self.assertIn('rel="shortcut icon" href="/kututa_web/favicon"', html)

    def test_pwa_manifest_is_kututa(self):
        manifest = self.url_open('/web/manifest.webmanifest').json()
        self.assertEqual(manifest['name'], 'Kututa ERP')
        self.assertEqual(manifest['theme_color'], '#13294B')
        self.assertTrue(all(i['src'].startswith('/kututa_web/static/img/') for i in manifest['icons']))
        self.assertIn('maskable', [i.get('purpose') for i in manifest['icons']])
        self.assertEqual(self.url_open(manifest['icons'][0]['src']).status_code, 200)


@tagged('post_install', '-at_install')
class TestKututaCores(TransactionCase):
    def test_brand_colors_in_primary_variables(self):
        # As cores da marca entram à cabeça das variáveis, antes das do Odoo (que são !default).
        paths = [p[0] for p in self.env['ir.asset']._get_asset_paths('web._assets_primary_variables', {})]
        marca = next(i for i, p in enumerate(paths) if p.endswith('kututa_web/static/scss/marca.scss'))
        odoo = next(i for i, p in enumerate(paths) if p.endswith('web/static/src/scss/primary_variables.scss'))
        self.assertLess(marca, odoo)


@tagged('post_install', '-at_install')
class TestKututaLoginTerms(TransactionCase):
    def test_login_in_angolan_portuguese(self):
        self.env['res.lang']._activate_lang('pt_AO')
        _kututa_login_terms(self.env)
        arch = self.env.ref('web.login').with_context(lang='pt_AO').arch_db
        self.assertIn('Palavra-passe', arch)
        self.assertIn('Escreva o seu e-mail', arch)
        self.assertNotIn('Senha', arch)
        self.assertNotIn('Digite seu e-mail', arch)
        # O inglês fica intacto.
        self.assertIn('Enter your email', self.env.ref('web.login').with_context(lang='en_US').arch_db)
