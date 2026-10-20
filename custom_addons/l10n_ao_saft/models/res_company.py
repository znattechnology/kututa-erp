from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ao_saft_producer_tax_id = fields.Char(
        string='NIF do produtor do software',
        help='SAF-T (AO): ProductCompanyTaxID, o NIF da entidade que produz o software (Kututa ERP).',
    )
    l10n_ao_saft_producer_name = fields.Char(
        string='Produtor do software',
        default='Kututa ERP',
        help='SAF-T (AO): segunda parte do ProductID («aplicação/produtor»).',
    )
