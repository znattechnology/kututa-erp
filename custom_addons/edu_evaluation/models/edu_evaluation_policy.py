from odoo import api, fields, models

from ..tools.grading import GENERAL, TECHNICAL, Rules

# Regras por omissão de cada nível (RAA, Dec. Exec. 424/25; Despacho 60/08 no técnico).
LEVEL_DEFAULTS = {
    'INICIACAO': {'regime': 'preschool', 'scale_max': 4, 'pass_grade': 2, 'floor': 0, 'conditional_max': 0},
    'PRIMARIO': {
        'regime': 'primary',
        'scale_max': 10,
        'pass_grade': 5,
        'floor': 0,
        'conditional_max': 0,
        'exam_classes': '6',
        'exam_max': 2,  # 6.ª: duas negativas entre 3 e 4 (art. 31.º, n.º 5)
        'exam_floor': 3,
        'auto_promote_classes': '1,3,5',
        'min_attendance': 2 / 3,
    },
    'SECUNDARIO_I_CICLO': {
        'regime': GENERAL,
        'conditional_classes': '7,8',
        'exam_classes': '9',
        'exam_max': 3,  # 9.ª: até três negativas entre 6 e 9 (art. 31.º, n.º 6)
        'exam_floor': 6,
        'forbidden_pairs': 'LP+MAT',
    },
    'SECUNDARIO_II_CICLO': {
        'regime': GENERAL,
        'conditional_classes': '10,11',
        'exam_classes': '12',
        'exam_max': 3,  # 12.ª: até três negativas entre 6 e 9 (art. 31.º, n.º 7)
        'exam_floor': 6,
        'forbidden_pairs': 'LP+MAT',
    },
    # Despacho 60/08, art. 29.º a 31.º: transita com até duas negativas, sem nota mínima (os 7 valores são do ano
    # terminal da disciplina, art. 28.º); faltas pelos tempos lectivos, não pela frequência de 2/3; até 5 exames.
    'TECNICO': {
        'regime': TECHNICAL,
        'conditional_classes': '10,11,12',
        'floor': 0,
        'exam_max': 5,
        'forbidden_pairs': '',
        'min_attendance': 0,
    },
    'MAGISTERIO': {'regime': GENERAL, 'conditional_classes': '10,11,12', 'exam_max': 4, 'forbidden_pairs': 'LP+MAT'},
}


def int_list(text):
    return {int(part) for part in (text or '').replace(';', ',').split(',') if part.strip().isdigit()}


class EduEvaluationPolicy(models.Model):
    _name = 'edu.evaluation.policy'
    _description = 'Regime de avaliação (por escola e nível)'
    _order = 'company_id, level_id'

    name = fields.Char(string='Designação', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    level_id = fields.Many2one('edu.level', string='Nível', required=True)
    regime = fields.Selection(
        [
            ('preschool', 'Pré-escolar (qualitativa, RDEC)'),
            ('primary', 'Primário'),
            (GENERAL, 'Secundário geral'),
            (TECHNICAL, 'Técnico-profissional'),
        ],
        required=True,
        default=GENERAL,
    )
    scale_max = fields.Integer(string='Escala até', default=20)
    pass_grade = fields.Float(string='Nota de aprovação', default=10)
    floor = fields.Float(
        string='Mínimo das negativas toleradas',
        default=7,
        help='As negativas toleradas na transição têm de ser ≥ a este valor.',
    )
    rounding = fields.Selection(
        [('integer', 'Às unidades (RAA, art. 16.º)'), ('decimal2', 'Duas casas decimais')],
        string='Arredondamento',
        default='integer',
        required=True,
    )
    mac_weight = fields.Float(string='Peso da avaliação contínua no trimestre', default=0.5, digits=(3, 2))
    national_exam_weight = fields.Float(string='Peso do exame nacional (6.ª e 9.ª)', default=0.4, digits=(3, 2))
    national_exam_weight_12 = fields.Float(string='Peso do exame nacional (12.ª)', default=0.5, digits=(3, 2))
    cf_weight = fields.Float(string='Peso da CF na CA (técnico)', default=0.6, digits=(3, 2))
    technical_ca_precise = fields.Boolean(
        string='CA com a CF e a PG sem arredondamentos intermédios',
        help='Como o secPed-Express: a CF e a PG entram na CA com todas as casas decimais e arredonda-se uma vez. '
        'Desmarcado: a CF e a PG arredondadas (classificação atribuída pelo conselho de turma).',
    )
    conditional_classes = fields.Char(string='Classes com transição condicional', help='Por exemplo: 7,8')
    conditional_max = fields.Integer(string='Negativas toleradas na transição', default=2)
    forbidden_pairs = fields.Char(
        string='Negativas que não podem coincidir',
        default='LP+MAT',
        help='Pares de códigos separados por vírgulas, por exemplo «LP+MAT». No II ciclo, a disciplina específica da '
        'área de formação de cada curso junta-se ao par com LP.',
    )
    exam_classes = fields.Char(string='Classes de exame nacional', help='Por exemplo: 6 ou 9 ou 12')
    exam_max = fields.Integer(string='Negativas que admitem exame de recurso', default=4)
    exam_floor = fields.Float(
        string='Mínimo das negativas para recurso',
        help='Ensino geral: 3 valores na 6.ª, 6 na 9.ª e na 12.ª (Dec. 424/25, art. 31.º). 0 = sem mínimo.',
    )
    auto_promote_classes = fields.Char(string='Classes de transição automática')
    min_attendance = fields.Float(
        string='Frequência mínima',
        digits=(4, 3),
        help='Primário: 2/3 das aulas (art. 21.º, n.º 2, al. b)). 0 = sem mínimo.',
    )
    structuring_codes = fields.Char(
        string='Disciplinas estruturantes', help='Códigos separados por vírgulas: negativa em todas → retido.'
    )
    max_retentions = fields.Integer(string='Retenções permitidas no nível', default=2)
    course_formula = fields.Selection(
        [
            ('dec90', '(2 × PC + PAP) / 3 (Despacho n.º 60/08, arts. 43.º e 44.º)'),
            ('internship', '(4 × PC + EC + PAP) / 6 (Resumo do INP)'),
        ],
        string='Classificação final do curso',
        default='dec90',
    )

    _company_level_uniq = models.Constraint('UNIQUE(company_id, level_id)', 'O nível já tem regime de avaliação.')

    @api.depends('level_id')
    def _compute_name(self):
        for policy in self:
            policy.name = self.env._('Regime de avaliação: %s', policy.level_id.name or '')

    @api.model
    def _get(self, company, level):
        """Regime da escola para o nível, criado com os valores do RAA se ainda não existir."""
        policy = self.sudo().search([('company_id', '=', company.id), ('level_id', '=', level.id)], limit=1)
        if not policy:
            vals = {'company_id': company.id, 'level_id': level.id, **LEVEL_DEFAULTS.get(level.code, {})}
            policy = self.sudo().create(vals)
        return policy

    def _pairs(self, course=None):
        pairs = []
        for item in (self.forbidden_pairs or '').split(','):
            codes = [code.strip() for code in item.split('+') if code.strip()]
            if len(codes) == 2:
                pairs.append(tuple(codes))
        for subject in course.edu_area_subject_ids if course else []:
            pairs.append(('LP', subject.code))
        return pairs

    def _national_weight(self, class_number):
        return self.national_exam_weight_12 if class_number == 12 else self.national_exam_weight

    def _is_exam_class(self, class_number):
        return class_number in int_list(self.exam_classes)

    def _rules(self, edu_class):
        number = edu_class.class_number
        terminal = number == (edu_class.curriculum_id.class_to or edu_class.level_id.class_to)
        exam_class = self._is_exam_class(number)
        return Rules(
            pass_grade=self.pass_grade,
            floor=self.floor or None,
            conditional_max=self.conditional_max if number in int_list(self.conditional_classes) else 0,
            forbidden_pairs=self._pairs(edu_class.course_id),
            exam_max=self.exam_max if (exam_class or self.regime == TECHNICAL or terminal) else 0,
            exam_floor=self.exam_floor or None,
            auto_promote=self.regime == 'preschool' or number in int_list(self.auto_promote_classes),
            terminal=terminal,
        )
