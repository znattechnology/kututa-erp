from odoo import fields, models

SUBSYSTEMS = [
    ('general', 'Ensino geral'),
    ('technical', 'Técnico-profissional'),
    ('teacher_training', 'Formação de professores'),
]


class EduLevel(models.Model):
    _name = 'edu.level'
    _description = 'Nível de ensino'
    _order = 'sequence, id'

    name = fields.Char(string='Nível', required=True, translate=True)
    code = fields.Char(string='Código', required=True, help='Código do nível no secPed-Express.')
    sequence = fields.Integer(default=10)
    subsystem = fields.Selection(SUBSYSTEMS, string='Subsistema', required=True, default='general')
    class_from = fields.Integer(string='Da classe', help='0 = iniciação.')
    class_to = fields.Integer(string='À classe')
    # Idades completas no ano da matrícula (DP 162/23, arts. 21.º e 22.º; DP 167/23, art. 23.º): abaixo da mínima
    # não se matricula; acima da regular, aviso (apoio pedagógico ou educação de adultos, art. 23.º).
    min_age = fields.Integer(string='Idade mínima de ingresso')
    regular_age_max = fields.Integer(string='Idade regular até')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'Já existe um nível com este código.')

    def action_materialize_plan(self):
        """Cria na empresa actual o plano curricular do tronco comum nacional deste nível."""
        self.ensure_one()
        base = self.env['edu.curriculum.template']._find(self, profile=False)
        if not base:
            return False
        curriculum = base._materialize(self.env.company)
        return curriculum._action_open()
