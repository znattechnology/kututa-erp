from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduPayroll(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        course = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.env.ref('edu_core.level_tecnico').id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }
        )
        tenth = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 10)
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': course.id, 'curriculum_year_id': tenth.id}
        )
        cls.subject = cls.edu_class.subject_line_ids.subject_id[:1]
        cls.teacher = cls.env['hr.employee'].create(
            {
                'name': 'Bento Professor',
                'edu_is_teacher': True,
                'contract_date_start': '2026-01-05',
                'wage': 0,
                'l10n_ao_pay_basis': 'lesson',
                'l10n_ao_lesson_rate': 2_500,
            }
        )
        cls.other = cls.env['hr.employee'].create({'name': 'Rita Substituta', 'edu_is_teacher': True})

    def test_teaching_load(self):
        monday = self.env['edu.schedule'].create(
            {
                'class_id': self.edu_class.id,
                'subject_id': self.subject.id,
                'teacher_id': self.teacher.id,
                'weekday': '0',
                'hour_from': 7.5,
                'hour_to': 8.25,
            }
        )
        other_slot = self.env['edu.schedule'].create(
            {
                'class_id': self.edu_class.id,
                'subject_id': self.subject.id,
                'teacher_id': self.other.id,
                'weekday': '2',
                'hour_from': 7.5,
                'hour_to': 8.25,
            }
        )
        # Setembro de 2026 (ano lectivo a partir de 1/09): segundas 7, 14, 21 e 28.
        self.env['edu.schedule.exception'].create({'schedule_id': monday.id, 'date': date(2026, 9, 14)})
        self.env['edu.schedule.replacement'].create(
            {'schedule_id': monday.id, 'date': date(2026, 9, 21), 'replacement_teacher_id': self.other.id}
        )
        for day in (date(2026, 9, 2), date(2026, 9, 9)):
            self.env['edu.schedule.replacement'].create(
                {'schedule_id': other_slot.id, 'date': day, 'replacement_teacher_id': self.teacher.id}
            )
        run = self.env['l10n_ao_payroll.run'].create({'company_id': self.company.id, 'year': 2026, 'month': '9'})
        run.action_compute()
        slip = run.payslip_ids.filtered(lambda s: s.employee_id == self.teacher)
        # 4 previstos − 1 sem realização − 1 dado pela substituta + 2 substituições dadas = 4.
        self.assertEqual(
            (slip.edu_planned, slip.edu_exceptions, slip.edu_replacement_out, slip.edu_replacement_in), (4, 1, 1, 2)
        )
        self.assertEqual(slip.lesson_count, 4)
        self.assertEqual(slip.gross, 10_000)
        slip.edu_adjustment = 2
        run.action_compute()
        self.assertEqual(slip.lesson_count, 6)
        slip.lesson_count = 3
        run.action_compute()
        self.assertTrue(slip.edu_lesson_manual)
        self.assertEqual(slip.lesson_count, 3)
