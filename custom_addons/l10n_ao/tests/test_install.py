from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ao')
class TestL10nAoInstall(TransactionCase):

    def test_module_installed(self):
        module = self.env['ir.module.module'].search([('name', '=', 'l10n_ao')])
        self.assertEqual(module.state, 'installed')

    def test_angola_country_and_currency_exist(self):
        angola = self.env.ref('base.ao')
        self.assertEqual(angola.code, 'AO')
        self.assertEqual(self.env.ref('base.AOA').name, 'AOA')
