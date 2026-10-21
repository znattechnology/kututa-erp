"""Limites de faltas injustificadas, sem acesso à base de dados.

Ensino geral (Decreto Executivo n.º 424/25, art. 25.º, n.os 8 e 16): por trimestre e disciplina, 3 faltas
com 1 tempo semanal, 4 com 2 tempos e 5 com mais de 2. Técnico-profissional (Despacho n.º 60/08, art. 7.º):
o triplo dos tempos semanais no ano lectivo, e a exclusão numa disciplina exclui de todas.
"""

GENERAL = 'general'
TECHNICAL = 'technical'

OK = 'ok'
AT_RISK = 'at_risk'
FAILED = 'failed'


def absence_limit(weekly_hours, regime):
    """Faltas injustificadas que levam à retenção (None = sem limite)."""
    if not weekly_hours or weekly_hours <= 0:
        return None
    if regime == TECHNICAL:
        return 3 * weekly_hours
    if weekly_hours == 1:
        return 3
    if weekly_hours == 2:
        return 4
    return 5


def absence_status(absences, limit):
    """Reprovado ao atingir o limite; em risco a uma falta do limite."""
    if limit is None:
        return OK
    if absences >= limit:
        return FAILED
    if absences == limit - 1:
        return AT_RISK
    return OK
