"""Motor de classificação do ensino superior: funções puras sobre o regulamento académico da instituição.

Média de frequência (MF): média ponderada das provas de frequência e trabalhos do semestre, na escala 0–20.
Com MF ≥ dispensa, a MF é a nota final; com admissão ≤ MF < dispensa, vai a exame; abaixo, ou sem a assiduidade
mínima, fica excluído. Com exame: nota = peso × MF + (1 − peso) × exame, e o exame tem de ter o mínimo. O recurso
substitui o exame normal; o exame especial dá a nota sozinho (positiva fixa, se o regulamento o disser); a melhoria
fica se for melhor.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

EXEMPT, ADMITTED, EXCLUDED, PENDING = 'exempt', 'admitted', 'excluded', 'pending'


@dataclass(frozen=True)
class Rules:
    pass_grade: float = 10
    exemption: float = 14  # 0 = sem dispensa
    admission: float = 7
    min_attendance: float = 75  # % de presenças; 0 = sem regra
    frequency_weight: float = 0.4  # peso da MF na nota com exame; 0 = só o exame
    exam_min: float = 10  # nota mínima no exame
    special_fixed: bool = True  # a positiva do exame especial é sempre a nota de aprovação
    appeal_for_excluded: bool = False  # o excluído pela MF ou pelas faltas pode ir ao recurso
    rounding: str = 'unit'  # 'unit' ou 'tenth'


@dataclass(frozen=True)
class Outcome:
    status: str  # situação na frequência
    final: float | None  # nota final (None: ainda por decidir)
    passed: bool
    source: str  # 'frequency', 'normal', 'appeal', 'special', 'improvement' ou '' (por decidir)


def round_grade(value, rounding='unit'):
    quantum = Decimal('0.1') if rounding == 'tenth' else Decimal('1')
    return float(Decimal(str(round(value, 6))).quantize(quantum, rounding=ROUND_HALF_UP))


def frequency_mark(items):
    """MF a partir de [(nota na escala 0–20, peso)]; None sem notas."""
    total = sum(weight for _score, weight in items)
    if not items or not total:
        return None
    return sum(score * weight for score, weight in items) / total


def frequency_status(rules, mf, attendance=None):
    if mf is None:
        return PENDING
    if attendance is not None and rules.min_attendance and attendance < rules.min_attendance:
        return EXCLUDED
    if rules.exemption and mf >= rules.exemption:
        return EXEMPT
    if mf < rules.admission:
        return EXCLUDED
    return ADMITTED


def with_exam(rules, mf, exam):
    """(nota, aprovado) com um exame: abaixo do mínimo no exame reprova, com a nota do exame."""
    if exam < rules.exam_min:
        return round_grade(exam, rules.rounding), False
    weight = rules.frequency_weight
    grade = round_grade(weight * mf + (1 - weight) * exam, rules.rounding)
    return grade, grade >= rules.pass_grade


def resolve(rules, mf, attendance=None, *, normal=None, appeal=None, special=None, improvement=None):
    status = frequency_status(rules, mf, attendance)
    if special is not None:
        passed = special >= rules.pass_grade
        final = rules.pass_grade if passed and rules.special_fixed else round_grade(special, rules.rounding)
        return Outcome(status, final, passed, 'special')
    final, passed, source = None, False, ''
    if status == EXEMPT:
        final, passed, source = round_grade(mf, rules.rounding), True, 'frequency'
    elif status == ADMITTED or (status == EXCLUDED and rules.appeal_for_excluded and appeal is not None):
        if appeal is not None:
            final, passed = with_exam(rules, mf, appeal)
            source = 'appeal'
        elif normal is not None and status == ADMITTED:
            final, passed = with_exam(rules, mf, normal)
            source = 'normal'
    elif status == EXCLUDED:
        final, passed, source = round_grade(mf, rules.rounding), False, 'frequency'
    if passed and improvement is not None:
        better = round_grade(improvement, rules.rounding)
        if better > final:
            final, source = better, 'improvement'
    return Outcome(status, final, passed, source)
