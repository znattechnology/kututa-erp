from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Normas Curriculares Gerais (DP 193/18): unidades curriculares obrigatórias, optativas e transversais, semestrais.
UC_TYPES = [
    ('compulsory', 'Obrigatória'),
    ('optional', 'Optativa'),
    ('transversal', 'Transversal'),
]
SEMESTERS = [
    ('1', '1.º semestre'),
    ('2', '2.º semestre'),
    ('annual', 'Anual'),
]


class EduCurriculum(models.Model):
    _inherit = 'edu.curriculum'

    edu_is_higher = fields.Boolean(compute='_compute_edu_is_higher')
    total_credits = fields.Float(string='Créditos do curso', compute='_compute_total_credits', digits=(6, 1))

    @api.depends('level_id.subsystem')
    def _compute_edu_is_higher(self):
        for curriculum in self:
            curriculum.edu_is_higher = curriculum.level_id.subsystem == 'higher'

    @api.depends('line_ids.credits')
    def _compute_total_credits(self):
        for curriculum in self:
            curriculum.total_credits = sum(curriculum.line_ids.mapped('credits'))


class EduCurriculumYear(models.Model):
    _inherit = 'edu.curriculum.year'

    edu_is_higher = fields.Boolean(related='curriculum_id.edu_is_higher')
    credits = fields.Float(string='Créditos', compute='_compute_credits', digits=(6, 1))

    @api.depends('line_ids.credits')
    def _compute_credits(self):
        for year in self:
            year.credits = sum(year.line_ids.mapped('credits'))

    @api.model_create_multi
    def create(self, vals_list):
        # No superior não há classe nacional: a «classe» do ano do plano é o ano do curso.
        Curriculum = self.env['edu.curriculum']
        for vals in vals_list:
            if not vals.get('class_number') and vals.get('year'):
                if Curriculum.browse(vals.get('curriculum_id')).level_id.subsystem == 'higher':
                    vals['class_number'] = vals['year']
        return super().create(vals_list)


class EduCurriculumLine(models.Model):
    _inherit = 'edu.curriculum.line'

    edu_is_higher = fields.Boolean(related='curriculum_id.edu_is_higher')
    semester = fields.Selection(SEMESTERS, string='Semestre', default='1')
    credits = fields.Float(string='Créditos', digits=(4, 1))
    contact_hours = fields.Integer(string='Horas de contacto', help='Horas lectivas presenciais no semestre.')
    uc_type = fields.Selection(
        UC_TYPES, string='Tipo de UC', compute='_compute_uc_type', store=True, readonly=False, precompute=True
    )
    is_final_work = fields.Boolean(
        string='Trabalho final', help='Trabalho de fim de curso (licenciatura) ou dissertação (mestrado).'
    )

    @api.depends('is_compulsory')
    def _compute_uc_type(self):
        # A optativa é a não obrigatória do núcleo; a transversal é obrigatória.
        for line in self:
            if not line.is_compulsory:
                line.uc_type = 'optional'
            elif line.uc_type != 'transversal':
                line.uc_type = 'compulsory'

    @api.onchange('uc_type')
    def _onchange_uc_type(self):
        self.is_compulsory = self.uc_type != 'optional'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('uc_type'):
                vals['is_compulsory'] = vals['uc_type'] != 'optional'
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('uc_type'):
            vals = dict(vals, is_compulsory=vals['uc_type'] != 'optional')
        return super().write(vals)

    @api.constrains('credits', 'contact_hours')
    def _check_credits(self):
        for line in self:
            if line.credits < 0 or line.contact_hours < 0:
                raise ValidationError(self.env._('Os créditos e as horas de contacto não podem ser negativos.'))
