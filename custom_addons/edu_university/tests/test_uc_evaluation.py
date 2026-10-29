from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestUcEvaluation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'edu_is_school': True, 'edu_school_type': 'higher'})
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 10, 1), 'date_end': date(2027, 9, 30), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.sem1, cls.sem2 = cls.year.trimester_ids.sorted('number')
        level = cls.env.ref('edu_university.level_licenciatura')
        cls.course = cls.env['edu.course'].create({'name': 'Direito', 'code': 'DIR', 'level_id': level.id})
        curriculum = cls.env['edu.curriculum'].create({'name': 'DIR', 'course_id': cls.course.id, 'level_id': level.id})
        cls.civil, cls.history = cls.env['edu.subject'].create(
            [{'name': 'Direito Civil I', 'code': 'DC1'}, {'name': 'História do Direito', 'code': 'HD'}]
        )
        plan = cls.env['edu.curriculum.year'].create(
            {
                'curriculum_id': curriculum.id,
                'year': 1,
                'line_ids': [
                    (0, 0, {'subject_id': cls.civil.id, 'semester': '1', 'credits': 6}),
                    (0, 0, {'subject_id': cls.history.id, 'semester': 'annual', 'credits': 8}),
                ],
            }
        )
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year.id, 'curriculum_year_id': plan.id}
        )
        cls.students = cls.env['edu.student'].create([{'name': n} for n in ('Ana', 'Bruno', 'Carla', 'Daniel')])
        cls.enrollments = cls.env['edu.enrollment']
        for student in cls.students:
            enrollment = cls.env['edu.enrollment'].create({'student_id': student.id, 'class_id': cls.edu_class.id})
            enrollment.action_confirm()
            cls.enrollments |= enrollment

    def _assess(self, name, scores, *, kind='frequency', weight=1.0, subject=None, semester=None):
        assessment = self.env['edu.assessment'].create(
            {
                'name': name,
                'class_id': self.edu_class.id,
                'subject_id': (subject or self.civil).id,
                'trimester_id': (semester or self.sem1).id,
                'assessment_type': kind,
                'weight': weight,
            }
        )
        assessment.action_fill_students()
        for grade in assessment.grade_ids:
            if grade.student_id.name in scores:
                grade.score = scores[grade.student_id.name]
        return assessment

    def _uc(self, name, subject=None):
        return self.enrollments.uc_registration_ids.filtered(
            lambda r: r.student_id.name == name and r.subject_id == (subject or self.civil)
        )

    def test_frequency_and_close(self):
        self._assess('1.ª frequência', {'Ana': 15, 'Bruno': 11, 'Carla': 5, 'Daniel': 16})
        self._assess('2.ª frequência', {'Ana': 14, 'Bruno': 9, 'Carla': 7, 'Daniel': 16})
        self._assess('Trabalho', {'Ana': 16, 'Bruno': 10, 'Carla': 6, 'Daniel': 16}, kind='coursework', weight=0.5)
        ana, bruno, carla, daniel = (self._uc(n) for n in ('Ana', 'Bruno', 'Carla', 'Daniel'))
        # Ana: (15 + 14 + 8) / 2,5 = 14,8 → dispensada com 15
        self.assertAlmostEqual(ana.frequency_mark, 14.8)
        self.assertEqual((ana.frequency_status, ana.final_grade, ana.result_source), ('exempt', 15, 'frequency'))
        self.assertEqual(bruno.frequency_status, 'admitted')
        self.assertFalse(bruno.has_final)
        self.assertEqual(carla.frequency_status, 'excluded')
        # Antes de fechar o semestre a situação fica em aberto (as notas ainda podem mudar).
        self.assertEqual(ana.state, 'enrolled')
        # Daniel faltou a 2 de 4 aulas: 50 % de presenças, excluído apesar de 16.
        for day, state in ((5, 'present'), (6, 'absent'), (7, 'absent'), (8, 'present')):
            lesson = self.env['edu.lesson'].create(
                {
                    'class_id': self.edu_class.id,
                    'subject_id': self.civil.id,
                    'date': date(2026, 10, day),
                    'summary': 'Fontes do direito',
                }
            )
            lesson.action_open_roll_call()
            lesson.attendance_ids.filtered(lambda a: a.student_id.name == 'Daniel').state = state
            lesson.action_done()
        self.sem1.action_close()
        self.assertEqual((daniel.attendance_rate, daniel.frequency_status, daniel.state), (50, 'excluded', 'failed'))
        self.assertEqual((ana.state, ana.credits_earned), ('passed', 6))
        self.assertEqual(carla.state, 'failed')
        self.assertEqual(bruno.state, 'enrolled', 'Admitido: espera o exame.')
        # A anual (História) não fecha com o 1.º semestre.
        self.assertEqual(self._uc('Ana', self.history).state, 'enrolled')
        # Exame normal 8: 0,4 × 10 + 0,6 × 8 → abaixo do mínimo, reprova com 8; recurso 12 → 0,4 × 10 + 0,6 × 12 = 11,2.
        self.assertAlmostEqual(bruno.frequency_mark, 10)
        bruno.exam_normal = 8
        self.assertEqual((bruno.final_grade, bruno.state, bruno.result_source), (8, 'failed', 'normal'))
        bruno.exam_appeal = 12
        self.assertEqual((bruno.final_grade, bruno.state, bruno.result_source), (11, 'passed', 'appeal'))
        # Reabrir o semestre reabre a situação por frequência.
        self.sem1.action_reopen()
        self.assertEqual(ana.state, 'enrolled')
        self.assertEqual(bruno.state, 'passed', 'A nota de exame decide logo.')

    def test_exam_rules(self):
        self._assess('1.ª frequência', {'Ana': 16, 'Bruno': 10, 'Carla': 4})
        ana, bruno, carla = (self._uc(n) for n in ('Ana', 'Bruno', 'Carla'))
        with self.assertRaisesRegex(UserError, 'Só os admitidos'):
            ana.exam_normal = 12
        with self.assertRaisesRegex(UserError, 'recurso'):
            carla.exam_appeal = 12
        with self.assertRaisesRegex(UserError, 'melhoria'):
            bruno.exam_improvement = 15
        with self.assertRaisesRegex(ValidationError, '0 a 20'):
            bruno.exam_normal = 21
        user = self.env['res.users'].create(
            {
                'name': 'Docente',
                'login': 'docente_uc',
                'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        with self.assertRaises(AccessError):
            bruno.with_user(user).final_grade = 20
        self.sem1.action_close()
        ana.exam_improvement = 18
        self.assertEqual((ana.final_grade, ana.result_source), (18, 'improvement'))
        carla.exam_special = 14
        self.assertEqual((carla.final_grade, carla.state), (10, 'passed'))

    def test_assessment_types(self):
        with self.assertRaisesRegex(ValidationError, 'provas de frequência'):
            self._assess('Prova trimestral', {}, kind='trimester_test')
        # Várias provas de frequência na mesma UC e semestre.
        self._assess('1.ª', {})
        self._assess('2.ª', {})
        self.assertEqual(
            self.env['edu.term.result'].search_count([('class_id', '=', self.edu_class.id)]),
            0,
            'No superior não há médias trimestrais.',
        )

    def test_regulation_rules(self):
        regulation = self.env['edu.university.regulation']._get(self.env.company, self.course.level_id)
        regulation.write({'exemption_grade': 0, 'frequency_weight': 0, 'exam_min': 0})
        self._assess('1.ª frequência', {'Ana': 18})
        ana = self._uc('Ana')
        self.assertEqual(ana.frequency_status, 'admitted', 'Sem dispensa, todos os admitidos vão a exame.')
        ana.exam_normal = 9.6
        self.assertEqual((ana.final_grade, ana.state), (10, 'passed'))
        with self.assertRaises(ValidationError):
            regulation.exemption_grade = 8
