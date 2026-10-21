from odoo.tests import TransactionCase, tagged


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
        action = report.preview_action([1, 2])
        self.assertEqual(action, {
            'type': 'ir.actions.act_url', 'url': f'/report/pdf/{report.report_name}/1,2', 'target': 'new',
        })  # fmt: skip

    def test_no_odoo_onboarding(self):
        # Nem tours de boas-vindas nem a conversa do OdooBot em inglês.
        user = self.env['res.users'].create({'name': 'Secretaria', 'login': 'secretaria_kw'})
        self.assertFalse(user.tour_enabled)
        self.assertFalse(user._init_odoobot())
        self.assertEqual(user.odoobot_state, 'disabled')
