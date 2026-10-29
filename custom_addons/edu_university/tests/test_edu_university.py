from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduUniversity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'edu_is_school': True, 'edu_school_type': 'higher'})
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 10, 1), 'date_end': date(2027, 9, 30), 'is_current': True}
        )
        cls.licenciatura = cls.env.ref('edu_university.level_licenciatura')
        cls.course = cls.env['edu.course'].create(
            {'name': 'Engenharia Informática', 'code': 'EI', 'level_id': cls.licenciatura.id}
        )
        cls.curriculum = cls.env['edu.curriculum'].create(
            {'name': 'EI 2026', 'course_id': cls.course.id, 'level_id': cls.licenciatura.id}
        )
        Subject = cls.env['edu.subject']
        cls.calc1, cls.prog1, cls.ethics, cls.tfc = Subject.create(
            [
                {'name': 'Cálculo I', 'code': 'CAL1'},
                {'name': 'Programação I', 'code': 'PRG1'},
                {'name': 'Ética e Deontologia', 'code': 'ETI'},
                {'name': 'Trabalho de Fim de Curso', 'code': 'TFC'},
            ]
        )
        cls.first_year = cls.env['edu.curriculum.year'].create(
            {
                'curriculum_id': cls.curriculum.id,
                'year': 1,
                'line_ids': [
                    (0, 0, {'subject_id': cls.calc1.id, 'semester': '1', 'credits': 6, 'contact_hours': 60}),
                    (0, 0, {'subject_id': cls.prog1.id, 'semester': '2', 'credits': 7.5, 'contact_hours': 75}),
                    (0, 0, {'subject_id': cls.ethics.id, 'semester': '2', 'credits': 3, 'uc_type': 'transversal'}),
                ],
            }
        )

    def test_company_is_higher(self):
        self.assertTrue(self.env.company.edu_is_higher)
        self.env.company.edu_school_type = 'general'
        self.assertFalse(self.env.company.edu_is_higher)

    def test_two_semesters(self):
        self.year.action_generate_trimesters()
        semesters = self.year.trimester_ids.sorted('number')
        self.assertEqual(semesters.mapped('name'), ['1º Semestre', '2º Semestre'])
        self.assertEqual(semesters[0].date_start, date(2026, 10, 1))
        self.assertEqual(semesters[1].date_end, date(2027, 9, 30))
        self.assertEqual(semesters[0].date_end.toordinal() + 1, semesters[1].date_start.toordinal())
        with self.assertRaisesRegex(ValidationError, 'dois semestres'):
            self.env['edu.trimester'].create(
                {
                    'academic_year_id': self.year.id,
                    'number': 3,
                    'date_start': date(2027, 9, 1),
                    'date_end': date(2027, 9, 30),
                }
            )

    def test_school_keeps_trimesters(self):
        """Uma escola do geral, na mesma base, continua com três trimestres."""
        school = self.env['res.company'].create({'name': 'Colégio', 'edu_is_school': True})
        year = self.env['edu.academic.year'].create(
            {
                'name': '2026/2027',
                'company_id': school.id,
                'date_start': date(2026, 9, 1),
                'date_end': date(2027, 7, 31),
            }
        )
        year.action_generate_trimesters()
        self.assertEqual(len(year.trimester_ids), 3)
        self.assertEqual(year.trimester_ids.sorted('number')[0].name, '1º Trimestre')

    def test_curriculum_credits(self):
        self.assertEqual(self.first_year.class_number, 1, 'No superior a classe é o ano do curso.')
        self.assertEqual(self.first_year.credits, 16.5)
        self.assertEqual(self.curriculum.total_credits, 16.5)
        self.assertTrue(self.curriculum.edu_is_higher)
        lines = self.first_year.line_ids
        ethics = lines.filtered(lambda line: line.subject_id == self.ethics)
        self.assertEqual((ethics.uc_type, ethics.is_compulsory), ('transversal', True))
        ethics.uc_type = 'optional'
        self.assertFalse(ethics.is_compulsory)
        ethics.is_compulsory = True
        self.assertEqual(ethics.uc_type, 'compulsory')
        with self.assertRaises(ValidationError):
            ethics.credits = -1

    def test_final_work(self):
        last = self.env['edu.curriculum.year'].create(
            {
                'curriculum_id': self.curriculum.id,
                'year': 4,
                'line_ids': [
                    (0, 0, {'subject_id': self.tfc.id, 'semester': 'annual', 'credits': 15, 'is_final_work': True})
                ],
            }
        )
        self.assertEqual(last.class_number, 4)
        self.assertTrue(last.line_ids.is_final_work)
        self.assertEqual(self.curriculum.total_credits, 31.5)

    def test_student_without_guardian(self):
        edu_class = self.env['edu.class'].create(
            {
                'name': 'EI-1A',
                'course_id': self.course.id,
                'curriculum_id': self.curriculum.id,
                'curriculum_year_id': self.first_year.id,
            }
        )
        self.assertEqual(edu_class.class_number, 1)
        application = self.env['edu.application'].create(
            {
                'name': 'Helena Kiala',
                'birth_date': date(2006, 3, 2),
                'id_number': '009988776LA041',
                'phone': '+244 923 111 222',
                'desired_course_id': self.course.id,
                'desired_class_number': 1,
                'completed_class': 12,
            }
        )
        self.assertTrue(application.edu_is_higher)
        application.action_submit()
        application.action_review()
        application.class_id = edu_class
        if application.admission_test_required:
            application.write({'has_admission_score': True, 'admission_score': 14})
        application.action_approve()
        student = application.student_id
        self.assertTrue(student.edu_is_higher)
        self.assertFalse(student.guardian_link_ids)
        self.assertEqual(application.enrollment_id.state, 'active')
