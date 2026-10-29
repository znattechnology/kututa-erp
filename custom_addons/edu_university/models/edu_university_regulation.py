from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..tools.grading_higher import Rules


class EduUniversityRegulation(models.Model):
    """Regulamento académico da instituição para um nível (licenciatura, mestrado). As regras de inscrição, avaliação
    e progressão do ensino superior não vêm de um diploma nacional: cada instituição aprova o seu. Os valores de
    origem são os típicos; cada instituição acerta-os pelo seu regulamento."""

    _name = 'edu.university.regulation'
    _description = 'Regulamento académico (ensino superior)'
    _order = 'company_id, level_id'
    _check_company_auto = True

    name = fields.Char(string='Designação', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Instituição', required=True, default=lambda self: self.env.company, index=True
    )
    level_id = fields.Many2one(
        'edu.level', string='Nível', required=True, domain="[('subsystem', '=', 'higher')]", ondelete='restrict'
    )
    # Inscrição
    max_attempts = fields.Integer(
        string='Inscrições por UC', default=3, help='Ao fim deste número de inscrições na mesma UC, a UC prescreve.'
    )
    max_semester_credits = fields.Float(
        string='Créditos por semestre (máximo)',
        default=40,
        digits=(4, 1),
        help='Soma dos créditos das UCs do semestre, com as UCs em atraso; as anuais contam metade em cada. 0 = sem '
        'limite.',
    )
    # Progressão
    max_backlog = fields.Integer(
        string='UCs em atraso para passar de ano',
        default=2,
        help='Passa ao ano seguinte com, no máximo, este número de UCs por aprovar (do ano e dos anteriores).',
    )
    # Avaliação
    pass_grade = fields.Float(string='Nota de aprovação', default=10, digits=(4, 2))
    exemption_grade = fields.Float(
        string='Dispensa de exame com',
        default=14,
        digits=(4, 2),
        help='Com média de frequência igual ou superior, a MF é a nota final. 0 = sem dispensa.',
    )
    admission_grade = fields.Float(
        string='Admissão a exame com', default=7, digits=(4, 2), help='Abaixo desta média de frequência, excluído.'
    )
    min_attendance = fields.Float(
        string='Assiduidade mínima (%)', default=75, digits=(5, 2), help='Abaixo, excluído. 0 = sem regra.'
    )
    frequency_weight = fields.Float(
        string='Peso da MF na nota com exame',
        default=0.4,
        digits=(3, 2),
        help='Nota = peso × MF + (1 − peso) × exame. 0 = só o exame.',
    )
    exam_min = fields.Float(
        string='Mínimo no exame', default=10, digits=(4, 2), help='Abaixo, reprova com a nota do exame.'
    )
    appeal_for_excluded = fields.Boolean(
        string='Excluídos vão ao recurso', help='O excluído pela MF ou pelas faltas pode fazer o exame de recurso.'
    )
    special_fixed_pass = fields.Boolean(
        string='Positiva do exame especial fixa',
        default=True,
        help='No exame especial, a positiva é sempre a nota de aprovação (10).',
    )
    rounding = fields.Selection(
        [('unit', 'Às unidades'), ('tenth', 'Às décimas')], string='Arredondamento da nota final', default='unit'
    )
    note = fields.Text(string='Observações', help='Referência ao regulamento aprovado pela instituição.')

    _company_level_uniq = models.Constraint('UNIQUE(company_id, level_id)', 'O nível já tem regulamento académico.')

    @api.depends('level_id')
    def _compute_name(self):
        for regulation in self:
            regulation.name = self.env._('Regulamento académico: %s', regulation.level_id.name or '')

    @api.constrains(
        'max_attempts',
        'max_semester_credits',
        'max_backlog',
        'pass_grade',
        'exemption_grade',
        'admission_grade',
        'min_attendance',
        'frequency_weight',
        'exam_min',
    )
    def _check_values(self):
        for regulation in self:
            if not 0 < regulation.pass_grade <= 20 or not 0 <= regulation.admission_grade <= regulation.pass_grade:
                raise ValidationError(self.env._('A admissão a exame fica entre 0 e a nota de aprovação (até 20).'))
            if regulation.exemption_grade and not regulation.pass_grade <= regulation.exemption_grade <= 20:
                raise ValidationError(self.env._('A dispensa fica entre a nota de aprovação e 20.'))
            if not 0 <= regulation.frequency_weight <= 1 or not 0 <= regulation.min_attendance <= 100:
                raise ValidationError(self.env._('O peso da MF vai de 0 a 1 e a assiduidade de 0 a 100 %.'))
            if not 0 <= regulation.exam_min <= 20:
                raise ValidationError(self.env._('O mínimo no exame vai de 0 a 20.'))
            if regulation.max_attempts < 1:
                raise ValidationError(self.env._('Tem de haver pelo menos uma inscrição por UC.'))
            if regulation.max_semester_credits < 0 or regulation.max_backlog < 0:
                raise ValidationError(self.env._('Os limites não podem ser negativos.'))

    def _rules(self):
        self.ensure_one()
        return Rules(
            pass_grade=self.pass_grade,
            exemption=self.exemption_grade,
            admission=self.admission_grade,
            min_attendance=self.min_attendance,
            frequency_weight=self.frequency_weight,
            exam_min=self.exam_min,
            special_fixed=self.special_fixed_pass,
            appeal_for_excluded=self.appeal_for_excluded,
            rounding=self.rounding,
        )

    @api.model
    def _get(self, company, level):
        """Regulamento da instituição para o nível, criado com os valores de origem se ainda não existir."""
        regulation = self.sudo().search([('company_id', '=', company.id), ('level_id', '=', level.id)], limit=1)
        return regulation or self.sudo().create({'company_id': company.id, 'level_id': level.id})
