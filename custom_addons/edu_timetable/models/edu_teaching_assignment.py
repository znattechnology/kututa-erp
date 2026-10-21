from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EduTeachingAssignment(models.Model):
    """Colocação: que professor lecciona que disciplina em que turma (no ano, ou só num trimestre). É a base do
    lançamento de notas e dos sumários."""

    _name = 'edu.teaching.assignment'
    _description = 'Colocação de professor'
    _inherit = ['mail.thread']
    _order = 'class_id, subject_id, trimester_id'
    _check_company_auto = True

    class_id = fields.Many2one('edu.class', string='Turma', required=True, index=True, check_company=True)
    company_id = fields.Many2one(related='class_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='class_id.academic_year_id', store=True, index=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, index=True, check_company=True)
    teacher_id = fields.Many2one(
        'hr.employee',
        string='Professor(a)',
        required=True,
        index=True,
        tracking=True,
        check_company=True,
        domain="[('edu_is_teacher', '=', True)]",
    )
    trimester_id = fields.Many2one(
        'edu.trimester',
        string='Trimestre',
        domain="[('academic_year_id', '=', academic_year_id)]",
        help='Vazio: o ano lectivo inteiro.',
    )
    weekly_hours = fields.Integer(string='Tempos semanais (plano)', compute='_compute_weekly_hours')
    qualified = fields.Boolean(string='Habilitado', compute='_compute_qualified')

    @api.depends('class_id', 'subject_id')
    def _compute_weekly_hours(self):
        for assignment in self:
            subject = assignment.subject_id
            lines = assignment.class_id.subject_line_ids.filtered(
                lambda line, subject=subject: line.subject_id == subject
            )
            assignment.weekly_hours = sum(lines.mapped('weekly_hours'))

    @api.depends('teacher_id', 'subject_id')
    def _compute_qualified(self):
        for assignment in self:
            subjects = assignment.teacher_id.sudo().edu_subject_ids
            assignment.qualified = not subjects or assignment.subject_id in subjects

    @api.depends('class_id', 'subject_id', 'teacher_id')
    def _compute_display_name(self):
        for assignment in self:
            assignment.display_name = (
                f'{assignment.subject_id.name or ""} · {assignment.class_id.display_name or ""} · '
                f'{assignment.teacher_id.name or ""}'
            )

    @api.constrains('class_id', 'subject_id', 'trimester_id')
    def _check_subject(self):
        for assignment in self:
            subjects = assignment.class_id.subject_line_ids.subject_id
            if subjects and assignment.subject_id not in subjects:
                raise ValidationError(
                    self.env._(
                        '%(subject)s não faz parte do plano da turma %(class)s.',
                        subject=assignment.subject_id.name,
                        **{'class': assignment.class_id.display_name},
                    )
                )
            trimester = assignment.trimester_id
            if trimester and trimester.academic_year_id != assignment.academic_year_id:
                raise ValidationError(self.env._('O trimestre não é do ano lectivo da turma.'))
            # Um só professor por turma e disciplina em períodos que se cruzam (o ano cruza-se com tudo).
            domain = [
                ('id', '!=', assignment.id),
                ('class_id', '=', assignment.class_id.id),
                ('subject_id', '=', assignment.subject_id.id),
            ]
            if trimester:
                domain.append(('trimester_id', 'in', [False, trimester.id]))
            other = self.search(domain, limit=1)
            if other:
                raise ValidationError(
                    self.env._(
                        '%(subject)s já tem professor colocado na turma %(class)s: %(teacher)s.',
                        subject=assignment.subject_id.name,
                        teacher=other.teacher_id.name,
                        **{'class': assignment.class_id.display_name},
                    )
                )

    @api.constrains('teacher_id', 'class_id')
    def _check_initiation(self):
        """O educador da iniciação acompanha só a sua turma (e quem lecciona noutras turmas não fica na iniciação)."""
        initiation = self.env.ref('edu_core.level_iniciacao', raise_if_not_found=False)
        for assignment in self:
            others = self.search(
                [
                    ('id', '!=', assignment.id),
                    ('teacher_id', '=', assignment.teacher_id.id),
                    ('academic_year_id', '=', assignment.academic_year_id.id),
                    ('class_id', '!=', assignment.class_id.id),
                ]
            )
            classes = others.class_id | assignment.class_id
            if len(classes) > 1 and initiation in classes.level_id:
                raise ValidationError(
                    self.env._(
                        '%s é educador(a) de uma turma da iniciação e não pode leccionar noutras turmas.',
                        assignment.teacher_id.name,
                    )
                )

    @api.model
    def _teacher_for(self, edu_class, subject, day=None):
        """Professor colocado na data: a colocação do trimestre prevalece sobre a do ano."""
        assignments = self.search([('class_id', '=', edu_class.id), ('subject_id', '=', subject.id)])
        if day:
            for assignment in assignments.filtered('trimester_id'):
                if assignment.trimester_id.date_start <= day <= assignment.trimester_id.date_end:
                    return assignment.teacher_id
        return assignments.filtered(lambda a: not a.trimester_id)[:1].teacher_id
