from odoo import api, fields, models

from .edu_enrollment import SEAT_STATES

STUDENT_STATUS = [
    ('enrolled', 'Matriculado'),
    ('pending', 'Matrícula pendente'),
    ('former', 'Não matriculado este ano'),
    ('graduated', 'Concluiu o curso'),
    ('transferred', 'Transferido'),
    ('dropped', 'Matrícula anulada'),
    ('none', 'Sem matrícula'),
]


class EduStudent(models.Model):
    _inherit = 'edu.student'

    enrollment_ids = fields.One2many('edu.enrollment', 'student_id', string='Matrículas')
    # Gravados: a lista de alunos filtra, agrupa e tem o painel Curso › Turma por eles (com milhares de alunos, a
    # secretaria procura pela turma, não pela lista inteira).
    current_enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula actual', compute='_compute_current_enrollment_id', store=True, index=True
    )
    current_class_id = fields.Many2one(
        'edu.class', string='Turma actual', compute='_compute_current_enrollment_id', store=True, index=True
    )
    current_course_id = fields.Many2one(
        'edu.course', string='Curso', related='current_class_id.course_id', store=True, index=True
    )
    current_class_number = fields.Integer(
        string='Classe', related='current_class_id.class_number', store=True, aggregator=None
    )
    last_academic_year_id = fields.Many2one(
        'edu.academic.year', string='Último ano lectivo', compute='_compute_current_enrollment_id', store=True
    )
    student_status = fields.Selection(
        STUDENT_STATUS, string='Situação', compute='_compute_current_enrollment_id', store=True, index=True
    )

    @api.depends(
        'enrollment_ids.state',
        'enrollment_ids.academic_year_id',
        'enrollment_ids.academic_year_id.is_current',
        'enrollment_ids.class_id',
    )
    def _compute_current_enrollment_id(self):
        for student in self:
            enrollments = student.enrollment_ids.sorted(lambda e: (e.academic_year_id.date_start, e.id), reverse=True)
            current = enrollments.filtered(lambda e: e.state in SEAT_STATES)[:1]
            student.current_enrollment_id = current
            student.current_class_id = current.class_id
            student.student_status = student._status_of(enrollments[:1])
            student.last_academic_year_id = enrollments[:1].academic_year_id

    def _status_of(self, last):
        """A situação pela última matrícula: matriculado no ano em curso, ou porque deixou de o estar."""
        if not last:
            return 'none'
        in_current_year = last.academic_year_id.is_current
        if in_current_year and last.state in SEAT_STATES:
            return 'enrolled'
        if in_current_year and last.state == 'draft':
            return 'pending'
        if last.state in ('transferred', 'dropped'):
            return last.state
        curriculum = last.class_id.curriculum_id
        if last.state == 'completed' and curriculum and last.class_id.class_number >= curriculum.class_to:
            return 'graduated'
        return 'former'
