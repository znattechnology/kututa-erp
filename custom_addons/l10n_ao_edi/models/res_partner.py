from odoo import models

FINAL_CONSUMER_NIF = '999999999'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _l10n_ao_edi_customer_tax_id(self):
        """customerTaxID: NIF angolano válido, identificação estrangeira, ou consumidor final (999999999)."""
        self.ensure_one()
        if self.country_id and self.country_id.code != 'AO':
            return (self.vat or FINAL_CONSUMER_NIF)[:50]
        nif = self._l10n_ao_normalize_nif(self.vat)
        return nif if nif and self._l10n_ao_is_valid_nif(nif) else FINAL_CONSUMER_NIF
