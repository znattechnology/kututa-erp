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


class EduCourse(models.Model):
    """Os números do curso no ano em curso, para os cartões da secretaria: as turmas, os alunos, as vagas e os
    alunos por classe."""

    _inherit = 'edu.course'

    edu_class_count = fields.Integer(string='Turmas', compute='_compute_edu_counts')
    edu_student_count = fields.Integer(string='Alunos', compute='_compute_edu_counts')
    edu_occupancy = fields.Integer(string='Ocupação (%)', compute='_compute_edu_counts')
    edu_per_class = fields.Json(string='Alunos por classe (cartão)', compute='_compute_edu_counts')

    def _compute_edu_counts(self):
        Class = self.env['edu.class'].sudo()
        Enrollment = self.env['edu.enrollment'].sudo()
        for course in self:
            classes = Class.search([('course_id', '=', course.id), ('academic_year_id.is_current', '=', True)])
            groups = (
                dict(
                    Enrollment._read_group(
                        [('class_id', 'in', classes.ids), ('state', 'in', ENROLLED)], ['class_id'], ['__count']
                    )
                )
                if classes
                else {}
            )
            per_number = {}
            for edu_class in classes:
                row = per_number.setdefault(edu_class.class_number, {'students': 0, 'classes': 0})
                row['students'] += groups.get(edu_class, 0)
                row['classes'] += 1
            students = sum(groups.values())
            capacity = sum(classes.mapped('capacity'))
            top = max([row['students'] for row in per_number.values()] or [0]) or 1
            course.edu_class_count = len(classes)
            course.edu_student_count = students
            course.edu_occupancy = round(100 * students / capacity) if capacity else 0
            course.edu_per_class = [
                {
                    'label': f'{number}ª' if number else 'Inic.',
                    'students': row['students'],
                    'classes': row['classes'],
                    'width': round(100 * row['students'] / top, 1),
                }
                for number, row in sorted(per_number.items())
            ]
