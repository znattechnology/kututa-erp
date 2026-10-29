from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    note = fields.Text(string='Observações', help='Referência ao regulamento aprovado pela instituição.')

    _company_level_uniq = models.Constraint('UNIQUE(company_id, level_id)', 'O nível já tem regulamento académico.')

    @api.depends('level_id')
    def _compute_name(self):
        for regulation in self:
            regulation.name = self.env._('Regulamento académico: %s', regulation.level_id.name or '')

    @api.constrains('max_attempts', 'max_semester_credits', 'max_backlog')
    def _check_values(self):
        for regulation in self:
            if regulation.max_attempts < 1:
                raise ValidationError(self.env._('Tem de haver pelo menos uma inscrição por UC.'))
            if regulation.max_semester_credits < 0 or regulation.max_backlog < 0:
                raise ValidationError(self.env._('Os limites não podem ser negativos.'))

    @api.model
    def _get(self, company, level):
        """Regulamento da instituição para o nível, criado com os valores de origem se ainda não existir."""
        regulation = self.sudo().search([('company_id', '=', company.id), ('level_id', '=', level.id)], limit=1)
        return regulation or self.sudo().create({'company_id': company.id, 'level_id': level.id})
