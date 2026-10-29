from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    edu_school_type = fields.Selection(
        selection_add=[('higher', 'Ensino superior')], ondelete={'higher': 'set default'}
    )
    edu_is_higher = fields.Boolean(string='Instituição de ensino superior', compute='_compute_edu_is_higher')
    edu_mescti_code = fields.Char(
        string='N.º de registo no MESCTI',
        help='Registo da instituição no Ministério do Ensino Superior, Ciência, Tecnologia e Inovação.',
    )

    @api.depends('edu_is_school', 'edu_school_type')
    def _compute_edu_is_higher(self):
        for company in self:
            company.edu_is_higher = company.edu_is_school and company.edu_school_type == 'higher'
