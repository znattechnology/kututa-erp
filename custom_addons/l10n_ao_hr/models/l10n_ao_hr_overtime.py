import math

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

OVERTIME_KINDS = [
    ('extra', 'Trabalho extraordinário (dia útil)'),
    ('night', 'Trabalho nocturno (20h às 6h)'),
    ('rest_day', 'Dia de descanso semanal'),
    ('holiday', 'Feriado'),
]
# Trabalho que excede o período normal e conta para os limites do art. 185.º (o nocturno é um acréscimo
# sobre horas que podem ser normais e não conta).
LIMITED_KINDS = ('extra', 'rest_day', 'holiday')
# LGT, art. 185.º: limites do trabalho extraordinário sem autorização da IGT.
LIMIT_DAY = 2.0
LIMIT_MONTH = 40.0
LIMIT_YEAR = 200.0
LOCKED_FIELDS = {'employee_id', 'date', 'kind', 'hours', 'authorized_by_igt'}


def round_overtime_hours(hours):
    """LGT, art. 188.º, n.º 4: fracções abaixo de 15 min não contam, de 15 a 44 min contam meia hora,
    de 45 a 60 min contam uma hora. Aplica-se ao total mensal por tipo. Os minutos contam-se por defeito
    (74,99 min são 74 min), com tolerância para os erros de vírgula flutuante."""
    total_minutes = math.floor(hours * 60 + 1e-6)
    whole, minutes = divmod(total_minutes, 60)
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

    employee_id = fields.Many2one('hr.employee', string='Trabalhador', required=True, index=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        compute='_compute_company_id',
        store=True,
        precompute=True,
        readonly=True,
        index=True,
    )
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today, tracking=True)
    kind = fields.Selection(OVERTIME_KINDS, string='Tipo', required=True, default='extra', tracking=True)
    hours = fields.Float(
        string='Horas', required=True, tracking=True, help='Horas efectivas (por exemplo 1,75 = 1h45).'
    )
    state = fields.Selection(
        [('draft', 'Rascunho'), ('approved', 'Aprovado'), ('refused', 'Recusado')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    note = fields.Char(string='Motivo')
    authorized_by_igt = fields.Boolean(
        string='Autorizado pela IGT',
        help='Acima de 2 h/dia, 40 h/mês ou 200 h/ano só com autorização da Inspecção Geral do Trabalho (art. 185.º).',
    )

    @api.depends('employee_id')
    def _compute_company_id(self):
        # A empresa fica a do momento do registo: não muda se o trabalhador mudar de empresa.
        for record in self:
            if not record.company_id:
                record.company_id = record.employee_id.company_id

    @api.depends('employee_id', 'date', 'kind', 'hours')
    def _compute_display_name(self):
        kinds = dict(OVERTIME_KINDS)
        for record in self:
            record.display_name = (
                f'{record.employee_id.name or ""} · {kinds.get(record.kind, "")} · '
                f'{record.date.strftime("%d/%m/%Y") if record.date else ""}'
            )

    @api.constrains('hours')
    def _check_hours(self):
        for record in self:
            if record.hours <= 0 or record.hours > 24:
                raise ValidationError(self.env._('As horas têm de estar entre 0 e 24.'))

    def _is_hr_user(self):
        return self.env.user.has_group('hr.group_hr_user') or self.env.su

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_hr_user():
            # O trabalhador regista as suas horas; aprovar e marcar a autorização da IGT é do RH.
            for vals in vals_list:
                vals['state'] = 'draft'
                vals['authorized_by_igt'] = False
        return super().create(vals_list)

    def write(self, vals):
        if not self._is_hr_user() and ({'state', 'authorized_by_igt'} & set(vals)):
            raise AccessError(self.env._('Só o RH aprova o trabalho extraordinário.'))
        if LOCKED_FIELDS & set(vals) and self.filtered(lambda r: r.state == 'approved'):
            raise UserError(self.env._('Um registo aprovado não se altera: reponha-o em rascunho primeiro.'))
        return super().write(vals)

    def _approved_hours(self, date_from, date_to, kinds):
        self.ensure_one()
        return sum(
            self.search(
                [
                    ('employee_id', '=', self.employee_id.id),
                    ('kind', 'in', kinds),
                    ('state', '=', 'approved'),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                    ('id', '!=', self.id),
                ]
            ).mapped('hours')
        )

    def action_approve(self):
        if not self._is_hr_user():
            raise AccessError(self.env._('Só o RH aprova o trabalho extraordinário.'))
        for record in self:
            if record.kind in LIMITED_KINDS and not record.authorized_by_igt:
                day = (
                    record.hours + record._approved_hours(record.date, record.date, ('extra',))
                    if record.kind == 'extra'
                    else 0.0
                )
                month = record.hours + record._approved_hours(
                    record.date.replace(day=1), fields.Date.end_of(record.date, 'month'), LIMITED_KINDS
                )
                year = record.hours + record._approved_hours(
                    record.date.replace(month=1, day=1), record.date.replace(month=12, day=31), LIMITED_KINDS
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
            record.write({'state': 'approved'})
        return True

    def action_refuse(self):
        if not self._is_hr_user():
            raise AccessError(self.env._('Só o RH recusa o trabalho extraordinário.'))
        self.write({'state': 'refused'})
        return True

    def action_draft(self):
        if not self._is_hr_user():
            raise AccessError(self.env._('Só o RH repõe o trabalho extraordinário.'))
        self.write({'state': 'draft'})
        return True
