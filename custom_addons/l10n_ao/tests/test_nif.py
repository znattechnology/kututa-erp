from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ao')
class TestL10nAoNif(TransactionCase):
    def test_nif_formats(self):
        partner = self.env['res.partner']
        self.assertTrue(partner._l10n_ao_is_valid_nif('5000123456'))  # pessoa colectiva
        self.assertTrue(partner._l10n_ao_is_valid_nif('004567890LA042'))  # BI
        self.assertTrue(partner._l10n_ao_is_valid_nif('AO 5000-123-456'))  # normalização
        self.assertTrue(partner._l10n_ao_is_valid_nif('999999999'))  # consumidor final
        self.assertFalse(partner._l10n_ao_is_valid_nif('12345'))
        self.assertFalse(partner._l10n_ao_is_valid_nif(''))
