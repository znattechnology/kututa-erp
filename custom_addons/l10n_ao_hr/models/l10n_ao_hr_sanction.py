from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

MAX_REDUCTION_PCT = 20.0
MAX_REDUCTION_MONTHS = 6


class L10nAoHrSanction(models.Model):
    _name = 'l10n_ao_hr.sanction'
    _description = 'Sanção disciplinar (LGT, arts. 85.º a 101.º)'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    employee_id = fields.Many2one('hr.employee', required=True, index=True, tracking=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True)
    date = fields.Date(string='Data da decisão', required=True, default=fields.Date.context_today, tracking=True)
    kind = fields.Selection(
        [
            ('warning', 'Admoestação'),
            ('reduction', 'Redução temporária do salário'),
            ('suspension', 'Suspensão com perda de salário'),
            ('demotion', 'Despromoção'),
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
    reason = fields.Text(string='Factos e fundamentos', required=True)
    state = fields.Selection(
        [('draft', 'Rascunho'), ('applied', 'Aplicada'), ('cancelled', 'Anulada')],
        default='draft',
        required=True,
        tracking=True,
    )

    @api.constrains('kind', 'reduction_pct', 'months', 'suspension_date_from', 'suspension_date_to')
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

    def action_apply(self):
        self.write({'state': 'applied'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def _reduction_in_month(self, year, month):
        """Percentagem de redução em vigor no mês (do mês da decisão, inclusive, durante «meses» meses)."""
        self.ensure_one()
        if self.state != 'applied' or self.kind != 'reduction':
            return 0.0
        start = self.date.replace(day=1)
        end = start + relativedelta(months=self.months) - relativedelta(days=1)
        day = fields.Date.to_date(f'{year}-{month:02d}-01')
        return self.reduction_pct if start <= day <= end else 0.0
