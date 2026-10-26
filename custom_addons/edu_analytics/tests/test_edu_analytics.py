from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduAnalytics(TransactionCase):
    """Análise de dados: o resultado de cada ano, o percurso dos que entraram num ano e as listas dos alunos."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Year = cls.env['edu.academic.year']
        cls.first = Year.create({'name': '2040/2041', 'date_start': date(2040, 9, 1), 'date_end': date(2041, 7, 31)})
        cls.second = Year.create({'name': '2041/2042', 'date_start': date(2041, 9, 1), 'date_end': date(2042, 7, 31)})
        course = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.env.ref('edu_core.level_tecnico').id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }  # fmt: skip
        )
        years = course.curriculum_id.year_ids

        def make_class(year, number):
            return cls.env['edu.class'].create(
                {
                    'name': 'A',
                    'course_id': course.id,
                    'curriculum_year_id': years.filtered(lambda y: y.class_number == number).id,
                    'academic_year_id': year.id,
                }
            )

        tenth, eleventh = make_class(cls.first, 10), make_class(cls.second, 11)
        cls.students = {}
        for name, state, status, average in (
            ('Ana', 'completed', 'promoted', 14.0),
            ('Bruno', 'retained', 'retained', 8.0),
            ('Carla', 'dropped', False, 0.0),
        ):
            student = cls.env['edu.student'].create({'name': name})
            enrollment = cls.env['edu.enrollment'].create(
                {'student_id': student.id, 'class_id': tenth.id, 'late_reason': 'Teste'}
            )
            enrollment.state = state
            if status:
                cls.env['edu.year.result'].create(
                    {'enrollment_id': enrollment.id, 'status': status, 'average': average}
                )
            cls.students[name] = student
        # Só a Ana renova a matrícula no ano seguinte.
        renewal = cls.env['edu.enrollment'].create(
            {
                'student_id': cls.students['Ana'].id,
                'class_id': eleventh.id,
                'enrollment_type': 'renewal',
                'late_reason': 'Teste',
            }
        )
        renewal.state = 'active'
        cls.filters = {'year_ids': [cls.first.id, cls.second.id]}

    def test_summary_and_cohort(self):
        data = self.env['edu.analytics'].dashboard(self.filters)
        first, second = data['summary']
        self.assertEqual(
            (first['enrolled'], first['decided'], first['transition'], first['retention']), (3, 2, 50.0, 50.0)
        )
        self.assertEqual(first['outcomes']['dropped'], 1)
        self.assertEqual((second['enrolled'], second['outcomes']['ongoing'], second['transition']), (1, 1, None))
        self.assertEqual(data['performance']['bands'][0]['counts'], [1, 0, 1, 0])
        # O percurso: dos três que entraram, a Ana continua; o Bruno não renovou e a Carla desistiu antes.
        cohort = data['cohort']
        self.assertEqual((cohort['entry_year_id'], cohort['size']), (self.first.id, 3))
        self.assertEqual(cohort['steps'][1]['segments']['ongoing'], 1)
        self.assertEqual(cohort['steps'][1]['segments']['left'], 2)
        self.assertEqual(cohort['kpis']['ever_retained'], 1)

    def test_students(self):
        Analytics = self.env['edu.analytics']
        action = Analytics.students(self.filters, 'cohort', {'year_id': self.second.id, 'key': 'left'})
        self.assertEqual(set(action['domain'][0][2]), {self.students['Bruno'].id, self.students['Carla'].id})
        action = Analytics.students(self.filters, 'outcome', {'year_id': self.first.id, 'key': 'retained'})
        self.assertEqual(action['domain'][0][2], self.students['Bruno'].ids)
        action = Analytics.students(self.filters, 'band', {'year_id': self.first.id, 'band': 2})
        self.assertEqual(action['domain'][0][2], self.students['Ana'].ids)

    def test_access(self):
        teacher = new_test_user(self.env, 'prof.analise', groups='edu_core.group_edu_teacher')
        with self.assertRaises(AccessError):
            self.env['edu.analytics'].with_user(teacher).options()
        secretary = new_test_user(self.env, 'sec.analise', groups='edu_core.group_edu_user')
        self.assertTrue(self.env['edu.analytics'].with_user(secretary).options()['years'])
