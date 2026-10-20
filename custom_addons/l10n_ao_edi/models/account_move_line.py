from odoo import api, fields, models

from .product_template import AGT_OPERATION_TYPES


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_ao_operation_type = fields.Selection(
        AGT_OPERATION_TYPES,
        string='Tipo de operação (AGT)',
        compute='_compute_l10n_ao_operation_type',
        store=True,
        readonly=False,
    )

    @api.depends('product_id')
    def _compute_l10n_ao_operation_type(self):
        for line in self:
            product = line.product_id
            if product.l10n_ao_operation_type:
                line.l10n_ao_operation_type = product.l10n_ao_operation_type
            elif product and product.type != 'service':
                line.l10n_ao_operation_type = 'TB'
            elif not line.l10n_ao_operation_type:
                line.l10n_ao_operation_type = 'SG'
