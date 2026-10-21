"""Motor de cálculo da folha de salários angolana, sem acesso à base de dados.

Fontes: Lei Geral do Trabalho (Lei n.º 12/23), Código do IRT (Lei n.º 18/14, com a Lei n.º 28/20 e a tabela da
Lei n.º 14/25) e Decreto Presidencial n.º 227/18 (INSS). As regras aplicadas estão em
docs/referencias/salarios/IRT-INSS.md e secped-folha.md.
"""

from dataclasses import dataclass, field


def round2(value):
    return round(value + 0.0, 2)


def hourly_rate(monthly_salary, weekly_hours):
    """LGT, art. 237.º, n.º 7: S/H = (Sm × 12) / (52 × Hs)."""
    if not monthly_salary or not weekly_hours:
        return 0.0
    return monthly_salary * 12 / (52 * weekly_hours)


def compute_irt(base, brackets):
    """IRT do grupo A: parcela fixa + taxa × (base − excesso), no escalão em que a base cai.

    ``brackets``: lista de (limite inferior exclusivo, limite superior inclusivo ou None, parcela fixa, taxa).
    """
    if base <= 0 or not brackets:
        return 0.0
    for lower, upper, fixed, rate in brackets:
        if base > lower and (upper is None or base <= upper):
            return round2(fixed + rate * (base - lower))
    return 0.0


@dataclass
class Component:
    code: str
    name: str
    amount: float
    subject_irt: bool = True
    subject_inss: bool = True
    irt_exempt_cap: float = 0.0  # parte isenta de IRT (alimentação e transporte até 30 000 Kz)
    proportional: bool = True  # multiplicado pela fracção do mês


@dataclass
class Settings:
    inss_employee_pct: float = 3.0
    inss_employer_pct: float = 8.0
    vacation_subsidy_pct: float = 50.0
    christmas_subsidy_pct: float = 50.0
    overtime_first_pct: float = 50.0  # até 30 h por mês (art. 188.º)
    overtime_after_pct: float = 75.0
    overtime_threshold_hours: float = 30.0
    night_pct: float = 20.0
    rest_day_pct: float = 75.0
    holiday_pct: float = 100.0
    advance_cap_pct: float = 25.0  # art. 248.º, n.º 7
    irt_brackets: list = field(default_factory=list)


@dataclass
class Inputs:
    base_salary: float = 0.0
    weekly_hours: float = 44.0
    fraction: float = 1.0  # dias úteis com contrato / dias úteis do mês
    worked_days: int = 0
    month_days: int = 0
    components: list = field(default_factory=list)
    lesson_count: float = 0.0
    lesson_rate: float = 0.0
    overtime_hours: float = 0.0  # já arredondadas (art. 188.º, n.º 4)
    night_hours: float = 0.0
    rest_day_hours: float = 0.0
    holiday_hours: float = 0.0
    absence_hours: float = 0.0  # faltas não pagas, em horas
    sanction_pct: float = 0.0
    vacation_subsidy: bool = False
    christmas_months: int = 0  # 0 = sem subsídio de Natal
    advance_requested: float = 0.0
    extra_lines: list = field(default_factory=list)  # [(code, name, amount, subject_irt, subject_inss)]


@dataclass
class Line:
    kind: str  # earning | deduction | employer
    code: str
    name: str
    amount: float
    quantity: float = 1.0
    rate: float = 0.0
    subject_irt: bool = False
    subject_inss: bool = False
    irt_base_part: float = 0.0
    inss_base_part: float = 0.0


class Result:
    def __init__(self):
        self.lines = []
        self.gross = 0.0
        self.irt_base = 0.0
        self.irt = 0.0
        self.inss_base = 0.0
        self.inss_employee = 0.0
        self.inss_employer = 0.0
        self.absences = 0.0
        self.sanction = 0.0
        self.advance = 0.0
        self.deductions = 0.0
        self.net = 0.0
        self.hourly_rate = 0.0

    def earning(
        self, code, name, amount, *, quantity=1.0, rate=0.0, subject_irt=True, subject_inss=True, irt_exempt_cap=0.0
    ):
        amount = round2(amount)
        if not amount:
            return None
        irt_part = amount if subject_irt else round2(max(0.0, amount - irt_exempt_cap))
        inss_part = amount if subject_inss else 0.0
        line = Line('earning', code, name, amount, quantity, rate, subject_irt, subject_inss, irt_part, inss_part)
        self.lines.append(line)
        return line

    def deduction(self, code, name, amount, *, quantity=1.0, rate=0.0):
        amount = round2(amount)
        if not amount:
            return None
        line = Line('deduction', code, name, amount, quantity, rate)
        self.lines.append(line)
        return line


def compute(inputs: Inputs, settings: Settings) -> Result:
    """Folha de um trabalhador num mês. Ordem: bruto → faltas → sanção → INSS → IRT → adiantamento."""
    result = Result()
    fraction = max(0.0, min(inputs.fraction, 1.0))
    base = round2(inputs.base_salary * fraction)
    rate = hourly_rate(inputs.base_salary, inputs.weekly_hours)
    result.hourly_rate = rate
    if base:
        name = 'Salário base'
        if fraction < 1 and inputs.month_days:
            name = f'Salário base ({inputs.worked_days} de {inputs.month_days} dias úteis)'
        result.earning('BASE', name, base)
    if inputs.lesson_count and inputs.lesson_rate:
        result.earning(
            'LESSONS',
            'Tempos lectivos',
            inputs.lesson_count * inputs.lesson_rate,
            quantity=inputs.lesson_count,
            rate=inputs.lesson_rate,
        )
    for component in inputs.components:
        amount = component.amount * (fraction if component.proportional else 1.0)
        result.earning(
            component.code,
            component.name,
            amount,
            subject_irt=component.subject_irt,
            subject_inss=component.subject_inss,
            irt_exempt_cap=component.irt_exempt_cap,
        )
    # Trabalho extraordinário (art. 188.º): +50% até 30 h/mês, +75% acima; nocturno +20% (art. 182.º);
    # dia de descanso +75% (art. 194.º); feriado: +100% (art. 200.º, um dia de salário por dia trabalhado).
    first = min(inputs.overtime_hours, settings.overtime_threshold_hours)
    after = max(inputs.overtime_hours - settings.overtime_threshold_hours, 0.0)
    factor_first = 1 + settings.overtime_first_pct / 100
    factor_after = 1 + settings.overtime_after_pct / 100
    if first:
        result.earning(
            'OT50',
            f'Horas extraordinárias (+{settings.overtime_first_pct:g}%)',
            first * rate * factor_first,
            quantity=first,
            rate=rate * factor_first,
        )
    if after:
        result.earning(
            'OT75',
            f'Horas extraordinárias (+{settings.overtime_after_pct:g}%)',
            after * rate * factor_after,
            quantity=after,
            rate=rate * factor_after,
        )
    if inputs.night_hours:
        night_rate = rate * settings.night_pct / 100
        result.earning(
            'NIGHT',
            f'Trabalho nocturno (+{settings.night_pct:g}%)',
            inputs.night_hours * night_rate,
            quantity=inputs.night_hours,
            rate=night_rate,
        )
    if inputs.rest_day_hours:
        rest_rate = rate * (1 + settings.rest_day_pct / 100)
        result.earning(
            'REST',
            f'Dia de descanso (+{settings.rest_day_pct:g}%)',
            inputs.rest_day_hours * rest_rate,
            quantity=inputs.rest_day_hours,
            rate=rest_rate,
        )
    if inputs.holiday_hours:
        holiday_rate = rate * (1 + settings.holiday_pct / 100)
        result.earning(
            'HOLIDAY',
            f'Feriado (+{settings.holiday_pct:g}%)',
            inputs.holiday_hours * holiday_rate,
            quantity=inputs.holiday_hours,
            rate=holiday_rate,
        )
    # Subsídios (art. 238.º): férias sem INSS (DP 227/18, art. 6.º); Natal proporcional aos meses do ano.
    if inputs.vacation_subsidy:
        result.earning(
            'VACATION',
            'Subsídio de férias',
            inputs.base_salary * settings.vacation_subsidy_pct / 100,
            subject_inss=False,
        )
    if inputs.christmas_months:
        months = max(0, min(inputs.christmas_months, 12))
        result.earning(
            'CHRISTMAS',
            f'Subsídio de Natal ({months}/12)' if months < 12 else 'Subsídio de Natal',
            inputs.base_salary * settings.christmas_subsidy_pct / 100 * months / 12,
        )
    for code, name, amount, subject_irt, subject_inss in inputs.extra_lines:
        result.earning(code, name, amount, subject_irt=subject_irt, subject_inss=subject_inss)

    earnings = [line for line in result.lines if line.kind == 'earning']
    result.gross = round2(sum(line.amount for line in earnings))
    irt_base = sum(line.irt_base_part for line in earnings)
    inss_base = sum(line.inss_base_part for line in earnings)
    # Faltas (art. 240.º): horas × salário-hora, até ao salário base do mês.
    if inputs.absence_hours and rate:
        result.absences = round2(min(inputs.absence_hours * rate, base))
        result.deduction('ABSENCE', 'Faltas', result.absences, quantity=inputs.absence_hours, rate=rate)
        irt_base -= result.absences
        inss_base -= result.absences
    # Sanção disciplinar (art. 87.º, n.º 2): até 20% do salário base.
    if inputs.sanction_pct:
        pct = min(inputs.sanction_pct, 20.0)
        result.sanction = round2(min(base * pct / 100, max(base - result.absences, 0.0)))
        result.deduction('SANCTION', f'Sanção disciplinar ({pct:g}%)', result.sanction)
        irt_base -= result.sanction
        inss_base -= result.sanction
    result.inss_base = round2(max(inss_base, 0.0))
    result.inss_employee = round2(result.inss_base * settings.inss_employee_pct / 100)
    result.inss_employer = round2(result.inss_base * settings.inss_employer_pct / 100)
    if result.inss_employee:
        result.deduction(
            'INSS',
            f'Segurança Social ({settings.inss_employee_pct:g}%)',
            result.inss_employee,
            rate=settings.inss_employee_pct,
        )
    # IRT (CIRT, art. 7.º): base = rendimento sujeito − INSS do trabalhador.
    result.irt_base = round2(max(irt_base - result.inss_employee, 0.0))
    result.irt = compute_irt(result.irt_base, settings.irt_brackets)
    if result.irt:
        result.deduction('IRT', 'IRT (grupo A)', result.irt)
    # Adiantamentos (art. 248.º, n.º 7): até 25% do líquido depois dos descontos obrigatórios.
    if inputs.advance_requested:
        available = max(result.gross - result.absences - result.sanction - result.inss_employee - result.irt, 0.0)
        cap = round2(available * settings.advance_cap_pct / 100)
        result.advance = round2(min(inputs.advance_requested, cap))
        if result.advance:
            result.deduction('ADVANCE', 'Adiantamento', result.advance)
    result.deductions = round2(sum(line.amount for line in result.lines if line.kind == 'deduction'))
    result.net = round2(result.gross - result.deductions)
    return result


def seniority_compensation(reason, base_salary, years):
    """Compensação na cessação (LGT, arts. 307.º a 310.º), em salários-base."""
    if reason in ('art307', 'art309'):
        return round2(0.5 * base_salary * years)
    if reason == 'art308':
        return round2(base_salary * min(years, 5) + 0.5 * base_salary * max(years - 5, 0))
    if reason == 'art310':
        return round2(max(base_salary * years, 3 * base_salary))
    if reason == 'notice':  # falta de aviso prévio na não renovação (art. 17.º): 30 dias de salário
        return round2(base_salary)
    return 0.0
