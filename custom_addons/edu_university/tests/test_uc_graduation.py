from datetime import date

from odoo.addons.edu_core.tools.trust import trusted
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestUcGraduation(TransactionCase):
    """Licenciatura de 2 anos: passagem com UCs em atraso, retenção, TFC e conclusão com a média pesada."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'edu_is_school': True, 'edu_school_type': 'higher', 'edu_director_name': 'Reitor'})
        Year = cls.env['edu.academic.year']
        cls.year1 = Year.create({'name': '2025/2026', 'date_start': date(2025, 10, 1), 'date_end': date(2026, 9, 30)})
        cls.year2 = Year.create({'name': '2026/2027', 'date_start': date(2026, 10, 1), 'date_end': date(2027, 9, 30)})
        level = cls.env.ref('edu_university.level_licenciatura')
        cls.course = cls.env['edu.course'].create({'name': 'Arquitectura', 'code': 'ARQ', 'level_id': level.id})
        curriculum = cls.env['edu.curriculum'].create({'name': 'ARQ', 'course_id': cls.course.id, 'level_id': level.id})
        Subject = cls.env['edu.subject']
        cls.a, cls.b, cls.c, cls.d, cls.tfc = Subject.create(
            [
                {'name': 'Desenho', 'code': 'DES'},
                {'name': 'Geometria', 'code': 'GEO'},
                {'name': 'História da Arte', 'code': 'HAR'},
                {'name': 'Projecto', 'code': 'PRJ'},
                {'name': 'Trabalho de Fim de Curso', 'code': 'TFC'},
            ]
        )
        Plan = cls.env['edu.curriculum.year']
        cls.plan1 = Plan.create(
            {
                'curriculum_id': curriculum.id,
                'year': 1,
                'line_ids': [
                    (0, 0, {'subject_id': cls.a.id, 'semester': '1', 'credits': 6}),
                    (0, 0, {'subject_id': cls.b.id, 'semester': '1', 'credits': 4}),
                    (0, 0, {'subject_id': cls.c.id, 'semester': '2', 'credits': 5}),
                ],
            }
        )
        cls.plan2 = Plan.create(
            {
                'curriculum_id': curriculum.id,
                'year': 2,
                'line_ids': [
                    (0, 0, {'subject_id': cls.d.id, 'semester': '1', 'credits': 10}),
                    (0, 0, {'subject_id': cls.tfc.id, 'semester': 'annual', 'credits': 10, 'is_final_work': True}),
                ],
            }
        )
        Class = cls.env['edu.class']
        cls.y1c1 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year1.id,
                                 'curriculum_year_id': cls.plan1.id})  # fmt: skip
        cls.y2c1 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year2.id,
                                 'curriculum_year_id': cls.plan1.id})  # fmt: skip
        cls.y2c2 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year2.id,
                                 'curriculum_year_id': cls.plan2.id})  # fmt: skip
        cls.student = cls.env['edu.student'].create({'name': 'Rui Kassoma'})
        cls.teacher = cls.env['hr.employee'].create({'name': 'Prof. Neto', 'edu_is_teacher': True})

    def _enroll(self, edu_class):
        enrollment = self.env['edu.enrollment'].create({'student_id': self.student.id, 'class_id': edu_class.id})
        enrollment.action_confirm()
        return enrollment

    def _grades(self, enrollment, grades):
        """Notas finais das UCs (o motor e os exames estão testados à parte)."""
        with trusted(self.env):
            for registration in enrollment.uc_registration_ids:
                if registration.subject_id in grades:
                    grade = grades[registration.subject_id]
                    registration.write(
                        {
                            'final_grade': grade,
                            'has_final': True,
                            'state': 'passed' if grade >= 10 else 'failed',
                        }
                    )

    def _decide(self, enrollment):
        result = (
            self.env['edu.year.result']
            ._compute_for_classes(enrollment.class_id)
            .filtered(lambda r: r.enrollment_id == enrollment)
        )
        enrollment._edu_close_year()
        return result

    def test_retention(self):
        regulation = self.env['edu.university.regulation']._get(self.env.company, self.course.level_id)
        regulation.max_backlog = 1
        first = self._enroll(self.y1c1)
        self._grades(first, {self.a: 8, self.b: 9, self.c: 14})
        result = self._decide(first)
        self.assertEqual((result.status, result.negative_count), ('retained', 2))
        self.assertIn('Desenho', result.reason)
        self.assertEqual(first.state, 'retained')
        # Fica no 1.º ano e inscreve-se só nas UCs em falta.
        repeat = self._enroll(self.y2c1)
        self.assertEqual(repeat.uc_registration_ids.subject_id, self.a | self.b)

    def test_pending_decision(self):
        first = self._enroll(self.y1c1)
        self._grades(first, {self.a: 12})
        self.assertEqual(self._decide(first).status, 'pending')
        self.assertEqual(first.state, 'active', 'Fica em aberto enquanto há UCs por decidir.')

    def test_full_course(self):
        first = self._enroll(self.y1c1)
        self._grades(first, {self.a: 15, self.b: 7, self.c: 12})
        result = self._decide(first)
        self.assertEqual(result.status, 'conditional')
        self.assertIn('Geometria', result.reason)
        # Média do ano: (15 × 6 + 12 × 5) / 11 = 13,6 → 14
        self.assertEqual(result.average, 14)
        self.assertEqual(first.state, 'completed')
        second = self._enroll(self.y2c2)
        self.assertEqual(second.uc_registration_ids.subject_id, self.b | self.d | self.tfc)
        # TFC: a nota da defesa é a nota da UC.
        tfc = second.uc_registration_ids.filtered(lambda r: r.subject_id == self.tfc)
        project = self.env['edu.final.project'].create(
            {
                'name': 'Habitação social em Luanda',
                'student_id': self.student.id,
                'advisor_id': self.teacher.id,
                'defense_date': date(2027, 7, 15),
            }
        )
        self.assertEqual((project.edu_kind, project.uc_registration_id), ('tfc', tfc))
        project.action_submit()
        project.action_evaluate(16.4)
        self.assertEqual((tfc.final_grade, tfc.state, tfc.result_source), (16, 'passed', 'final_work'))
        self._grades(second, {self.b: 11, self.d: 13})
        result = self._decide(second)
        self.assertEqual(result.status, 'graduated')
        graduation = result._register_graduation()
        self.assertEqual(graduation.final_project_id, project)
        # Média final pesada: (15×6 + 11×4 + 12×5 + 13×10 + 16×10) / 35 = 484 / 35 = 13,83 → 14
        self.assertEqual(graduation.uc_credits, 35)
        self.assertEqual(graduation.final_grade, 14)
        self.assertEqual(len(graduation.uc_result_ids), 5)
        graduation.action_issue()
        self.assertTrue(graduation.diploma_number)
        certificate = graduation._graduation_document('certificate')
        html = (
            self.env['ir.actions.report']
            ._render_qweb_html('edu_documents.action_report_certificate', certificate.ids)[0]
            .decode()
        )
        self.assertIn('Habitação social em Luanda', html)
        self.assertIn('Geometria', html)
        self.assertIn('Média final do curso', html)
        self.assertNotIn('Média por Extenso', html, 'Sem o quadro do ensino geral.')
        self.assertNotIn('Plano Curricular (PC)', html, 'Sem o quadro do técnico.')
        diploma = graduation._graduation_document('diploma')
        html = self.env['ir.actions.report']._render_qweb_html('edu_documents.action_report_diploma', diploma.ids)[0]
        html = html.decode()
        self.assertIn('Licenciatura em Arquitectura', html)
        self.assertIn('Ministério do Ensino Superior', html)
        self.assertIn('conferido o grau de', html)
        self.assertNotIn('nesta Escola', html)
