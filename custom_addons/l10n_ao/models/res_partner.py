import re

from odoo import api, models

# NIF de pessoa colectiva: 10 dígitos. Pessoa singular: n.º do BI (9 dígitos, 2 letras, 3 dígitos).
AO_NIF_RE = re.compile(r'^(\d{10}|\d{9}[A-Z]{2}\d{3})$')
# Consumidor final sem NIF (DE n.º 683/25, customerTaxID).
AO_FINAL_CONSUMER_NIF = '999999999'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _l10n_ao_normalize_nif(self, vat):
        return re.sub(r'[\s.\-]', '', vat or '').upper().removeprefix('AO')

    @api.model
    def _l10n_ao_is_valid_nif(self, vat):
        nif = self._l10n_ao_normalize_nif(vat)
        return nif == AO_FINAL_CONSUMER_NIF or bool(AO_NIF_RE.match(nif))

    # Gancho de validação do NIF do módulo base (res.partner._run_vat_checks → check_vat_<país>).
    def check_vat_ao(self, vat):
        return self._l10n_ao_is_valid_nif(vat)

    # Gancho de formatação do módulo base (res.partner._format_vat_number → format_vat_<país>).
    def format_vat_ao(self, vat):
        return self._l10n_ao_normalize_nif(vat)
