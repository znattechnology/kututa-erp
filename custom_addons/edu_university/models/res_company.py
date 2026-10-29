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

    edu_pedagogical_title = fields.Char(
        string='Cargo do(a) responsável académico(a)',
        help='Assina com o reitor os documentos do ensino superior (por exemplo «Vice-Reitora para os Assuntos '
        'Académicos»).',
    )
    edu_name_of = fields.Char(string='Nome com a preposição', compute='_compute_edu_name_of')

    @api.depends('name')
    def _compute_edu_name_of(self):
        """«do Instituto Superior Kianda», «da Universidade …»: o nome como se escreve nos documentos."""
        feminine = ('universidade', 'escola', 'academia', 'faculdade')
        for company in self:
            first = (company.name or '').split(' ')[0].casefold()
            company.edu_name_of = f'{"da" if first in feminine else "do"} {company.name or ""}'

    @api.onchange('edu_school_type')
    def _onchange_edu_school_type_higher(self):
        if self.edu_school_type == 'higher':
            self.edu_director_title = self.edu_director_title or 'Reitor'
            self.edu_pedagogical_title = self.edu_pedagogical_title or 'Vice-Reitor para os Assuntos Académicos'

    @api.depends('edu_is_school', 'edu_school_type')
    def _compute_edu_is_higher(self):
        for company in self:
            company.edu_is_higher = company.edu_is_school and company.edu_school_type == 'higher'
