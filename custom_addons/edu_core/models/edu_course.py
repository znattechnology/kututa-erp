from odoo import api, fields, models
from odoo.exceptions import ValidationError

COMPONENTS = [
    ('socio_cultural', 'Sociocultural'),
    ('scientific', 'Científica'),
    ('technical', 'Técnica, tecnológica e prática'),
    ('internship', 'Estágio'),
]


class EduCoordination(models.Model):
    _name = 'edu.coordination'
    _description = 'Coordenação (de curso ou de disciplina)'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string='Coordenação', required=True)
    code = fields.Char(string='Código')
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    coordination_type = fields.Selection(
        [('course', 'Coordenação de curso'), ('subject', 'Coordenação de disciplina')], string='Tipo'
    )
    head_id = fields.Many2one('hr.employee', string='Coordenador(a)', check_company=True)
    course_ids = fields.One2many('edu.course', 'coordination_id', string='Cursos')
    subject_ids = fields.One2many('edu.subject', 'coordination_id', string='Disciplinas')
    active = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint('UNIQUE(company_id, name)', 'Já existe uma coordenação com este nome.')


class EduCourse(models.Model):
    _name = 'edu.course'
    _description = 'Curso'
    _inherit = ['mail.thread']
    _order = 'level_id, name'
    _check_company_auto = True

    name = fields.Char(string='Curso', required=True, tracking=True)
    code = fields.Char(string='Código', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    level_id = fields.Many2one('edu.level', string='Nível', required=True, tracking=True)
    coordination_id = fields.Many2one('edu.coordination', string='Coordenação', check_company=True)
    duration_years = fields.Integer(
        string='Duração (anos)', compute='_compute_duration_years', store=True, readonly=False, precompute=True
    )
    description = fields.Text(string='Descrição')
    curriculum_template_id = fields.Many2one(
        'edu.curriculum.template',
        string='Molde nacional',
        domain="[('level_id', '=', level_id), ('is_profile', '=', True)]",
        help='Perfil do curso no catálogo nacional; o plano junta o tronco comum do nível e este perfil.',
    )
    requires_internship = fields.Boolean(string='Estágio obrigatório')
    requires_final_project = fields.Boolean(string='Prova de aptidão profissional (PAP)')
    has_national_exam = fields.Boolean(string='Exame nacional')
    has_special_exam = fields.Boolean(string='Exame especial')
    curriculum_ids = fields.One2many('edu.curriculum', 'course_id', string='Planos curriculares')
    curriculum_id = fields.Many2one(
        'edu.curriculum', string='Plano em vigor', compute='_compute_curriculum_id', help='O plano activo mais recente.'
    )
    active = fields.Boolean(default=True)

    _code_company_uniq = models.Constraint('UNIQUE(company_id, code)', 'Já existe um curso com este código.')

    @api.depends('curriculum_ids.active')
    def _compute_curriculum_id(self):
        for course in self:
            curricula = course.curriculum_ids.filtered('active').sorted('id')
            course.curriculum_id = curricula[-1:] if curricula else False

    @api.depends('level_id')
    def _compute_duration_years(self):
        for course in self:
            if course.level_id and not course.duration_years:
                course.duration_years = course.level_id.class_to - course.level_id.class_from + 1

    @api.onchange('level_id')
    def _onchange_level_id(self):
        if self.curriculum_template_id.level_id != self.level_id:
            self.curriculum_template_id = False

    @api.model_create_multi
    def create(self, vals_list):
        courses = super().create(vals_list)
        if not self.env.context.get('edu_no_materialize'):
            # Como no secPed: o curso nasce com o plano nacional (tronco comum ⊕ perfil), editável depois.
            for course in courses:
                course._materialize_curriculum()
        return courses

    def _materialize_curriculum(self):
        self.ensure_one()
        Template = self.env['edu.curriculum.template']
        base = Template._find(self.level_id, profile=False)
        profile = self.curriculum_template_id
        if not base and not profile:
            return self.env['edu.curriculum']
        return (base or profile)._materialize(
            self.company_id,
            course=self,
            profile=profile if base else None,
            name=self.env._('Plano Nacional — %s', self.name),
        )

    def action_materialize_curriculum(self):
        self.ensure_one()
        curriculum = self._materialize_curriculum()
        if not curriculum:
            raise ValidationError(
                self.env._('Não há molde nacional para o nível %s: crie o plano à mão.', self.level_id.name)
            )
        return curriculum._action_open()


class EduSubject(models.Model):
    _name = 'edu.subject'
    _description = 'Disciplina'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string='Disciplina', required=True, translate=True)
    code = fields.Char(string='Código', help='Código nacional (LP, MAT, FIS…), chave dos planos e das pautas.')
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    coordination_id = fields.Many2one('edu.coordination', string='Coordenação', check_company=True)
    component = fields.Selection(COMPONENTS, string='Componente de formação')
    duration_years = fields.Integer(
        string='Duração (anos)', default=1, help='1 = anual; 2 ou mais = plurianual (a nota final é a do último ano).'
    )
    start_year = fields.Integer(string='Começa no ano', default=1, help='Ano do curso em que a disciplina começa.')
    is_national_exam = fields.Boolean(string='Exame nacional')
    prerequisite_ids = fields.Many2many(
        'edu.subject',
        'edu_subject_prerequisite_rel',
        'subject_id',
        'prerequisite_id',
        string='Precedências',
        check_company=True,
    )
    active = fields.Boolean(default=True)

    _code_company_uniq = models.Constraint('UNIQUE(company_id, code)', 'Já existe uma disciplina com este código.')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for subject in self:
            subject.display_name = f'{subject.name} ({subject.code})' if subject.code else subject.name

    @api.constrains('prerequisite_ids')
    def _check_prerequisites(self):
        for subject in self:
            if subject in subject.prerequisite_ids:
                raise ValidationError(self.env._('Uma disciplina não pode ser precedência de si mesma.'))
            if subject._has_cycle('prerequisite_ids'):
                raise ValidationError(self.env._('As precedências de %s formam um ciclo.', subject.name))

    @api.constrains('duration_years', 'start_year')
    def _check_years(self):
        for subject in self:
            if subject.duration_years < 1 or subject.start_year < 1:
                raise ValidationError(self.env._('A duração e o ano de início começam em 1.'))
