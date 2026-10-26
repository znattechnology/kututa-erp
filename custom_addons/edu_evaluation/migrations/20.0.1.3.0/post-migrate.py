from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """No técnico, o CT de um trimestre com só a NPP (ou só a NPT) passou a ser (NPP + NPT)/2 com a que falta a contar
    0: recalculam-se os resultados de trimestre gravados com uma das duas em falta (os importados ficam como vieram)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Term = env['edu.term.result']
    terms = Term.search([('imported', '=', False), ('has_mt', '=', True)]).filtered(lambda t: t.has_mac != t.has_npt)
    Term._recompute_keys({(t.enrollment_id.id, t.subject_id.id, t.trimester_id.id) for t in terms})
