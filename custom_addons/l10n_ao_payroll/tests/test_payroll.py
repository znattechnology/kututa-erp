from datetime import date

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao')
class TestL10nAoPayroll(AccountTestInvoicingCommon):
    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.write({'vat': '5000000001'})
        cls.env.user.write(
            {
                'group_ids': [
                    Command.link(cls.env.ref('hr.group_hr_manager').id),
                    Command.link(cls.env.ref('hr_holidays.group_hr_holidays_manager').id),
                ]
            }
        )
        cls.calendar = cls.env.ref('l10n_ao_hr.resource_calendar_ao_44h')
        cls.env.user.tz = 'Africa/Luanda'
        cls.bank = cls.env['res.partner.bank'].create(
            {
                'account_number': 'AO06 0000 0000 0000 0000 0000 0',
                'partner_id': cls.env['res.partner'].create({'name': 'Ana Banco'}).id,
            }
        )
        cls.employee = cls.env['hr.employee'].create(
            {
                'name': 'Ana Silva',
                'company_id': cls.company.id,
                'resource_calendar_id': cls.calendar.id,
                'contract_date_start': '2025-03-10',
                'wage': 200_000,
                'l10n_ao_inss_number': '123456789',
                'identification_id': '001234567LA041',
            }
        )
        cls.employee.version_id.l10n_ao_payroll_bank_account_id = cls.bank
        cls.employee.version_id.l10n_ao_payroll_component_ids = [
            Command.create({'code': 'MEAL', 'amount': 30_000}),
            Command.create({'code': 'TRANSPORT', 'amount': 40_000}),
        ]
        cls.teacher = cls.env['hr.employee'].create(
            {
                'name': 'Bento Professor',
                'company_id': cls.company.id,
                'resource_calendar_id': cls.calendar.id,
                'contract_date_start': '2026-01-05',
                'wage': 0,
                'l10n_ao_pay_basis': 'lesson',
                'l10n_ao_lesson_rate': 2_500,
                'l10n_ao_inss_number': '987654321',
            }
        )

    def _approve(self, leave):
        if leave.state != 'validate':
            leave.sudo().action_approve()
        self.assertEqual(leave.state, 'validate')

    def _run(self, year=2026, month=3):
        run = self.env['l10n_ao_payroll.run'].create({'company_id': self.company.id, 'year': year, 'month': str(month)})
        run.action_compute()
        return run

    def test_monthly_run(self):
        run = self._run()
        self.assertEqual(run.state, 'computed')
        slips = {s.employee_id: s for s in run.payslip_ids}
        ana = slips[self.employee]
        # 200 000 + 30 000 + 40 000 = 270 000 brutos; IRT isento: alimentação 30 000 e transporte 30 000.
        self.assertEqual(ana.gross, 270_000)
        self.assertEqual(ana.inss_base, 270_000)
        self.assertEqual(ana.inss_employee, 8_100)
        self.assertEqual(ana.irt_base, 210_000 - 8_100)
        self.assertEqual(ana.irt, 31_250 + 0.18 * (201_900 - 200_000))
        self.assertEqual(ana.worked_days, run.payslip_ids[0].month_days)
        bento = slips[self.teacher]
        self.assertEqual(bento.gross, 0)
        bento.lesson_count = 40
        bento.action_compute()
        self.assertEqual(bento.gross, 100_000)
        self.assertEqual(bento.irt, 0)
        run.action_close()
        self.assertEqual(run.state, 'closed')
        self.assertTrue(ana.number.startswith('2026/'))
        self.assertEqual(run.move_id.state, 'posted')
        balances = {}
        for line in run.move_id.line_ids:
            balances[line.account_id.code] = balances.get(line.account_id.code, 0.0) + line.balance
        self.assertEqual(balances['72.2'], 370_000)
        self.assertEqual(balances['72.5.2'], round(370_000 * 0.08, 2))
        self.assertAlmostEqual(balances['36.1.2'], -(ana.net + bento.net), places=2)
        self.assertAlmostEqual(balances['34.3.1'], -ana.irt, places=2)
        self.assertAlmostEqual(balances['34.9.1'], -(370_000 * 0.11), places=2)
        with self.assertRaisesRegex(UserError, 'fechada'):
            run.action_compute()
        # Exportações
        for action in (run.action_export_bank_file(), run.action_export_irt_map(), run.action_export_inss_map()):
            attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
            self.assertTrue(attachment.raw.content)
        html = self.env['ir.actions.report']._render_qweb_html('l10n_ao_payroll.report_payslip', ana.ids)[0]
        self.assertIn(b'123456789', html)
        self.assertIn('Líquido a receber'.encode(), html)

    def test_absences_overtime_sanction_advance(self):
        unjustified = self.env.ref('l10n_ao_hr.work_entry_type_ao_injustificada')
        leave = (
            self.env['hr.leave']
            .with_context(leave_skip_date_check=True)
            .create(
                {
                    'employee_id': self.employee.id,
                    'work_entry_type_id': unjustified.id,
                    'request_date_from': date(2026, 3, 3),
                    'request_date_to': date(2026, 3, 4),
                }
            )
        )
        self._approve(leave)
        self.env['l10n_ao_hr.overtime'].create(
            {'employee_id': self.employee.id, 'date': '2026-03-05', 'kind': 'extra', 'hours': 1.75}
        ).action_approve()
        self.env['l10n_ao_hr.overtime'].create(
            {'employee_id': self.employee.id, 'date': '2026-03-06', 'kind': 'extra', 'hours': 1.5}
        ).action_approve()
        sanction = self.env['l10n_ao_hr.sanction'].create(
            {
                'employee_id': self.employee.id,
                'date': '2026-03-01',
                'kind': 'reduction',
                'reduction_pct': 10,
                'months': 1,
                'reason': 'x',
            }
        )
        sanction.action_apply()
        advance = self.env['l10n_ao_payroll.advance'].create(
            {'employee_id': self.employee.id, 'date': '2026-02-20', 'amount': 90_000, 'monthly_deduction': 30_000}
        )
        advance.action_approve()
        with self.assertRaisesRegex(UserError, '3 salários'):
            self.env['l10n_ao_payroll.advance'].create(
                {'employee_id': self.employee.id, 'date': '2026-02-21', 'amount': 600_000, 'monthly_deduction': 1}
            ).action_approve()
        run = self._run()
        ana = run.payslip_ids.filtered(lambda s: s.employee_id == self.employee)
        # 2 dias de 8 h de faltas; 3,25 h extra arredondadas a 3,5 (art. 188.º); sanção de 10%.
        self.assertEqual(ana.absence_hours, 16)
        self.assertEqual(ana.overtime_hours, 3.5)
        self.assertEqual(ana.sanction_pct, 10)
        self.assertEqual(ana.sanction, 20_000)
        self.assertEqual(ana.advance_requested, 30_000)
        self.assertEqual(ana.advance, 30_000)
        run.action_close()
        self.assertEqual(advance.balance, 60_000)
        self.assertEqual(advance.state, 'approved')
        self.assertEqual(ana.advance_deduction_ids.amount, 30_000)

    def test_vacation_and_christmas(self):
        vacation = self.env.ref('l10n_ao_hr.work_entry_type_ao_ferias')
        self.env['hr.leave.allocation'].create(
            {
                'name': 'Férias 2026',
                'employee_id': self.employee.id,
                'work_entry_type_id': vacation.id,
                'number_of_days': 22,
                'date_from': '2026-01-01',
                'state': 'confirm',
            }
        ).action_approve()
        leave = (
            self.env['hr.leave']
            .with_context(leave_skip_date_check=True)
            .create(
                {
                    'employee_id': self.employee.id,
                    'work_entry_type_id': vacation.id,
                    'request_date_from': date(2026, 3, 9),
                    'request_date_to': date(2026, 3, 13),
                }
            )
        )
        self._approve(leave)
        run = self._run()
        ana = run.payslip_ids.filtered(lambda s: s.employee_id == self.employee)
        self.assertTrue(ana.vacation_subsidy)
        self.assertEqual({line.code: line.amount for line in ana.line_ids}['VACATION'], 100_000)
        run.action_close()
        self.assertEqual(self.employee.l10n_ao_payroll_vacation_subsidy_year, 2026)
        december = self._run(month=12) if date.today() >= date(2026, 12, 1) else None
        if december:
            bento = december.payslip_ids.filtered(lambda s: s.employee_id == self.teacher)
            self.assertEqual(bento.christmas_months, 12)

    def test_termination(self):
        wizard = self.env['l10n_ao_payroll.termination'].create(
            {
                'employee_id': self.employee.id,
                'date': '2026-03-31',
                'departure_reason_id': self.env.ref('l10n_ao_hr.departure_ao_objective').id,
            }
        )
        # Admissão a 10/03/2025: 1 ano e 21 dias → 1 ano (art. 311.º); art. 308.º: 1 salário por ano.
        self.assertEqual(wizard.seniority_years, 1)
        self.assertEqual(wizard.compensation_article, 'art308')
        self.assertEqual(wizard.compensation_amount, 200_000)
        self.assertEqual(wizard.months_worked, 3)
        self.assertEqual(wizard.vacation_days_proportional, 6)
        self.assertEqual(wizard.vacation_days_due, 22)
        self.assertEqual(wizard.subsidies_amount, 50_000)
        action = wizard.action_confirm()
        slip = self.env['l10n_ao_payroll.payslip'].browse(action['res_id'])
        self.assertEqual(slip.kind, 'final')
        codes = {line.code: line.amount for line in slip.line_ids}
        self.assertEqual(codes['COMPENSATION'], 200_000)
        self.assertEqual(codes['SUBSIDIES'], 50_000)
        self.assertEqual(self.employee.departure_date, date(2026, 3, 31))
        # A compensação não entra no INSS; férias e subsídios entram.
        self.assertEqual(slip.inss_base, slip.gross - 200_000)
