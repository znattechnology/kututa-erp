from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ao_asset_category_id = fields.Many2one(
        'l10n_ao_asset.category',
        string='Categoria de imobilizado',
        company_dependent=True,
        help='Categoria da ficha criada ao lançar uma factura de fornecedor com este artigo, quando a conta '
        'é partilhada por várias categorias.',
    )
