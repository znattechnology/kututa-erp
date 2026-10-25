from odoo import fields, models

ENROLLED = ('active', 'irregular')


class EduCoordination(models.Model):
    """Os números da coordenação para os cartões da secretaria: os professores, as turmas e os alunos dos seus
    cursos no ano em curso, e os nomes dos cursos."""

    _inherit = 'edu.coordination'

    edu_course_names = fields.Json(string='Cursos (cartão)', compute='_compute_edu_counts')
    edu_teacher_count = fields.Integer(string='Professores', compute='_compute_edu_counts')
    edu_class_count = fields.Integer(string='Turmas', compute='_compute_edu_counts')
    edu_student_count = fields.Integer(string='Alunos', compute='_compute_edu_counts')

    def _compute_edu_counts(self):
        Employee = self.env['hr.employee'].sudo()
        Class = self.env['edu.class'].sudo()
        Enrollment = self.env['edu.enrollment'].sudo()
        for coordination in self:
            courses = coordination.course_ids
            classes = Class.search([('course_id', 'in', courses.ids), ('academic_year_id.is_current', '=', True)])
            coordination.edu_course_names = courses.sorted('name').mapped('name')
            coordination.edu_teacher_count = Employee.search_count([('edu_coordination_id', '=', coordination.id)])
            coordination.edu_class_count = len(classes)
            coordination.edu_student_count = (
                Enrollment.search_count([('class_id', 'in', classes.ids), ('state', 'in', ENROLLED)]) if classes else 0
            )
