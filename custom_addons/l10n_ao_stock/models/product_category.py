from odoo import fields, models

# Tipo de produto do SAF-T de inventário (Circular n.º 05/GACA/GJ/DSF/AGT/2026), pela conta de existências do PGC.
PRODUCT_TYPES = [
    ('M', 'Mercadorias'),
    ('P', 'Matérias-primas, subsidiárias e de consumo'),
    ('A', 'Produtos acabados e intermédios'),
    ('S', 'Subprodutos, desperdícios e refugos'),
    ('T', 'Produtos e trabalhos em curso'),
    ('B', 'Activos biológicos'),
]
TYPE_BY_ACCOUNT = {'22': 'P', '23': 'T', '24': 'A', '25': 'S', '26': 'M'}


class ProductCategory(models.Model):
    _inherit = 'product.category'

    l10n_ao_stock_product_type = fields.Selection(
        PRODUCT_TYPES,
        string='Tipo de produto (inventário AGT)',
        help='Se vazio, deduz-se da conta de existências do PGC (22, 23, 24, 25 ou 26); por omissão, Mercadorias.',
    )

    def _l10n_ao_stock_product_type(self, company):
        self.ensure_one()
        if self.l10n_ao_stock_product_type:
            return self.l10n_ao_stock_product_type
        category = self.with_company(company)
        account = category.property_stock_valuation_account_id or company.account_stock_valuation_id
        return TYPE_BY_ACCOUNT.get((account.code or '')[:2], 'M')
