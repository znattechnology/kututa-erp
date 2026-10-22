"""Limites de faltas injustificadas, sem acesso à base de dados.

Ensino geral (Decreto Executivo n.º 424/25, art. 25.º, n.os 8 e 16): retido ao acumular, por trimestre e
disciplina, 3 faltas com 1 tempo semanal, 4 com 2 tempos e 5 com mais de 2.

Técnico-profissional (Despacho n.º 60/08, art. 12.º, n.º 2): «o número máximo anual de faltas injustificadas é
o triplo do número de tempos semanais», portanto reprova com o triplo mais uma. A exclusão numa disciplina retém
o aluno no ano (decisão da escola, como no Resumo do Regime de Avaliação, VI.1).
"""

GENERAL = 'general'
TECHNICAL = 'technical'

OK = 'ok'
AT_RISK = 'at_risk'
FAILED = 'failed'


def absence_limit(weekly_hours, regime):
    """Limite de faltas injustificadas (None = sem limite): no geral, as que retêm; no técnico, o máximo permitido."""
    if not weekly_hours or weekly_hours <= 0:
        return None
    if regime == TECHNICAL:
        return 3 * weekly_hours
    if weekly_hours == 1:
        return 3
    if weekly_hours == 2:
        return 4
    return 5


def absence_status(absences, limit, regime=GENERAL):
    """Geral: retido ao atingir o limite. Técnico: reprovado ao passar o máximo. Em risco a uma falta disso."""
    if limit is None:
        return OK
    failing = limit + 1 if regime == TECHNICAL else limit
    if absences >= failing:
        return FAILED
    if absences == failing - 1:
        return AT_RISK
    return OK
