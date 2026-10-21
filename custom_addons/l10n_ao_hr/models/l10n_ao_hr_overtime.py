from odoo import api, fields, models
from odoo.exceptions import ValidationError

OVERTIME_KINDS = [
    ('extra', 'Trabalho extraordinário (dia útil)'),
    ('night', 'Trabalho nocturno (20h às 6h)'),
    ('rest_day', 'Dia de descanso semanal'),
    ('holiday', 'Feriado'),
]
# LGT, art. 185.º: limites do trabalho extraordinário sem autorização da IGT.
LIMIT_DAY = 2.0
LIMIT_MONTH = 40.0
LIMIT_YEAR = 200.0


def round_overtime_hours(hours):
    """LGT, art. 188.º, n.º 4: fracções abaixo de 15 min não contam, de 15 a 44 min contam meia hora,
    de 45 a 60 min contam uma hora. Aplica-se ao total mensal por tipo."""
    whole = int(hours)
    minutes = round((hours - whole) * 60)
    if minutes < 15:
        return float(whole)
    if minutes < 45:
        return whole + 0.5
    return whole + 1.0


class L10nAoHrOvertime(models.Model):
    _name = 'l10n_ao_hr.overtime'
    _description = 'Registo de trabalho extraordinário (LGT, art. 187.º)'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    employee_id = fields.Many2one('hr.employee', required=True, index=True, tracking=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    kind = fields.Selection(OVERTIME_KINDS, string='Tipo', required=True, default='extra', tracking=True)
    hours = fields.Float(
        string='Horas', required=True, tracking=True, help='Horas efectivas (por exemplo 1,75 = 1h45).'
    )
    state = fields.Selection(
        [('draft', 'Rascunho'), ('approved', 'Aprovado'), ('refused', 'Recusado')],
        default='draft',
        required=True,
        tracking=True,
    )
    note = fields.Char(string='Motivo')
    authorized_by_igt = fields.Boolean(
        string='Autorizado pela IGT',
        help='Acima de 2 h/dia, 40 h/mês ou 200 h/ano só com autorização da Inspecção Geral do Trabalho (art. 185.º).',
    )

    @api.constrains('hours')
    def _check_hours(self):
        for record in self:
            if record.hours <= 0 or record.hours > 24:
                raise ValidationError(self.env._('As horas têm de estar entre 0 e 24.'))

    def _approved_hours(self, date_from, date_to):
        self.ensure_one()
        return sum(
            self.search(
                [
                    ('employee_id', '=', self.employee_id.id),
                    ('kind', '=', 'extra'),
                    ('state', '=', 'approved'),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                    ('id', '!=', self.id),
                ]
            ).mapped('hours')
        )

    def action_approve(self):
        for record in self:
            if record.kind == 'extra' and not record.authorized_by_igt:
                day = record.hours + record._approved_hours(record.date, record.date)
                month = record.hours + record._approved_hours(
                    record.date.replace(day=1), fields.Date.end_of(record.date, 'month')
                )
                year = record.hours + record._approved_hours(
                    record.date.replace(month=1, day=1), record.date.replace(month=12, day=31)
                )
                if day > LIMIT_DAY or month > LIMIT_MONTH or year > LIMIT_YEAR:
                    raise ValidationError(
                        self.env._(
                            'Limites do trabalho extraordinário (LGT, art. 185.º): %(day)s h no dia (máx. 2), '
                            '%(month)s h no mês (máx. 40), %(year)s h no ano (máx. 200). Acima disso só com '
                            'autorização da IGT: marque «Autorizado pela IGT».',
                            day=day,
                            month=month,
                            year=year,
                        )
                    )
            record.state = 'approved'

    def action_refuse(self):
        self.write({'state': 'refused'})

    def action_draft(self):
        self.write({'state': 'draft'})
