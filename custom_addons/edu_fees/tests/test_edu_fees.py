from datetime import date

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.edu_fees.models.edu_fee_plan import due_dates
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'edu')
class TestEduFees(AccountTestInvoicingCommon):
    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.write({'edu_is_school': True, 'edu_gate_grace_days': 0})
        cls.env.user.group_ids |= cls.env.ref('edu_core.group_edu_manager')
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.course = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.env.ref('edu_core.level_tecnico').id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }  # fmt: skip
        )
        tenth = cls.course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 10)
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': cls.course.id, 'curriculum_year_id': tenth.id}
        )
        cls.plan = cls.env['edu.fee.plan'].create(
            {
                'name': 'Propinas 2026/2027',
                'academic_year_id': cls.year.id,
                'line_ids': [
                    Command.create(
                        {'name': 'Matrícula', 'category': 'enrollment', 'recurrence': 'one_off', 'amount': 20_000}
                    ),
                    Command.create(
                        {'name': 'Confirmação', 'category': 'confirmation', 'recurrence': 'one_off', 'amount': 5_000}
                    ),
                    Command.create(
                        {'name': 'Propina', 'category': 'tuition', 'recurrence': 'monthly', 'amount': 50_000}
                    ),
                    Command.create(
                        {'name': 'Declaração', 'category': 'service', 'recurrence': 'one_off', 'amount': 2_500}
                    ),
                    Command.create({'name': 'Cartão', 'category': 'card', 'recurrence': 'one_off', 'amount': 3_420}),
                ],
            }
        )
        cls.tuition = cls.plan.line_ids.filtered(lambda line: line.category == 'tuition')
        cls.student = cls.env['edu.student'].create({'name': 'Ana Kiala', 'birth_date': date(2007, 5, 10)})
        guardian = cls.env['edu.guardian'].create(
            {'name': 'Maria Kiala', 'phone': '+244 923 000 000', 'vat': '004567891LA041'}
        )
        cls.env['edu.student.guardian'].create({'student_id': cls.student.id, 'guardian_id': guardian.id})
        cls.guardian = guardian

    def _enroll(self, day, student=None):
        enrollment = self.env['edu.enrollment'].create(
            {'student_id': (student or self.student).id, 'class_id': self.edu_class.id, 'date': day}
        )
        enrollment.with_context(edu_fees_skip_generation=True).action_confirm()
        return enrollment

    def _generate(self, enrollment, today):
        return self.env['edu.fee.plan']._generate_for_enrollments(enrollment, today=today)

    def test_due_dates(self):
        # Janela de Setembro a Julho: 11 meses, dia 8.
        months = due_dates('monthly', date(2026, 9, 1), date(2027, 7, 31), 8)
        self.assertEqual(len(months), 11)
        self.assertEqual((months[0], months[-1]), (date(2026, 9, 8), date(2027, 7, 8)))
        self.assertEqual(len(due_dates('monthly', date(2026, 9, 1), date(2027, 7, 31), 8, 10)), 10)
        self.assertEqual(
            due_dates('quarterly', date(2026, 9, 1), date(2027, 7, 31), 31),
            [date(2026, 9, 28), date(2026, 12, 28), date(2027, 3, 28)],
        )
        self.assertEqual(due_dates('one_off', date(2026, 9, 1), date(2027, 7, 31), 5), [date(2026, 9, 5)])

    def test_generation(self):
        enrollment = self._enroll(date(2026, 9, 1))
        invoices = self._generate(enrollment, date(2026, 11, 15))
        tuition = invoices.filtered(lambda m: m.edu_category == 'tuition')
        # Setembro, Outubro e Novembro; nunca um mês futuro.
        self.assertEqual(
            sorted(tuition.mapped('edu_due_period')), [date(2026, 9, 8), date(2026, 10, 8), date(2026, 11, 8)]
        )
        self.assertEqual(len(invoices.filtered(lambda m: m.edu_category == 'enrollment')), 1)
        self.assertEqual(set(invoices.mapped('state')), {'posted'})
        first = tuition.sorted('edu_due_period')[0]
        self.assertEqual(first.amount_total, 50_000)
        self.assertEqual(first.partner_id, self.guardian.partner_id)  # encarregado com NIF
        self.assertEqual(first.invoice_line_ids.tax_ids.l10n_ao_exemption_id.code, 'M21')
        self.assertIn('Setembro 2026', first.invoice_line_ids.name)
        # Repetir não duplica.
        self.assertFalse(self._generate(enrollment, date(2026, 11, 20)))
        # Quem entra a meio do ano começa no mês da matrícula (a matrícula cobra-se na mesma).
        late = self._enroll(date(2026, 11, 10), self.env['edu.student'].create({'name': 'Bento'}))
        invoices = self._generate(late, date(2026, 11, 15))
        self.assertEqual(
            invoices.filtered(lambda m: m.edu_category == 'tuition').mapped('edu_due_period'), [date(2026, 11, 8)]
        )
        self.assertEqual(len(invoices), 2)
        # Escola sem propina: só a matrícula.
        self.company.edu_billing_mode = 'fee_free'
        other = self._enroll(date(2026, 9, 1), self.env['edu.student'].create({'name': 'Carla'}))
        self.assertEqual(self._generate(other, date(2026, 10, 1)).mapped('edu_category'), ['enrollment'])
        # Quem continua na escola paga a confirmação, não a matrícula (DE Conjunto 40/21 tabela as duas).
        renewal = self._enroll(date(2026, 9, 1), self.env['edu.student'].create({'name': 'Domingos'}))
        renewal.enrollment_type = 'renewal'
        self.assertEqual(self._generate(renewal, date(2026, 10, 1)).mapped('edu_category'), ['confirmation'])

    def test_plan_resolution(self):
        enrollment = self._enroll(date(2026, 9, 1))
        Plan = self.env['edu.fee.plan']
        self.assertEqual(Plan._for_enrollment(enrollment), self.plan)
        by_course = Plan.create({'name': 'Curso', 'academic_year_id': self.year.id, 'course_id': self.course.id})
        self.assertEqual(Plan._for_enrollment(enrollment), by_course)
        by_class_number = Plan.create({'name': 'Classe', 'academic_year_id': self.year.id, 'class_number': 10})
        self.assertEqual(Plan._for_enrollment(enrollment), by_class_number)
        by_class = Plan.create({'name': 'Turma', 'academic_year_id': self.year.id, 'class_id': self.edu_class.id})
        self.assertEqual(Plan._for_enrollment(enrollment), by_class)

    def test_scholarships(self):
        Scholarship = self.env['edu.scholarship']
        due = date(2026, 10, 8)
        cases = [
            ({'scholarship_type': 'full'}, 50_000),
            ({'discount_amount': 15_000}, 15_000),
            ({'discount_amount': 80_000}, 50_000),
            ({'discount_percent': 30}, 15_000),
            ({'discount_percent': 50, 'discount_amount': 10_000}, 25_000),
            ({'discount_percent': 50, 'date_from': date(2026, 11, 1)}, 0),
            ({'discount_percent': 50, 'date_to': date(2026, 9, 30)}, 0),
        ]
        for vals, expected in cases:
            scholarship = Scholarship.create(
                {
                    'student_id': self.student.id,
                    'academic_year_id': self.year.id,
                    'scholarship_type': 'partial',
                    'date_from': date(2026, 9, 1),
                    'state': 'approved',
                    **vals,
                }  # fmt: skip
            )
            self.assertEqual(Scholarship._relief(self.student, self.year, due, 50_000)[1], expected, vals)
            scholarship.unlink()
        # Mérito 20% e carência 30 000: vale a mais vantajosa.
        Scholarship.create([
            {'student_id': self.student.id, 'academic_year_id': self.year.id, 'scholarship_type': 'merit',
             'discount_percent': 20, 'date_from': date(2026, 9, 1), 'state': 'approved'},
            {'student_id': self.student.id, 'academic_year_id': self.year.id, 'scholarship_type': 'need',
             'discount_amount': 30_000, 'date_from': date(2026, 9, 1), 'state': 'approved'},
        ])  # fmt: skip
        self.assertEqual(Scholarship._relief(self.student, self.year, due, 50_000)[1], 30_000)

    def test_scholarship_invoice_and_approval(self):
        scholarship = self.env['edu.scholarship'].create(
            {
                'student_id': self.student.id,
                'academic_year_id': self.year.id,
                'scholarship_type': 'partial',
                'discount_percent': 30,
                'date_from': date(2026, 9, 1),
            }  # fmt: skip
        )
        with self.assertRaises(UserError):
            scholarship.action_approve()  # quem pediu não aprova
        scholarship.requested_by_id = self.env.ref('base.user_root')
        scholarship.action_approve()
        enrollment = self._enroll(date(2026, 9, 1))
        tuition = self._generate(enrollment, date(2026, 9, 10)).filtered(lambda m: m.edu_category == 'tuition')
        self.assertEqual((tuition.amount_total, tuition.edu_discount), (35_000, 15_000))
        scholarship.discount_percent = 40
        self.assertEqual(scholarship.state, 'draft')  # a alteração volta a pedir aprovação

    def test_late_fees(self):
        enrollment = self._enroll(date(2026, 9, 1))
        invoice = self._generate(enrollment, date(2026, 9, 10)).filtered(lambda m: m.edu_category == 'tuition')
        Rule = self.env['edu.late.fee.rule']
        rule = Rule.create({'name': 'Multa 2%', 'fee_type': 'percent', 'percent': 2, 'grace_days': 0})
        self.assertEqual(rule.tax_id.l10n_ao_exemption_id.code, 'M02')
        # Vencida a 8/09, a 1/11: 2 meses × 2% de 50 000 = 2 000 (overdue.service.spec).
        fees = Rule._apply_late_fees(today=date(2026, 11, 1))
        fee = fees.filtered(lambda m: m.edu_late_fee_origin_id == invoice)
        self.assertEqual((fee.amount_total, fee.edu_category, fee.state), (2_000, 'late_fee', 'posted'))
        self.assertFalse(
            Rule._apply_late_fees(today=date(2026, 11, 1)).filtered(lambda m: m.edu_late_fee_origin_id == invoice)
        )
        # Um mês depois factura-se só a diferença.
        later = Rule._apply_late_fees(today=date(2026, 12, 1)).filtered(lambda m: m.edu_late_fee_origin_id == invoice)
        self.assertEqual(later.amount_total, 1_000)
        self.assertEqual(rule._late_fee(50_000, date(2026, 9, 8), date(2026, 11, 1)), 2_000)
        rule.max_amount = 500
        self.assertEqual(rule._late_fee(50_000, date(2026, 9, 8), date(2026, 11, 1)), 500)
        rule.write({'max_amount': 0, 'grace_days': 365})
        self.assertEqual(rule._late_fee(50_000, date(2026, 9, 8), date(2026, 11, 1)), 0)
        rule.write({'fee_type': 'fixed', 'amount': 5_000, 'grace_days': 0})
        self.assertEqual(rule._late_fee(50_000, date(2026, 9, 8), date(2026, 11, 1)), 5_000)

    def test_payment_oldest_first(self):
        enrollment = self._enroll(date(2026, 9, 1))
        invoices = self._generate(enrollment, date(2026, 10, 15))
        wizard = self.env['edu.fee.payment'].create(
            {
                'student_id': self.student.id,
                'amount': 90_000,
                'journal_id': self.company_data['default_journal_cash'].id,
            }
        )
        wizard.action_confirm()
        by_due = invoices.sorted(lambda m: (m.invoice_date_due, m.id))
        # Matrícula (20 000) e Setembro (50 000) pagas; Outubro com 20 000.
        self.assertEqual(by_due.mapped('payment_state'), ['paid', 'paid', 'partial'])
        self.assertEqual(by_due[-1].amount_residual, 30_000)
        self.assertEqual(self.student.edu_open_amount, 30_000)

    def test_gating_and_irregular(self):
        enrollment = self._enroll(date(2026, 9, 1))
        self._generate(enrollment, date(2026, 9, 10))
        self.assertTrue(self.student.edu_in_debt)
        self.assertIn(self.student, self.env['edu.student'].search([('edu_in_debt', '=', True)]))
        self.env['edu.student']._edu_update_standing()
        self.assertEqual(enrollment.state, 'irregular')
        # Avisar: segue com aviso; bloquear: impede.
        blocked, message = self.student._edu_gate('documents')
        self.assertFalse(blocked)
        self.assertTrue(message)
        self.company.edu_gate_mode = 'block'
        document = self.env['edu.document'].create(
            {'document_type': 'frequency', 'student_id': self.student.id, 'enrollment_id': enrollment.id}
        )
        with self.assertRaisesRegex(UserError, 'Situação financeira'):
            document.action_issue()
        # Bolseiro do Estado: isento do bloqueio.
        self.env['edu.scholarship'].create(
            {
                'student_id': self.student.id,
                'academic_year_id': self.year.id,
                'scholarship_type': 'government',
                'discount_percent': 50,
                'date_from': date(2026, 9, 1),
                'state': 'approved',
            }  # fmt: skip
        )
        self.student.invalidate_recordset()
        self.assertFalse(self.student._edu_gate('documents')[0])
        # Paga a dívida, volta a activa.
        self.env['edu.fee.payment'].create(
            {
                'student_id': self.student.id,
                'amount': 70_000,
                'journal_id': self.company_data['default_journal_cash'].id,
            }
        ).action_confirm()
        self.student.invalidate_recordset()
        self.env['edu.student']._edu_update_standing()
        self.assertEqual(enrollment.state, 'active')

    def test_service_charge(self):
        enrollment = self._enroll(date(2026, 9, 1))
        declaration = self.plan.line_ids.filtered(lambda line: line.category == 'service')
        wizard = self.env['edu.fee.service'].create(
            {'student_id': self.student.id, 'fee_line_id': declaration.id, 'reference': 'PED-1'}
        )
        move = self.env['account.move'].browse(wizard.action_confirm()['res_id'])
        self.assertEqual((move.amount_total, move.edu_enrollment_id), (2_500, enrollment))
        again = self.env['edu.fee.service'].create(
            {'student_id': self.student.id, 'fee_line_id': declaration.id, 'reference': 'PED-1'}
        )
        self.assertEqual(again.action_confirm()['res_id'], move.id)
        # O cartão leva IVA a 14% incluído no valor: 3 000 + 420.
        card = self.plan.line_ids.filtered(lambda line: line.category == 'card')
        card_move = self.env['account.move'].browse(
            self.env['edu.fee.service']
            .create({'student_id': self.student.id, 'fee_line_id': card.id})
            .action_confirm()['res_id']
        )
        self.assertEqual((card_move.amount_untaxed, card_move.amount_total), (3_000, 3_420))
