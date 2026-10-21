"""Casos dourados do motor de cálculo (os mesmos do secPed-Express e da tabela da Lei n.º 14/25)."""

from odoo.addons.l10n_ao_payroll.tools.payroll_calc import (
    Component,
    Inputs,
    Settings,
    compute,
    compute_irt,
    hourly_rate,
    seniority_compensation,
)
from odoo.tests import BaseCase, tagged

BRACKETS = [
    (0, 150000, 0, 0),
    (150000, 200000, 12500, 0.16),
    (200000, 300000, 31250, 0.18),
    (300000, 500000, 49250, 0.19),
    (500000, 1000000, 87250, 0.20),
    (1000000, 1500000, 187250, 0.21),
    (1500000, 2000000, 292250, 0.22),
    (2000000, 2500000, 402250, 0.23),
    (2500000, 5000000, 517250, 0.24),
    (5000000, 10000000, 1117250, 0.245),
    (10000000, None, 2342250, 0.25),
]


@tagged('post_install', '-at_install', 'l10n_ao')
class TestPayrollCalc(BaseCase):
    def settings(self):
        return Settings(irt_brackets=BRACKETS)

    def test_hourly_rate(self):
        self.assertAlmostEqual(hourly_rate(220_000, 44), 1153.85, places=2)
        self.assertEqual(hourly_rate(0, 44), 0.0)
        self.assertEqual(hourly_rate(100_000, 0), 0.0)

    def test_irt_table(self):
        for base, expected in [
            (0, 0), (100_000, 0), (150_000, 0), (150_001, 12_500.16), (160_000, 14_100), (180_000, 17_300),
            (200_000, 20_500), (250_000, 40_250), (300_000, 49_250), (400_000, 68_250), (12_000_000, 2_842_250),
        ]:  # fmt: skip
            self.assertAlmostEqual(compute_irt(base, BRACKETS), expected, places=2, msg=str(base))
        # Descontinuidade legislada: 200 000 → 20 500; 200 001 → 31 250,18.
        self.assertAlmostEqual(compute_irt(200_001, BRACKETS) - compute_irt(200_000, BRACKETS), 10_750.18, places=2)

    def test_regular_employee(self):
        result = compute(Inputs(base_salary=200_000), self.settings())
        self.assertEqual(result.gross, 200_000)
        self.assertEqual(result.inss_employee, 6_000)
        self.assertEqual(result.inss_employer, 16_000)
        self.assertEqual(result.irt_base, 194_000)
        self.assertEqual(result.irt, 19_540)
        self.assertEqual(result.net, 174_460)

    def test_lessons_and_mixed(self):
        result = compute(Inputs(base_salary=0, lesson_count=80, lesson_rate=2_500), self.settings())
        self.assertEqual(result.gross, 200_000)
        self.assertEqual(result.irt_base, 194_000)
        mixed = compute(Inputs(base_salary=150_000, lesson_count=20, lesson_rate=2_500), self.settings())
        self.assertEqual(mixed.gross, 200_000)
        self.assertEqual(mixed.irt, 19_540)

    def test_meal_allowance(self):
        meal = Component(
            'MEAL', 'Subsídio de alimentação', 30_000, subject_irt=False, subject_inss=True, irt_exempt_cap=30_000
        )
        result = compute(Inputs(base_salary=100_000, components=[meal]), self.settings())
        self.assertEqual(result.gross, 130_000)
        # DP 227/18: o subsídio de alimentação contribui para o INSS na totalidade.
        self.assertEqual(result.inss_base, 130_000)
        self.assertEqual(result.irt_base, 100_000 - 3_900)
        self.assertEqual(result.irt, 0)
        self.assertEqual(result.net, 126_100)
        # Acima dos 30 000, o excedente é tributado em IRT.
        big = Component('MEAL', 'Subsídio de alimentação', 200_000, subject_irt=False, irt_exempt_cap=30_000)
        result = compute(Inputs(base_salary=200_000, components=[big]), self.settings())
        self.assertEqual(result.gross, 400_000)
        self.assertEqual(result.inss_base, 400_000)
        self.assertEqual(result.irt_base, 370_000 - 12_000)

    def test_overtime(self):
        result = compute(Inputs(base_salary=200_000, overtime_hours=35), self.settings())
        lines = {line.code: line for line in result.lines}
        self.assertAlmostEqual(result.hourly_rate, 1_048.95, places=2)
        self.assertAlmostEqual(lines['OT50'].amount, 47_202.80, places=2)
        self.assertAlmostEqual(lines['OT75'].amount, 9_178.32, places=2)
        night = compute(Inputs(base_salary=200_000, night_hours=10), self.settings())
        self.assertAlmostEqual({line.code: line for line in night.lines}['NIGHT'].amount, 2_097.90, places=2)

    def test_absences_sanction_and_advance(self):
        result = compute(Inputs(base_salary=220_000, absence_hours=17.6), self.settings())
        self.assertAlmostEqual(result.absences, 20_307.69, places=2)
        self.assertAlmostEqual(result.inss_base, 220_000 - 20_307.69, places=2)
        sanction = compute(Inputs(base_salary=200_000, sanction_pct=20), self.settings())
        self.assertEqual(sanction.sanction, 40_000)
        self.assertEqual(sanction.inss_base, 160_000)
        self.assertEqual(sanction.irt, 13_332)
        self.assertEqual(sanction.net, 141_868)
        capped = compute(Inputs(base_salary=200_000, sanction_pct=50), self.settings())
        self.assertEqual(capped.sanction, 40_000)
        advance = compute(Inputs(base_salary=100_000, advance_requested=90_000), self.settings())
        self.assertEqual(advance.advance, 24_250)
        self.assertEqual(advance.net, 72_750)

    def test_subsidies(self):
        vacation = compute(Inputs(base_salary=200_000, vacation_subsidy=True), self.settings())
        lines = {line.code: line for line in vacation.lines}
        self.assertEqual(lines['VACATION'].amount, 100_000)
        self.assertEqual(vacation.gross, 300_000)
        # O subsídio de férias não entra no INSS (DP 227/18, art. 13.º, n.º 3, al. b)) mas entra no IRT.
        self.assertEqual(vacation.inss_base, 200_000)
        self.assertEqual(vacation.irt_base, 300_000 - 6_000)
        christmas = compute(Inputs(base_salary=200_000, christmas_months=6), self.settings())
        self.assertEqual({line.code: line for line in christmas.lines}['CHRISTMAS'].amount, 50_000)
        self.assertEqual(christmas.inss_base, 250_000)

    def test_holiday_and_owed_lines(self):
        # Feriado trabalhado: o salário já paga o dia, acresce um dia de salário (art. 200.º, n.º 2).
        holiday = compute(Inputs(base_salary=200_000, holiday_hours=8), self.settings())
        self.assertAlmostEqual({line.code: line for line in holiday.lines}['HOLIDAY'].amount, 8_391.61, places=2)
        # Linha negativa (aviso prévio devido pelo trabalhador): desconto fora do IRT e do INSS.
        owed = compute(
            Inputs(base_salary=200_000, extra_lines=[('NOTICE', 'Aviso prévio', -50_000, False, False)]),
            self.settings(),
        )
        self.assertEqual(owed.gross, 200_000)
        self.assertEqual(owed.inss_base, 200_000)
        self.assertEqual({line.code: line.kind for line in owed.lines}['NOTICE'], 'deduction')
        self.assertEqual(owed.net, 200_000 - 6_000 - owed.irt - 50_000)

    def test_exempt_cap_by_code(self):
        # Duas linhas de alimentação partilham o limite de 30 000 Kz isentos de IRT.
        meals = [
            Component('MEAL', 'Alimentação', 20_000, subject_irt=False, irt_exempt_cap=30_000),
            Component('MEAL', 'Alimentação (turno)', 20_000, subject_irt=False, irt_exempt_cap=30_000),
        ]
        result = compute(Inputs(base_salary=200_000, components=meals), self.settings())
        self.assertEqual(result.irt_base, 200_000 + 10_000 - result.inss_employee)

    def test_prorated_base_and_reference(self):
        # Aumento a meio do mês: o salário base vem já rateado; o salário-hora usa o salário de referência.
        result = compute(
            Inputs(base_salary=300_000, base_amount=250_000, reference_salary=300_000, absence_hours=8),
            self.settings(),
        )
        self.assertEqual({line.code: line.amount for line in result.lines}['BASE'], 250_000)
        self.assertAlmostEqual(result.hourly_rate, hourly_rate(300_000, 44), places=6)
        teacher = compute(
            Inputs(lesson_count=10, lesson_rate=3_000, reference_salary=120_000, vacation_subsidy=True),
            self.settings(),
        )
        self.assertEqual({line.code: line.amount for line in teacher.lines}['VACATION'], 60_000)

    def test_fraction_of_month(self):
        result = compute(Inputs(base_salary=100_000, fraction=11 / 22, worked_days=11, month_days=22), self.settings())
        self.assertEqual(result.gross, 50_000)
        self.assertEqual(result.lines[0].name, 'Salário base (11 de 22 dias úteis)')

    def test_identities(self):
        for base in (123_456.78, 87_654.32, 250_000.01, 99_999.99, 45_678.90):
            result = compute(
                Inputs(
                    base_salary=base,
                    overtime_hours=7,
                    night_hours=3.5,
                    components=[Component('BONUS', 'Prémio', 3_333.33)],
                ),
                self.settings(),
            )
            earnings = sum(line.amount for line in result.lines if line.kind == 'earning')
            self.assertAlmostEqual(result.gross, earnings, places=2)
            self.assertAlmostEqual(result.net, result.gross - result.deductions, places=2)
            for line in result.lines:
                self.assertEqual(round(line.amount, 2), line.amount)

    def test_compensation(self):
        self.assertEqual(seniority_compensation('art307', 200_000, 4), 400_000)
        self.assertEqual(seniority_compensation('art308', 200_000, 3), 600_000)
        self.assertEqual(seniority_compensation('art308', 200_000, 8), 1_300_000)
        self.assertEqual(seniority_compensation('art309', 150_000, 6), 450_000)
        self.assertEqual(seniority_compensation('art310', 200_000, 7), 1_400_000)
        self.assertEqual(seniority_compensation('art310', 200_000, 1), 600_000)
        self.assertEqual(seniority_compensation('none', 200_000, 1), 0)
