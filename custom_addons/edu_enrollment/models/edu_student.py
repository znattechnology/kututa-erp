from odoo import api, fields, models

from .edu_enrollment import SEAT_STATES


class EduStudent(models.Model):
    _inherit = 'edu.student'

    enrollment_ids = fields.One2many('edu.enrollment', 'student_id', string='Matrículas')
    current_enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula actual', compute='_compute_current_enrollment_id'
    )
    current_class_id = fields.Many2one('edu.class', string='Turma actual', compute='_compute_current_enrollment_id')

    @api.depends('enrollment_ids.state', 'enrollment_ids.academic_year_id')
    def _compute_current_enrollment_id(self):
        for student in self:
            enrolled = student.enrollment_ids.filtered(lambda e: e.state in SEAT_STATES)
            current = enrolled.sorted(lambda e: e.academic_year_id.date_start, reverse=True)[:1]
            student.current_enrollment_id = current
            student.current_class_id = current.class_id
