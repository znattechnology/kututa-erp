from odoo import api, fields, models


class EduCourse(models.Model):
    _inherit = 'edu.course'

    # Prova de acesso: obrigatória na Média-Técnica (DP 167/23, art. 49.º) e adoptada pela escola no ensino geral
    # secundário; admitido só com a nota mínima em cada prova, mesmo que sobrem vagas (art. 52.º, n.º 1).
    admission_test_required = fields.Boolean(
        string='Prova de acesso',
        compute='_compute_admission_test_required',
        store=True,
        readonly=False,
        help='A candidatura exige a nota da prova de acesso; abaixo do mínimo é rejeitada.',
    )
    admission_min_score = fields.Float(string='Nota mínima de acesso', default=10.0, digits=(4, 1))

    @api.depends('level_id')
    def _compute_admission_test_required(self):
        for course in self:
            level = course.level_id
            course.admission_test_required = level.subsystem == 'technical' or (level.class_from or 0) >= 7
