from odoo.tests import HttpCase, TransactionCase, tagged


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
