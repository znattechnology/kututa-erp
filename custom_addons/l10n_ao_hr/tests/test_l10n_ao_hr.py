from datetime import date, datetime

from odoo.addons.l10n_ao_hr.models.hr_employee import seniority_years
from odoo.addons.l10n_ao_hr.models.l10n_ao_hr_overtime import round_overtime_hours
from odoo.addons.l10n_ao_hr.tools.holidays import easter, public_holidays
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ao')
class TestL10nAoHr(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create(
            {
                'name': 'Escola Teste, Lda',
                'country_id': cls.env.ref('base.ao').id,
                'currency_id': cls.env.ref('base.AOA').id,
            }
        )
        cls.env.user.company_ids |= cls.company
        cls.env.user.company_id = cls.company
        cls.calendar = cls.env.ref('l10n_ao_hr.resource_calendar_ao_44h')
        cls.employee = cls.env['hr.employee'].create(
            {
                'name': 'Maria Teste',
                'company_id': cls.company.id,
                'resource_calendar_id': cls.calendar.id,
                'contract_date_start': '2026-01-05',
                'wage': 200_000,
            }
        )

    def test_public_holidays(self):
        self.assertEqual(easter(2026), date(2026, 4, 5))
        holidays = {day: name for day, name, _bridge in public_holidays(2026)}
        self.assertEqual(holidays[date(2026, 2, 17)], 'Dia do Carnaval')
        self.assertEqual(holidays[date(2026, 4, 3)], 'Sexta-feira Santa')
        # Pontes: 1 de Janeiro (quinta) → 2 de Janeiro; Carnaval (terça) → 16 de Fevereiro;
        # 17 de Setembro (quinta) → 18.
        self.assertIn(date(2026, 1, 2), holidays)
        self.assertIn(date(2026, 2, 16), holidays)
        self.assertIn(date(2026, 9, 18), holidays)
        self.assertEqual(len([d for d in holidays if not holidays[d].startswith('Ponte')]), 12)
        # Feriado ao fim-de-semana não se transfere: 8 de Março de 2026 é domingo.
        self.assertNotIn(date(2026, 3, 9), holidays)
        self.company._l10n_ao_hr_generate_public_holidays(2026)
        leaves = self.env['resource.calendar.leaves'].search(
            [('company_id', '=', self.company.id), ('resource_id', '=', False)]
        )
        self.assertEqual(len(leaves), 15 + 2)  # 12 feriados + 3 pontes + 2 tardes
        self.company._l10n_ao_hr_generate_public_holidays(2026)
        self.assertEqual(len(self.env['resource.calendar.leaves'].search([('company_id', '=', self.company.id)])), 17)

    def test_seniority_and_rounding(self):
        self.assertEqual(seniority_years(date(2024, 1, 1), date(2026, 5, 2)), 3)
        self.assertEqual(seniority_years(date(2024, 1, 1), date(2026, 3, 1)), 2)
        self.assertEqual(seniority_years(date(2026, 1, 1), date(2026, 6, 5)), 1)
        self.assertEqual(seniority_years(date(2026, 1, 1), date(2026, 3, 2)), 0)
        self.assertEqual(round_overtime_hours(2.2), 2.0)
        self.assertEqual(round_overtime_hours(2.25), 2.5)
        self.assertEqual(round_overtime_hours(2.74), 2.5)
        self.assertEqual(round_overtime_hours(2.75), 3.0)

    def test_contract_rules(self):
        version = self.employee.version_id
        self.assertEqual(version.l10n_ao_weekly_hours, 44.0)
        # Primeiro contrato indeterminado: período experimental de 60 dias por omissão.
        self.assertEqual(version.trial_date_end, date(2026, 3, 5))
        with self.assertRaisesRegex(ValidationError, 'art. 18'):
            version.trial_date_end = date(2026, 6, 30)
        version.l10n_ao_is_director = True
        version.trial_date_end = date(2026, 6, 30)
        # Contrato a termo sem causa é recusado; com causa e acima do máximo também.
        with self.assertRaisesRegex(ValidationError, 'art. 15'):
            version.write(
                {'l10n_ao_contract_type': 'fixed', 'contract_date_end': '2026-12-31', 'trial_date_end': False}
            )
        with self.assertRaisesRegex(ValidationError, 'art. 16'):
            version.write(
                {
                    'l10n_ao_contract_type': 'fixed',
                    'l10n_ao_fixed_term_reason': 'd',
                    'contract_date_end': '2026-12-31',
                    'trial_date_end': False,
                }
            )
        version.write(
            {
                'l10n_ao_contract_type': 'fixed',
                'l10n_ao_fixed_term_reason': 'b',
                'contract_date_end': '2026-06-30',
                'trial_date_end': False,
            }
        )
        self.assertEqual(version.l10n_ao_term_months, 6)
        # Renovação com a mesma causa (b: 12 meses): a duração acumula.
        renewal = (
            self.env['hr.version']
            .with_context(l10n_ao_skip_trial=True)
            .create(
                {
                    'employee_id': self.employee.id,
                    'date_version': '2026-07-01',
                    'contract_date_start': '2026-07-01',
                    'contract_date_end': '2026-09-30',
                    'l10n_ao_contract_type': 'fixed',
                    'l10n_ao_fixed_term_reason': 'b',
                }
            )
        )
        self.assertEqual(renewal.l10n_ao_renewal_count, 1)
        self.assertEqual(renewal.l10n_ao_term_months, 9)
        with self.assertRaisesRegex(ValidationError, 'art. 16'):
            renewal.contract_date_end = '2027-01-31'

    def test_overtime_limits(self):
        Overtime = self.env['l10n_ao_hr.overtime']
        first = Overtime.create({'employee_id': self.employee.id, 'date': '2026-03-02', 'kind': 'extra', 'hours': 2})
        first.action_approve()
        second = Overtime.create({'employee_id': self.employee.id, 'date': '2026-03-02', 'kind': 'extra', 'hours': 1})
        with self.assertRaisesRegex(ValidationError, 'art. 185'):
            second.action_approve()
        second.authorized_by_igt = True
        second.action_approve()
        # O trabalho nocturno não entra no limite.
        Overtime.create(
            {'employee_id': self.employee.id, 'date': '2026-03-02', 'kind': 'night', 'hours': 3}
        ).action_approve()

    def test_sanction(self):
        sanction = self.env['l10n_ao_hr.sanction'].create(
            {
                'employee_id': self.employee.id,
                'date': '2026-03-10',
                'kind': 'reduction',
                'reduction_pct': 10,
                'months': 2,
                'reason': 'Faltas',
            }
        )
        with self.assertRaisesRegex(ValidationError, '20%'):
            sanction.reduction_pct = 25
        sanction.action_apply()
        self.assertEqual(sanction._reduction_in_month(2026, 3), 10)
        self.assertEqual(sanction._reduction_in_month(2026, 4), 10)
        self.assertEqual(sanction._reduction_in_month(2026, 5), 0)

    def test_leave_limits(self):
        legal = self.env.ref('l10n_ao_hr.work_entry_type_ao_obrigacao_legal')
        Leave = self.env['hr.leave'].with_context(leave_skip_date_check=True)

        def leave(start, end):
            record = Leave.create(
                {
                    'employee_id': self.employee.id,
                    'work_entry_type_id': legal.id,
                    'request_date_from': start,
                    'request_date_to': end,
                }
            )
            record.action_approve()
            return record

        leave(date(2026, 3, 2), date(2026, 3, 3))  # 2 dias: o máximo do mês
        with self.assertRaisesRegex(ValidationError, 'máximo por mês'):
            leave(date(2026, 3, 4), date(2026, 3, 4))
        wedding = self.env.ref('l10n_ao_hr.work_entry_type_ao_casamento')
        with self.assertRaisesRegex(ValidationError, 'máximo por evento'):
            Leave.create(
                {
                    'employee_id': self.employee.id,
                    'work_entry_type_id': wedding.id,
                    'request_date_from': date(2026, 4, 6),
                    'request_date_to': date(2026, 4, 17),
                }
            ).action_approve()
        unjustified = self.env.ref('l10n_ao_hr.work_entry_type_ao_injustificada')
        for day in (6, 7, 8, 9):
            Leave.create(
                {
                    'employee_id': self.employee.id,
                    'work_entry_type_id': unjustified.id,
                    'request_date_from': date(2026, 4, day),
                    'request_date_to': date(2026, 4, day),
                }
            ).action_approve()
        self.assertTrue(self.employee.activity_ids.filtered(lambda a: a.summary == 'Faltas injustificadas'))
        self.assertIsInstance(datetime.now(), datetime)
