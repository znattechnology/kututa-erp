from odoo import SUPERUSER_ID, api

# Valores antigos por omissão → valores da lei. Só se mudam os que ninguém alterou.
RESIT = {
    'PRIMARIO': (3, 2, 3),  # 6.ª: duas negativas entre 3 e 4 (Dec. 424/25, art. 31.º, n.º 5)
    'SECUNDARIO_I_CICLO': (4, 3, 6),  # 9.ª: até três negativas entre 6 e 9 (n.º 6)
    'SECUNDARIO_II_CICLO': (4, 3, 6),  # 12.ª: até três negativas entre 6 e 9 (n.º 7)
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Policy = env['edu.evaluation.policy']
    for code, (old_max, new_max, exam_floor) in RESIT.items():
        Policy.search([('level_id.code', '=', code), ('exam_max', '=', old_max)]).write(
            {'exam_max': new_max, 'exam_floor': exam_floor}
        )
    # Técnico (Despacho 60/08): transição sem nota mínima e sem a frequência de 2/3 (as faltas contam pelos tempos).
    technical = Policy.search([('regime', '=', 'technical')])
    technical.filtered(lambda p: p.floor == 7).write({'floor': 0})
    technical.write({'min_attendance': 0})

    # Nota para a transição: a classificação final; no técnico, recalcula-se a das plurianuais no ano terminal.
    cr.execute('UPDATE edu_subject_result SET transition_grade = final')
    env.invalidate_all()
    results = env['edu.subject.result'].search(
        [('terminal_subject', '=', True), ('company_id', 'in', technical.company_id.ids)]
    )
    plural = results.filtered(lambda r: r._policy().regime == 'technical' and len(r._subject_span()[0]) > 1)
    for start in range(0, len(plural), 500):
        plural[start : start + 500]._recompute()
