from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            *super()._load_pos_data_fields(config),
            'l10n_ao_edi_enabled',
            'l10n_ao_edi_software_validation_number',
        ]
