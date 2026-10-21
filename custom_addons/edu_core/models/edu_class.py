from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EduClass(models.Model):
    """Turma num ano lectivo («10ª A de 2026/2027»). No secPed, a turma (SchoolClass) é a identidade persistente e a
    oferta (ClassOffering) dá-lhe o ano; aqui a turma já é do ano, e a migração cria uma por oferta."""

    _name = 'edu.class'
    _description = 'Turma'
    _inherit = ['mail.thread']
    _order = 'academic_year_id desc, class_number, course_id, name'
    _check_company_auto = True

    name = fields.Char(string='Turma', required=True, tracking=True, help='Letra ou designação: A, B, IG-1…')
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    academic_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano lectivo',
        required=True,
        index=True,
        check_company=True,
        default=lambda self: self.env.company.edu_current_year_id,
        tracking=True,
    )
    course_id = fields.Many2one('edu.course', string='Curso', required=True, index=True, check_company=True)
    level_id = fields.Many2one(related='course_id.level_id', store=True)
    curriculum_id = fields.Many2one(
        'edu.curriculum',
        string='Plano curricular',
        compute='_compute_curriculum_id',
        store=True,
        readonly=False,
        precompute=True,
        check_company=True,
        domain="[('course_id', '=', course_id)]",
    )
    curriculum_year_id = fields.Many2one(
        'edu.curriculum.year',
        string='Ano do plano',
        domain="[('curriculum_id', '=', curriculum_id)]",
        help='Define a classe e as disciplinas da turma.',
    )
    class_number = fields.Integer(
        string='Classe', compute='_compute_class_number', store=True, readonly=False, precompute=True
    )
    course_year = fields.Integer(string='Ano do curso', related='curriculum_year_id.year', store=True)
    subject_line_ids = fields.One2many(related='curriculum_year_id.line_ids', string='Disciplinas')
    capacity = fields.Integer(string='Vagas', default=30)
    room_id = fields.Many2one('edu.room', string='Sala', check_company=True)
    shift_id = fields.Many2one('edu.shift', string='Turno', check_company=True)
    note = fields.Text(string='Notas')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'UNIQUE(company_id, academic_year_id, course_id, class_number, name)',
        'Já existe esta turma no ano lectivo.',
    )

    @api.depends('course_id')
    def _compute_curriculum_id(self):
        for edu_class in self:
            if edu_class.course_id and edu_class.curriculum_id.course_id != edu_class.course_id:
                edu_class.curriculum_id = edu_class.course_id.curriculum_id

    @api.depends('curriculum_year_id')
    def _compute_class_number(self):
        for edu_class in self:
            if edu_class.curriculum_year_id:
                edu_class.class_number = edu_class.curriculum_year_id.class_number
            elif not edu_class.class_number:
                edu_class.class_number = edu_class.course_id.level_id.class_from or 0

    @api.depends('name', 'class_number', 'course_id', 'academic_year_id')
    def _compute_display_name(self):
        for edu_class in self:
            parts = [f'{edu_class.class_number}ª {edu_class.name or ""}'.strip()]
            if edu_class.course_id:
                parts.append(edu_class.course_id.code or edu_class.course_id.name)
            if edu_class.academic_year_id:
                parts.append(edu_class.academic_year_id.name)
            edu_class.display_name = ' · '.join(parts)

    @api.constrains('class_number', 'course_id')
    def _check_class_number(self):
        for edu_class in self:
            level = edu_class.course_id.level_id
            if level and not level.class_from <= edu_class.class_number <= level.class_to:
                raise ValidationError(
                    self.env._(
                        'A %(number)sª classe não pertence ao nível %(level)s (%(start)s.ª a %(end)s.ª).',
                        number=edu_class.class_number,
                        level=level.name,
                        start=level.class_from,
                        end=level.class_to,
                    )
                )

    @api.constrains('room_id', 'shift_id', 'academic_year_id')
    def _check_room(self):
        """Uma sala fixa não serve duas turmas no mesmo turno e ano lectivo."""
        for edu_class in self.filtered(lambda c: c.room_id and c.shift_id):
            clash = self.search(
                [
                    ('id', '!=', edu_class.id),
                    ('room_id', '=', edu_class.room_id.id),
                    ('shift_id', '=', edu_class.shift_id.id),
                    ('academic_year_id', '=', edu_class.academic_year_id.id),
                ],
                limit=1,
            )
            if clash:
                raise ValidationError(
                    self.env._(
                        'A sala %(room)s já é da turma %(other)s no turno %(shift)s.',
                        room=edu_class.room_id.display_name,
                        other=clash.display_name,
                        shift=edu_class.shift_id.name,
                    )
                )

    @api.constrains('capacity', 'room_id')
    def _check_capacity(self):
        for edu_class in self:
            if edu_class.capacity < 0:
                raise ValidationError(self.env._('O número de vagas não pode ser negativo.'))
