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


# As componentes do plano pela ordem da legenda, cada uma com a sua cor da paleta categórica (o_edu_subj_N).
COMPONENT_ORDER = ['socio_cultural', 'scientific', 'technical', 'internship']


class EduCurriculum(models.Model):
    """O plano curricular para os cartões da secretaria: por classe, os tempos semanais e as disciplinas, com os
    tempos de cada componente; as disciplinas do plano e as turmas deste ano que o seguem."""

    _inherit = 'edu.curriculum'

    edu_years = fields.Json(string='Anos (cartão)', compute='_compute_edu_card')
    edu_subject_count = fields.Integer(string='Disciplinas', compute='_compute_edu_card')
    edu_class_count = fields.Integer(string='Turmas este ano', compute='_compute_edu_card')

    def _compute_edu_card(self):
        Class = self.env['edu.class'].sudo()
        labels = dict(self.env['edu.curriculum.line']._fields['component'].selection)
        for curriculum in self:
            years = []
            for year in curriculum.year_ids.sorted('class_number'):
                hours = {}
                for line in year.line_ids:
                    hours[line.component or 'technical'] = (
                        hours.get(line.component or 'technical', 0) + line.weekly_hours
                    )
                total = sum(hours.values())
                years.append(
                    {
                        'id': year.id,
                        'label': f'{year.class_number}ª classe' if year.class_number else 'Iniciação',
                        'hours': total,
                        'subjects': len(year.line_ids),
                        'parts': [
                            {
                                'key': key,
                                'css': f'o_edu_subj_{index + 1}',
                                'label': labels.get(key, key),
                                'hours': hours[key],
                            }
                            for index, key in enumerate(COMPONENT_ORDER)
                            if hours.get(key)
                        ],
                    }
                )
            # A barra de cada classe com a largura dos seus tempos face à classe com mais tempos.
            top = max([y['hours'] for y in years] or [0]) or 1
            for year in years:
                year['width'] = round(100 * year['hours'] / top, 1)
            curriculum.edu_years = years
            curriculum.edu_subject_count = len(curriculum.line_ids.subject_id)
            curriculum.edu_class_count = Class.search_count(
                [('curriculum_id', '=', curriculum.id), ('academic_year_id.is_current', '=', True)]
            )


class EduSubject(models.Model):
    """A disciplina nos planos e no ano em curso, para os cartões da secretaria: as classes e os tempos semanais
    nos planos, os cursos que a têm, os professores atribuídos e as turmas deste ano (com as que estão sem
    professor)."""

    _inherit = 'edu.subject'

    edu_classes_label = fields.Char(string='Classes', compute='_compute_edu_card')
    edu_hours_label = fields.Char(string='Tempos semanais', compute='_compute_edu_card')
    edu_course_count = fields.Integer(string='Cursos', compute='_compute_edu_card')
    edu_teacher_count = fields.Integer(string='Professores este ano', compute='_compute_edu_card')
    edu_class_count = fields.Integer(string='Turmas este ano', compute='_compute_edu_card')
    edu_missing_count = fields.Integer(string='Turmas sem professor', compute='_compute_edu_card')
    edu_component_css = fields.Char(compute='_compute_edu_card')

    def _compute_edu_card(self):
        Line = self.env['edu.curriculum.line'].sudo()
        Class = self.env['edu.class'].sudo()
        Assignment = self.env['edu.teaching.assignment'].sudo()
        lines = Line.search([('subject_id', 'in', self.ids), ('curriculum_id.active', '=', True)])
        current = Class.search(
            [('academic_year_id.is_current', '=', True), ('company_id', 'in', self.env.companies.ids)]
        )
        assignments = Assignment.search([('subject_id', 'in', self.ids), ('class_id', 'in', current.ids)])
        for subject in self:
            mine = lines.filtered(lambda line, s=subject: line.subject_id == s)
            numbers = sorted(set(mine.year_id.mapped('class_number')))
            hours = sorted({h for h in mine.mapped('weekly_hours') if h})
            subject.edu_classes_label = ', '.join(f'{n}ª' if n else 'Inic.' for n in numbers)
            subject.edu_hours_label = (
                '' if not hours else f'{hours[0]}' if len(hours) == 1 else f'{hours[0]} a {hours[-1]}'
            )
            subject.edu_course_count = len(mine.curriculum_id.course_id)
            classes = current.filtered(lambda c, years=mine.year_id: c.curriculum_year_id in years)
            given = assignments.filtered(lambda a, s=subject: a.subject_id == s)
            subject.edu_teacher_count = len(given.teacher_id)
            subject.edu_class_count = len(classes)
            # O estágio acompanha-o o tutor (Estágios), não um professor da disciplina: não conta como em falta.
            missing = classes - given.filtered('teacher_id').class_id
            subject.edu_missing_count = 0 if subject.component == 'internship' else len(missing)
            index = COMPONENT_ORDER.index(subject.component) + 1 if subject.component in COMPONENT_ORDER else 0
            subject.edu_component_css = f'o_edu_subj_{index}'
