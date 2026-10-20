from odoo import api, fields, models
from odoo.tools import html2plaintext


class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_ao_edi_legal_note = fields.Char(
        string='Menção legal (talão)',
        compute='_compute_l10n_ao_edi_legal_note',
        help='Motivo de isenção ou não sujeição a imprimir no talão (DP n.º 71/25).',
    )

    @api.depends('invoice_legal_notes')
    def _compute_l10n_ao_edi_legal_note(self):
        for tax in self:
            tax.l10n_ao_edi_legal_note = html2plaintext(tax.invoice_legal_notes or '').strip() or False

    @api.model
    def _load_pos_data_fields(self, config):
        return [*super()._load_pos_data_fields(config), 'l10n_ao_edi_legal_note']
