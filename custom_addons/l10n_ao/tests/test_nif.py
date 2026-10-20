from odoo.exceptions import ValidationError
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
        self.assertFalse(partner._l10n_ao_is_valid_nif('50001234567'))  # 11 dígitos
        self.assertFalse(partner._l10n_ao_is_valid_nif('004567890L0042'))  # BI mal formado
        self.assertFalse(partner._l10n_ao_is_valid_nif(''))

    def test_nif_validation_is_wired_to_partner(self):
        """O módulo base chama check_vat_ao / format_vat_ao ao gravar o NIF de um parceiro angolano."""
        angola = self.env.ref('base.ao')
        partner = self.env['res.partner'].create({'name': 'OK', 'country_id': angola.id, 'vat': 'AO 5000-123-456'})
        self.assertEqual(partner.vat, '5000123456')
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({'name': 'KO', 'country_id': angola.id, 'vat': '12345'})
