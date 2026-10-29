from datetime import date

from odoo.addons.edu_core.tools.trust import trusted
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestUcRegistration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'edu_is_school': True, 'edu_school_type': 'higher'})
        Year = cls.env['edu.academic.year']
        cls.year1 = Year.create({'name': '2025/2026', 'date_start': date(2025, 10, 1), 'date_end': date(2026, 9, 30)})
        cls.year2 = Year.create({'name': '2026/2027', 'date_start': date(2026, 10, 1), 'date_end': date(2027, 9, 30)})
        level = cls.env.ref('edu_university.level_licenciatura')
        cls.course = cls.env['edu.course'].create({'name': 'Economia', 'code': 'ECO', 'level_id': level.id})
        curriculum = cls.env['edu.curriculum'].create({'name': 'ECO', 'course_id': cls.course.id, 'level_id': level.id})
        Subject = cls.env['edu.subject']
        cls.mat1, cls.mat2, cls.intro, cls.opt, cls.micro, cls.stats = Subject.create(
            [
                {'name': 'Matemática I', 'code': 'MAT1'},
                {'name': 'Matemática II', 'code': 'MAT2'},
                {'name': 'Introdução à Economia', 'code': 'IEC'},
                {'name': 'Inglês Técnico', 'code': 'ING'},
                {'name': 'Microeconomia', 'code': 'MIC'},
                {'name': 'Estatística', 'code': 'EST'},
            ]
        )
        cls.mat2.prerequisite_ids = cls.mat1
        cls.stats.prerequisite_ids = cls.mat2
        Plan = cls.env['edu.curriculum.year']
        cls.plan1 = Plan.create(
            {
                'curriculum_id': curriculum.id,
                'year': 1,
                'line_ids': [
                    (0, 0, {'subject_id': cls.mat1.id, 'semester': '1', 'credits': 6}),
                    (0, 0, {'subject_id': cls.intro.id, 'semester': '1', 'credits': 6}),
                    (0, 0, {'subject_id': cls.mat2.id, 'semester': '2', 'credits': 6}),
                    (0, 0, {'subject_id': cls.opt.id, 'semester': '2', 'credits': 3, 'uc_type': 'optional'}),
                ],
            }
        )
        cls.plan2 = Plan.create(
            {
                'curriculum_id': curriculum.id,
                'year': 2,
                'line_ids': [
                    (0, 0, {'subject_id': cls.micro.id, 'semester': '1', 'credits': 6}),
                    (0, 0, {'subject_id': cls.stats.id, 'semester': '2', 'credits': 6}),
                ],
            }
        )
        Class = cls.env['edu.class']
        cls.c1_y1 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year1.id,
                                  'curriculum_year_id': cls.plan1.id})  # fmt: skip
        cls.c1_y2 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year2.id,
                                  'curriculum_year_id': cls.plan1.id})  # fmt: skip
        cls.c2_y2 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year2.id,
                                  'curriculum_year_id': cls.plan2.id})  # fmt: skip
        cls.student = cls.env['edu.student'].create({'name': 'Joana Mbala'})

    def _enroll(self, edu_class, student=None):
        enrollment = self.env['edu.enrollment'].create(
            {'student_id': (student or self.student).id, 'class_id': edu_class.id}
        )
        enrollment.action_confirm()
        return enrollment

    def _close(self, enrollment, results):
        """Resultados do ano (na 7c vêm da avaliação)."""
        with trusted(self.env):
            for registration in enrollment.uc_registration_ids:
                registration.state = results.get(registration.subject_id, 'passed')
            enrollment.state = 'completed'

    def test_generation_first_year(self):
        enrollment = self._enroll(self.c1_y1)
        registrations = enrollment.uc_registration_ids
        self.assertEqual(registrations.subject_id, self.mat1 | self.intro | self.mat2, 'As optativas escolhem-se.')
        self.assertEqual(enrollment.uc_credits, 18)
        self.assertEqual(set(registrations.mapped('attempt')), {1})
        self.assertEqual(enrollment.subject_ids, registrations.subject_id, 'As UCs são as disciplinas da matrícula.')
        # A optativa acrescenta-se à mão e entra nas disciplinas.
        self.env['edu.uc.registration'].create({'enrollment_id': enrollment.id, 'subject_id': self.opt.id})
        self.assertIn(self.opt, enrollment.subject_ids)
        self.assertEqual(enrollment.uc_credits, 21)
        # A lista das notas da turma inclui a estudante na UC.
        self.assertIn(enrollment, self.env['edu.enrollment']._for_class_subject(self.c1_y1, self.mat2))

    def test_out_of_plan_and_future_year(self):
        enrollment = self._enroll(self.c1_y1)
        foreign = self.env['edu.subject'].create({'name': 'Direito Romano', 'code': 'DRO'})
        with self.assertRaisesRegex(ValidationError, 'não é do plano'):
            self.env['edu.uc.registration'].create({'enrollment_id': enrollment.id, 'subject_id': foreign.id})
        with self.assertRaisesRegex(ValidationError, 'é do 2º ano'):
            self.env['edu.uc.registration'].create({'enrollment_id': enrollment.id, 'subject_id': self.micro.id})

    def test_backlog_in_lower_class(self):
        """Passa ao 2.º ano com Matemática II reprovada: faz MAT2 na turma do 1.º ano; Estatística (precede MAT2)
        fica de fora, com aviso."""
        first = self._enroll(self.c1_y1)
        self._close(first, {self.mat2: 'failed'})
        second = self._enroll(self.c2_y2)
        registrations = second.uc_registration_ids
        self.assertEqual(registrations.subject_id, self.mat2 | self.micro)
        backlog = registrations.filtered(lambda r: r.subject_id == self.mat2)
        self.assertTrue(backlog.is_backlog)
        self.assertEqual((backlog.class_id, backlog.attempt), (self.c1_y2, 2))
        self.assertIn('Estatística', second.warning)
        self.assertIn(second, self.env['edu.enrollment']._for_class_subject(self.c1_y2, self.mat2))
        self.assertNotIn(second, self.env['edu.enrollment']._for_class_subject(self.c2_y2, self.mat2))
        self.assertEqual(second.uc_backlog_count, 1)
        # Aprovadas não se repetem.
        with self.assertRaisesRegex(ValidationError, 'já aprovou'):
            self.env['edu.uc.registration'].create({'enrollment_id': second.id, 'subject_id': self.mat1.id})

    def test_precedence_same_year(self):
        """A precedência do 1.º semestre, inscrita no mesmo ano, deixa inscrever na UC do 2.º."""
        enrollment = self._enroll(self.c1_y1)
        mat2 = enrollment.uc_registration_ids.filtered(lambda r: r.subject_id == self.mat2)
        self.assertTrue(mat2)
        mat1 = enrollment.uc_registration_ids.filtered(lambda r: r.subject_id == self.mat1)
        mat2.unlink()
        mat1.action_drop()
        self.assertEqual(mat1.state, 'dropped')
        self.assertNotIn(self.mat1, enrollment.subject_ids)
        with self.assertRaisesRegex(ValidationError, 'falta aprovar: Matemática I'):
            self.env['edu.uc.registration'].create({'enrollment_id': enrollment.id, 'subject_id': self.mat2.id})

    def test_prescription(self):
        regulation = self.env['edu.university.regulation']._get(self.env.company, self.course.level_id)
        regulation.max_attempts = 1
        first = self._enroll(self.c1_y1)
        self._close(first, {self.intro: 'failed'})
        repeat = self._enroll(self.c1_y2)
        self.assertNotIn(self.intro, repeat.uc_registration_ids.subject_id)
        self.assertIn('prescreveu', repeat.warning)
        self.assertNotIn(self.mat1, repeat.uc_registration_ids.subject_id, 'Aprovada no ano anterior.')

    def test_credit_limit(self):
        regulation = self.env['edu.university.regulation']._get(self.env.company, self.course.level_id)
        regulation.max_semester_credits = 8
        enrollment = self._enroll(self.c1_y1)
        self.assertIn('créditos no 1º semestre', enrollment.warning)
        # Sem Introdução, o 1.º semestre fica com 6; a optativa leva o 2.º a 9.
        enrollment.uc_registration_ids.filtered(lambda r: r.subject_id == self.intro).action_drop()
        with self.assertRaisesRegex(ValidationError, '9 créditos no 2º semestre'):
            self.env['edu.uc.registration'].create({'enrollment_id': enrollment.id, 'subject_id': self.opt.id})

    def test_state_protected(self):
        enrollment = self._enroll(self.c1_y1)
        registration = enrollment.uc_registration_ids[:1]
        user = self.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'secretaria_uc',
                'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        with self.assertRaises(AccessError):
            registration.with_user(user).state = 'passed'
