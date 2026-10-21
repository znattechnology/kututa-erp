from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

MAX_REDUCTION_PCT = 20.0
MAX_REDUCTION_MONTHS = 6
# LGT, art. 87.º, n.º 3: suspensão até 30 dias por infracção e 60 dias por ano civil.
MAX_SUSPENSION_DAYS = 30
MAX_SUSPENSION_DAYS_YEAR = 60
LOCKED_FIELDS = {
    'employee_id',
    'date',
    'kind',
    'reduction_pct',
    'months',
    'suspension_date_from',
    'suspension_date_to',
}


class L10nAoHrSanction(models.Model):
    _name = 'l10n_ao_hr.sanction'
    _description = 'Sanção disciplinar (LGT, arts. 85.º a 101.º)'
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
    date = fields.Date(string='Data da decisão', required=True, default=fields.Date.context_today, tracking=True)
    kind = fields.Selection(
        [
            ('oral', 'Admoestação oral'),
            ('warning', 'Admoestação registada'),
            ('demotion', 'Despromoção temporária de categoria'),
            ('reduction', 'Redução temporária do salário'),
            ('suspension', 'Suspensão com perda de salário'),
        ],
        string='Sanção',
        required=True,
        default='warning',
        tracking=True,
    )
    reduction_pct = fields.Float(
        string='Redução (%)', help='Até 20% do salário-base (LGT, art. 87.º, n.º 2).', tracking=True
    )
    months = fields.Integer(string='Meses', default=1, help='De 1 a 6 meses (art. 87.º, n.º 2).', tracking=True)
    suspension_date_from = fields.Date(string='Suspensão de')
    suspension_date_to = fields.Date(string='Suspensão até')
    leave_id = fields.Many2one('hr.leave', string='Ausência de suspensão', readonly=True, copy=False)
    reason = fields.Text(string='Factos e fundamentos', required=True)
    state = fields.Selection(
        [('draft', 'Rascunho'), ('applied', 'Aplicada'), ('cancelled', 'Anulada')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )

    @api.depends('employee_id')
    def _compute_company_id(self):
        for sanction in self:
            if not sanction.company_id:
                sanction.company_id = sanction.employee_id.company_id

    @api.depends('employee_id', 'kind', 'date')
    def _compute_display_name(self):
        kinds = dict(self._fields['kind'].selection)
        for sanction in self:
            sanction.display_name = (
                f'{sanction.employee_id.name or ""} · {kinds.get(sanction.kind, "")} · '
                f'{sanction.date.strftime("%d/%m/%Y") if sanction.date else ""}'
            )

    def _suspension_days(self):
        self.ensure_one()
        if self.kind != 'suspension' or not self.suspension_date_from or not self.suspension_date_to:
            return 0
        return (self.suspension_date_to - self.suspension_date_from).days + 1

    @api.constrains('kind', 'reduction_pct', 'months', 'suspension_date_from', 'suspension_date_to', 'state')
    def _check_values(self):
        for sanction in self:
            if sanction.kind == 'reduction':
                if not 0 < sanction.reduction_pct <= MAX_REDUCTION_PCT:
                    raise ValidationError(self.env._('A redução do salário vai até 20% (LGT, art. 87.º, n.º 2).'))
                if not 1 <= sanction.months <= MAX_REDUCTION_MONTHS:
                    raise ValidationError(
                        self.env._('A redução do salário dura de 1 a 6 meses (LGT, art. 87.º, n.º 2).')
                    )
            if sanction.kind == 'suspension':
                if not sanction.suspension_date_from or not sanction.suspension_date_to:
                    raise ValidationError(self.env._('Indique as datas da suspensão.'))
                if sanction.suspension_date_to < sanction.suspension_date_from:
                    raise ValidationError(self.env._('A data de fim da suspensão é anterior à de início.'))
                if sanction._suspension_days() > MAX_SUSPENSION_DAYS:
                    raise ValidationError(
                        self.env._('A suspensão não pode exceder 30 dias por infracção (LGT, art. 87.º, n.º 3).')
                    )
                year = sanction.suspension_date_from.year
                others = self.search(
                    [
                        ('employee_id', '=', sanction.employee_id.id),
                        ('kind', '=', 'suspension'),
                        ('state', '=', 'applied'),
                        ('id', '!=', sanction.id),
                        ('suspension_date_from', '>=', f'{year}-01-01'),
                        ('suspension_date_from', '<=', f'{year}-12-31'),
                    ]
                )
                total = sanction._suspension_days() + sum(s._suspension_days() for s in others)
                if total > MAX_SUSPENSION_DAYS_YEAR:
                    raise ValidationError(
                        self.env._(
                            'As suspensões de %(year)s somam %(days)s dias; o máximo é 60 por ano civil '
                            '(LGT, art. 87.º, n.º 3).',
                            year=year,
                            days=total,
                        )
                    )

    def write(self, vals):
        if LOCKED_FIELDS & set(vals) and self.filtered(lambda s: s.state == 'applied'):
            raise UserError(self.env._('Uma sanção aplicada não se altera: anule-a e registe outra.'))
        return super().write(vals)

    def action_apply(self):
        for sanction in self.filtered(lambda s: s.state == 'draft'):
            if sanction.kind == 'suspension':
                sanction.leave_id = sanction._create_suspension_leave()
            sanction.write({'state': 'applied'})
        return True

    def _create_suspension_leave(self):
        """A suspensão entra como ausência não paga, para a folha a descontar (art. 87.º, n.º 1, al. e))."""
        self.ensure_one()
        kind = self.env.ref('l10n_ao_hr.work_entry_type_ao_suspensao')
        leave = (
            self.env['hr.leave']
            .sudo()
            .with_context(leave_skip_date_check=True, leave_fast_create=True, mail_activity_automation_skip=True)
            .create(
                {
                    'employee_id': self.employee_id.id,
                    'work_entry_type_id': kind.id,
                    'request_date_from': self.suspension_date_from,
                    'request_date_to': self.suspension_date_to,
                    'private_name': self.env._('Suspensão disciplinar'),
                }
            )
        )
        if leave.state != 'validate':
            leave.with_context(leave_skip_state_check=True).action_approve(check_state=False)
        return leave

    def action_cancel(self):
        for sanction in self:
            if sanction.leave_id and sanction.leave_id.state != 'cancel':
                sanction.leave_id.sudo().with_context(leave_skip_state_check=True).action_refuse()
            sanction.write({'state': 'cancelled'})
        return True

    def _reduction_in_month(self, year, month):
        """Percentagem de redução em vigor no mês (do mês da decisão, inclusive, durante «meses» meses)."""
        self.ensure_one()
        if self.state != 'applied' or self.kind != 'reduction':
            return 0.0
        start = self.date.replace(day=1)
        end = start + relativedelta(months=self.months) - relativedelta(days=1)
        day = fields.Date.to_date(f'{year}-{month:02d}-01')
        return self.reduction_pct if start <= day <= end else 0.0
