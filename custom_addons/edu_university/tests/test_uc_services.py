from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.edu_core.tools.trust import trusted
from odoo.addons.edu_fees.models.edu_fee_plan import EduFeePlan
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'edu')
class TestUcServices(AccountTestInvoicingCommon):
    """Emolumentos por UC, declaração com notas e «Minhas notas» do portal no superior."""

    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.write({'edu_is_school': True, 'edu_school_type': 'higher'})
        cls.env.user.group_ids |= cls.env.ref('edu_core.group_edu_manager')
        Year = cls.env['edu.academic.year']
        cls.year1 = Year.create({'name': '2025/2026', 'date_start': date(2025, 10, 1), 'date_end': date(2026, 9, 30)})
        cls.year2 = Year.create(
            {'name': '2026/2027', 'date_start': date(2026, 10, 1), 'date_end': date(2027, 9, 30), 'is_current': True}
        )
        level = cls.env.ref('edu_university.level_licenciatura')
        cls.course = cls.env['edu.course'].create({'name': 'Medicina', 'code': 'MED', 'level_id': level.id})
        curriculum = cls.env['edu.curriculum'].create({'name': 'MED', 'course_id': cls.course.id, 'level_id': level.id})
        cls.anat, cls.bio, cls.phys = cls.env['edu.subject'].create(
            [
                {'name': 'Anatomia', 'code': 'ANA'},
                {'name': 'Biologia', 'code': 'BIO'},
                {'name': 'Fisiologia', 'code': 'FIS'},
            ]
        )
        Plan = cls.env['edu.curriculum.year']
        plan1 = Plan.create(
            {
                'curriculum_id': curriculum.id,
                'year': 1,
                'line_ids': [
                    (0, 0, {'subject_id': cls.anat.id, 'semester': '1', 'credits': 8}),
                    (0, 0, {'subject_id': cls.bio.id, 'semester': '1', 'credits': 6}),
                ],
            }
        )
        plan2 = Plan.create(
            {'curriculum_id': curriculum.id, 'year': 2, 'line_ids': [(0, 0, {'subject_id': cls.phys.id, 'credits': 8})]}
        )
        Class = cls.env['edu.class']
        cls.y1 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year1.id,
                               'curriculum_year_id': plan1.id})  # fmt: skip
        cls.y2_first = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year2.id,
                                     'curriculum_year_id': plan1.id})  # fmt: skip
        cls.y2 = Class.create({'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year2.id,
                               'curriculum_year_id': plan2.id})  # fmt: skip
        cls.plan = cls.env['edu.fee.plan'].create(
            {
                'name': 'Emolumentos',
                'academic_year_id': cls.year2.id,
                'line_ids': [
                    Command.create(
                        {'name': 'Inscrição em UC em atraso', 'category': 'service', 'recurrence': 'one_off',
                         'amount': 15_000, 'uc_trigger': 'backlog'}
                    ),
                    Command.create(
                        {'name': 'Exame de recurso', 'category': 'exam', 'recurrence': 'one_off', 'amount': 7_500,
                         'uc_trigger': 'uc_appeal'}
                    ),
                ],
            }
        )  # fmt: skip
        cls.student = cls.env['edu.student'].create({'name': 'Teresa Lumbo'})
        cls.startClassPatcher(patch.object(EduFeePlan, '_edu_billing_issue', return_value=False))

    def _enroll(self, edu_class):
        enrollment = self.env['edu.enrollment'].create({'student_id': self.student.id, 'class_id': edu_class.id})
        enrollment.with_context(edu_fees_skip_generation=True).action_confirm()
        return enrollment

    def _invoices(self, enrollment):
        return self.env['account.move'].search([('edu_enrollment_id', '=', enrollment.id)])

    def _year_one(self):
        first = self._enroll(self.y1)
        with trusted(self.env):
            for registration in first.uc_registration_ids:
                passed = registration.subject_id == self.anat
                registration.write({'final_grade': 14 if passed else 6, 'has_final': True,
                                    'state': 'passed' if passed else 'failed'})  # fmt: skip
            first.state = 'completed'
        return first

    def test_backlog_fee(self):
        self._year_one()
        lines = self.plan.line_ids
        self.assertFalse(any(lines.mapped('mandatory')), 'Os emolumentos por UC não entram na geração das propinas.')
        second = self._enroll(self.y2)
        backlog = second.uc_registration_ids.filtered('is_backlog')
        self.assertEqual(backlog.subject_id, self.bio)
        invoices = self._invoices(second)
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices.amount_total, 15_000)
        self.assertIn('Biologia', invoices.invoice_line_ids.name)
        self.assertEqual(invoices.partner_id, self.student.partner_id, 'Sem encarregado: factura ao estudante.')
        backlog._edu_charge('backlog')
        self.assertEqual(len(self._invoices(second)), 1, 'Uma vez por inscrição.')
        self.assertFalse(self.student._edu_service_catalog() & lines, 'Fora do balcão.')

    def test_appeal_fee(self):
        self._year_one()
        second = self._enroll(self.y2)
        self.year2.action_generate_trimesters()
        semester = self.year2.trimester_ids.sorted('number')[:1]
        bio = second.uc_registration_ids.filtered('is_backlog')
        # O docente lança a frequência (aqui em sudo: a janela de lançamento é do professor da UC).
        assessment = self.env['edu.assessment'].sudo().create(
            {'name': 'Frequência', 'class_id': self.y2_first.id, 'subject_id': self.bio.id,
             'trimester_id': semester.id, 'assessment_type': 'frequency'}
        )  # fmt: skip
        assessment.action_fill_students()
        assessment.grade_ids.score = 9
        self.assertEqual(bio.frequency_status, 'admitted')
        period = self.env['edu.exam.period'].create(
            {'name': 'Recurso', 'kind': 'uc_appeal', 'academic_year_id': self.year2.id,
             'date_start': date(2027, 2, 1), 'date_end': date(2027, 2, 28)}
        )  # fmt: skip
        session = self.env['edu.exam.session'].create(
            {'period_id': period.id, 'subject_id': self.bio.id, 'date': date(2027, 2, 10)}
        )
        session.action_summon()
        self.assertEqual(session.seat_ids.uc_registration_id, bio)
        appeal = self._invoices(second).filtered(lambda m: m.edu_category == 'exam')
        self.assertEqual(appeal.amount_total, 7_500)

    def test_declaration_and_portal(self):
        first = self._year_one()
        document = self.env['edu.document'].create(
            {'document_type': 'grades', 'student_id': self.student.id, 'enrollment_id': first.id, 'purpose': 'bolsa'}
        )
        document._check_requirements()
        html = (
            self.env['ir.actions.report']
            ._render_qweb_html('edu_documents.action_report_declaration_grades', document.ids)[0]
            .decode()
        )
        self.assertIn('Anatomia', html)
        self.assertNotIn('Biologia', html, 'Só as aprovadas.')
        self.assertIn('8 créditos', html)
        second = self._enroll(self.y2)
        data = self.env['edu.student.portal'].grades(self.student, second)
        self.assertTrue(data['higher'])
        self.assertEqual({row['name'] for row in data['ucs']}, {'Biologia', 'Fisiologia'})
        self.assertEqual((data['credits_earned'], data['credits_course']), ('8', '22'))
        self.assertEqual(data['course_average']['text'], '14')
        self.assertTrue(next(row for row in data['ucs'] if row['name'] == 'Biologia')['backlog'])
