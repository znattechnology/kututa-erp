from datetime import date

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'edu')
class TestEduRecords(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.course = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.env.ref('edu_core.level_tecnico').id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
                'requires_final_project': True,
            }
        )
        last = cls.course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 13)
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': cls.course.id, 'curriculum_year_id': last.id}
        )
        cls.student = cls.env['edu.student'].create({'name': 'Ana Kiala', 'process_number': '1520'})
        cls.subjects = cls.edu_class.subject_line_ids.subject_id[:2]
        cls.enrollment = cls.env['edu.enrollment'].create(
            {'student_id': cls.student.id, 'class_id': cls.edu_class.id, 'subject_ids': [Command.set(cls.subjects.ids)]}
        )
        cls.enrollment.action_confirm()

    def _grades(self, score_by_subject):
        for subject, score in zip(self.subjects, score_by_subject, strict=True):
            for trimester in self.year.trimester_ids:
                for kind in ('continuous', 'trimester_test'):
                    assessment = self.env['edu.assessment'].create(
                        {
                            'name': kind,
                            'class_id': self.edu_class.id,
                            'subject_id': subject.id,
                            'trimester_id': trimester.id,
                            'assessment_type': kind,
                        }  # fmt: skip
                    )
                    assessment.action_fill_students()
                    assessment.grade_ids.score = score

    def test_graduation(self):
        self._grades([14, 17])
        self.edu_class.action_compute_year_results()
        result = self.enrollment.year_result_id
        self.assertEqual(result.status, 'graduated')
        project = self.env['edu.final.project'].create(
            {
                'name': 'Cuidados de enfermagem ao recém-nascido',
                'student_id': self.student.id,
                'enrollment_id': self.enrollment.id,
                'defense_date': date(2027, 7, 10),
                'grade': 18,
            }  # fmt: skip
        )
        action = result.action_register_graduation()
        graduation = self.env['edu.graduation'].browse(action['res_id'])
        with self.assertRaises(UserError):
            graduation.action_issue()  # o curso exige a PAP aprovada
        project.action_evaluate()
        graduation.final_project_id = project
        graduation.action_issue()
        # PC = (14 + 17) / 2 = 15,5 → 16; final = (2 × 16 + 18) / 3 = 16,7 → 17.
        self.assertEqual((graduation.plan_average, graduation.final_grade), (16, 17))
        self.assertTrue(graduation.diploma_number.startswith(f'{date.today().year}/'))
        self.assertEqual(graduation.state, 'issued')
        self.assertEqual(len(graduation.final_result_ids), 2)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env['edu.student'].create({'name': 'Outro', 'process_number': '1520'})

    def test_not_graduated(self):
        self._grades([8, 9])
        self.edu_class.action_compute_year_results()
        with self.assertRaises(ValidationError):
            self.env['edu.graduation'].create(
                {'student_id': self.student.id, 'year_result_id': self.enrollment.year_result_id.id}
            )
