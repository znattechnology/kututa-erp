from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Técnico: o trimestre, o CT e a CF deixam de se arredondar (só a CA e a CFD) e calculam-se até ao 3.º trimestre a
    partir da primeira nota. Recalculam-se os resultados de trimestre do técnico que não vieram importados (e com eles
    os anuais); os importados ficam como vieram."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Term = env['edu.term.result']
    Policy = env['edu.evaluation.policy']
    terms = Term.search([('imported', '=', False)]).filtered(
        lambda t: Policy._get(t.company_id, t.class_id.level_id).regime == 'technical'
    )
    Term._recompute_keys({(t.enrollment_id.id, t.subject_id.id, t.trimester_id.id) for t in terms})
