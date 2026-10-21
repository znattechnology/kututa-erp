"""Motor de cálculo das classificações escolares angolanas, sem acesso à base de dados.

Ensino geral, primário e magistério: Decreto Executivo n.º 424/25 (Regulamento de Avaliação das Aprendizagens),
Anexo III. Técnico-profissional: Despacho n.º 60/08 (CF cumulativa, CA = 60% CF + 40% PG). Regras e divergências
face ao secPed-Express em docs/referencias/academico/secped-avaliacao-presencas.md.
"""

import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

GENERAL = 'general'
TECHNICAL = 'technical'

PROMOTED = 'promoted'
GRADUATED = 'graduated'
CONDITIONAL = 'conditional'
EXAM = 'exam'
RETAINED = 'retained'
PENDING = 'pending'

GLOBAL_EXAM_CF_WEIGHT = 0.6
GLOBAL_EXAM_MIN_HOURS = 3
# Sem prova global: componente técnica/prática e estágio, e as disciplinas práticas (Despacho 60/08, art. 18.º).
NO_GLOBAL_EXAM_WORDS = (
    'educacao fisica', 'ed fisica', 'ed. fisica', 'informatica', 'desenho', 'pratica', 'laborator', 'oficina',
)  # fmt: skip
NO_GLOBAL_EXAM_COMPONENTS = ('technical', 'internship')


def round_units(value):
    """Arredondamento às unidades, metade para cima (9,5 → 10), como manda o art. 16.º do RAA."""
    if value is None:
        return None
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def rounder(mode):
    if mode == 'decimal2':
        return lambda value: (
            None if value is None else float(Decimal(str(value)).quantize(Decimal('0.01'), ROUND_HALF_UP))
        )
    return round_units


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def normalise(score, max_score, scale_max):
    """Nota numa avaliação com cotação menor do que a escala, convertida para a escala (nunca se reduz)."""
    if score is None:
        return None
    if max_score and max_score < scale_max:
        return score / max_score * scale_max
    return score


def weighted_mean(items):
    """[(nota, peso)] → média ponderada; sem pesos, média simples."""
    items = [(score, weight or 0) for score, weight in items if score is not None]
    if not items:
        return None
    total = sum(weight for _score, weight in items)
    if not total:
        return mean([score for score, _weight in items])
    return sum(score * weight for score, weight in items) / total


# ----------------------------------------------------------------------------
# Ensino geral (Anexo III do RAA)
# ----------------------------------------------------------------------------
def general_mt(mac, npt, mac_weight=0.5, round_fn=round_units):
    """MT = (MACT + NPT) / 2 nas classes de transição. Sem prova trimestral não há média do trimestre."""
    if mac is None or npt is None:
        return None
    return round_fn(mac * mac_weight + npt * (1 - mac_weight))


def exam_class_mt3(previous_mts, mac3, round_fn=round_units):
    """Classes de exame nacional, III trimestre: MT3 = (MT1 + MT2 + MACT3) / 3, sem prova trimestral."""
    if mac3 is None:
        return None
    return round_fn(mean([*previous_mts, mac3]))


def general_final(mts, round_fn=round_units):
    """Média final da disciplina: MFD = (MT1 + MT2 + MT3) / 3 (as médias que existam)."""
    value = mean(mts)
    return round_fn(value) if value is not None else None


def national_final(mt3, national, weight, round_fn=round_units):
    """MFED = 0,6 × MT3 + 0,4 × EN (6.ª e 9.ª) ou 0,5 × MT3 + 0,5 × EN (12.ª)."""
    if mt3 is None or national is None:
        return None
    return round_fn(mt3 * (1 - weight) + national * weight)


# ----------------------------------------------------------------------------
# Técnico-profissional (Despacho 60/08)
# ----------------------------------------------------------------------------
def technical_ct(npp, npt, round_fn=round_units):
    """Classificação do trimestre: média das partes existentes (NPP, NPT)."""
    value = mean([npp, npt])
    return round_fn(value) if value is not None else None


def cumulative(cts, round_fn=round_units):
    """CT1 = MT1, CT2 = (CT1 + MT2)/2, CF = CT3 = (CT2 + MT3)/2, arredondando em cada passo; um trimestre sem nota
    deixa o acumulado como está."""
    running = []
    acc = None
    for ct in cts:
        if ct is not None:
            acc = round_fn(ct) if acc is None else round_fn((acc + ct) / 2)
        running.append(acc)
    return running


def frequency_classification(cts, regime, round_fn=round_units, imported=None):
    """CF do ano: a importada (pauta assinada) vence; no técnico é cumulativa, no geral é a média."""
    if imported is not None:
        return round_fn(imported)
    if regime == TECHNICAL:
        running = cumulative(cts, round_fn)
        return running[-1] if running else None
    return general_final(cts, round_fn)


def technical_ca(cf, pg, eligible, round_fn=round_units, cf_weight=GLOBAL_EXAM_CF_WEIGHT):
    """CA = 60% CF + 40% PG nas disciplinas com prova global; CA = CF nas outras (ou sem PG lançada)."""
    if cf is None:
        return None
    if not eligible or pg is None:
        return round_fn(cf)
    return round_fn(cf * cf_weight + pg * (1 - cf_weight))


def _plain(text):
    text = unicodedata.normalize('NFD', text or '')
    return ''.join(char for char in text if unicodedata.category(char) != 'Mn').lower()


def has_global_exam(weekly_hours, component, name, code=''):
    """Prova global só com 3 ou mais tempos semanais, fora da componente técnica/prática e das disciplinas práticas."""
    if (weekly_hours or 0) < GLOBAL_EXAM_MIN_HOURS or component in NO_GLOBAL_EXAM_COMPONENTS:
        return False
    plain = _plain(f'{name} {code}')
    return not any(word in plain for word in NO_GLOBAL_EXAM_WORDS)


def with_adjustment(base, points, scale_max=20):
    """Bonificação do conselho de turma, com tecto no máximo da escala."""
    if base is None:
        return None
    return min(scale_max, base + (points or 0))


def multi_year_final(annuals, round_fn=round_units):
    """CFD de uma disciplina plurianual: média das classificações anuais, arredondada."""
    return general_final(annuals, round_fn)


def course_final(pc, pap=None, internship=None, formula='dec90'):
    """Classificação final do curso: (2 × PC + PAP) / 3 (Decreto 90/04) ou (4 × PC + EC + PAP) / 6 (com estágio)."""
    if pc is None:
        return None
    if formula == 'internship' and pap is not None and internship is not None:
        return round_units((4 * pc + internship + pap) / 6)
    if pap is not None:
        return round_units((2 * pc + pap) / 3)
    return round_units(pc)


# ----------------------------------------------------------------------------
# Decisão de fim de ano
# ----------------------------------------------------------------------------
@dataclass
class Rules:
    pass_grade: float = 10
    floor: float | None = 7  # nota mínima das negativas toleradas na transição
    conditional_max: int = 0  # negativas toleradas (0 = classe terminal ou sem tolerância)
    forbidden_pairs: list = field(default_factory=list)  # [(código, código)] que não podem ser ambas negativas
    exam_max: int = 0  # negativas que ainda admitem exame de recurso
    auto_promote: bool = False
    terminal: bool = False


@dataclass
class Decision:
    status: str
    negatives: list
    reason: str = ''


def _pair_violated(codes, pairs):
    return any(first in codes and second in codes for first, second in pairs)


def decide(averages, rules, complete=True, excluded_absence=False, low_attendance=False):  # noqa: PLR0911 (árvore de decisão)
    """Decisão de transição a partir das classificações finais {código: nota}.

    Ordem: transição automática → reprovado por faltas → classificações em falta → sem negativas → negativas
    toleradas (condicional, com exame extraordinário) → admitido a exame de recurso → retido.
    """
    passed_status = GRADUATED if rules.terminal else PROMOTED
    if rules.auto_promote:
        return Decision(PROMOTED, [], 'Transição automática')
    if excluded_absence:
        return Decision(RETAINED, [], 'Reprovado por faltas')
    if low_attendance:
        return Decision(RETAINED, [], 'Frequência inferior a 2/3 das aulas')
    if not complete or not averages:
        return Decision(PENDING, [], 'Classificações em falta')
    negatives = sorted(code for code, value in averages.items() if value is not None and value < rules.pass_grade)
    if not negatives:
        return Decision(passed_status, [])
    pair = _pair_violated(set(negatives), rules.forbidden_pairs)
    below_floor = rules.floor is not None and any(averages[code] < rules.floor for code in negatives)
    if len(negatives) <= rules.conditional_max and not below_floor and not pair:
        return Decision(CONDITIONAL, negatives, 'Transita com disciplinas em atraso')
    if len(negatives) <= rules.exam_max and not pair:
        return Decision(EXAM, negatives, 'Admitido a exame de recurso')
    return Decision(RETAINED, negatives, 'Negativas acima do permitido')


def special_exam_result(previous, exam, improvement=False):
    """Recurso e extraordinário: a nota do exame substitui; melhoria: prevalece a mais alta."""
    if exam is None:
        return previous
    if improvement and previous is not None:
        return max(previous, exam)
    return exam
