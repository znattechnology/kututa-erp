import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

DAYS_PER_MONTH = 30


class EduLateFeeRule(models.Model):
    """Multa por atraso: percentagem mensal ou valor fixo, depois da tolerância, com tecto. A multa é facturada à parte
    (no secPed ficava sem documento fiscal) e só se factura o que ainda não foi facturado."""

    _name = 'edu.late.fee.rule'
    _description = 'Regra de multa por atraso'
    _order = 'fee_line_id, id'
    _check_company_auto = True

    name = fields.Char(string='Regra', required=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    fee_line_id = fields.Many2one(
        'edu.fee.plan.line', string='Só para a taxa', check_company=True, help='Vazio: todas as taxas.'
    )
    fee_type = fields.Selection(
        [('percent', 'Percentagem por mês'), ('fixed', 'Valor fixo')], string='Tipo', required=True, default='percent'
    )
    percent = fields.Float(string='Percentagem mensal', digits=(5, 2), help='Por exemplo, 2 = 2% por mês de atraso.')
    amount = fields.Monetary(string='Valor fixo')
    grace_days = fields.Integer(string='Tolerância (dias)', default=15)
    max_amount = fields.Monetary(string='Tecto', help='0 = sem tecto.')
    tax_id = fields.Many2one(
        'account.tax',
        string='IVA',
        compute='_compute_tax_id',
        store=True,
        readonly=False,
        precompute=True,
        check_company=True,
        help='Por omissão, não sujeito (M02): a multa é uma indemnização, não uma prestação de serviço. Confirme com o '
        'contabilista.',
    )
    active = fields.Boolean(default=True)

    @api.depends('company_id')
    def _compute_tax_id(self):
        for rule in self:
            if not rule.tax_id and rule.company_id:
                rule.tax_id = (
                    self.env['account.chart.template']
                    .with_company(rule.company_id)
                    .ref('ao_ns_sale_m02', raise_if_not_found=False)
                )

    @api.constrains('fee_type', 'percent', 'amount', 'grace_days', 'fee_line_id', 'active')
    def _check_rule(self):
        for rule in self:
            if rule.fee_type == 'percent' and not 0 < rule.percent <= 100:
                raise ValidationError(self.env._('A percentagem mensal vai de 0 a 100.'))
            if rule.fee_type == 'fixed' and rule.amount <= 0:
                raise ValidationError(self.env._('Indique o valor fixo da multa.'))
            if rule.grace_days < 0:
                raise ValidationError(self.env._('A tolerância não pode ser negativa.'))
            if rule.active:
                clash = self.search_count(
                    [
                        ('id', '!=', rule.id),
                        ('company_id', '=', rule.company_id.id),
                        ('fee_line_id', '=', rule.fee_line_id.id),
                        ('active', '=', True),
                    ]
                )
                if clash:
                    raise ValidationError(self.env._('Já existe uma regra activa para estas taxas.'))

    def _late_fee(self, principal, due, today):
        """Multa devida à data: (meses de atraso depois da tolerância) × percentagem, ou o valor fixo; com tecto."""
        self.ensure_one()
        start = due + timedelta(days=self.grace_days)
        if today <= start:
            return 0.0
        months = (today - start).days // DAYS_PER_MONTH + 1
        value = principal * self.percent / 100 * months if self.fee_type == 'percent' else self.amount
        if self.max_amount:
            value = min(value, self.max_amount)
        return self.currency_id.round(value)

    @api.model
    def _rule_for(self, move):
        rules = self.search([('company_id', '=', move.company_id.id)])
        specific = rules.filtered(lambda r: r.fee_line_id and r.fee_line_id == move.edu_fee_line_id)
        return specific[:1] or rules.filtered(lambda r: not r.fee_line_id)[:1]

    @api.model
    def _apply_late_fees(self, today=None):
        """Factura a multa em falta de cada factura escolar vencida (o total facturado acompanha o atraso)."""
        today = today or fields.Date.context_today(self)
        Move = self.env['account.move']
        overdue = Move.search(
            [
                ('edu_student_id', '!=', False),
                ('edu_category', 'not in', ('late_fee', False)),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', today),
            ]
        )
        created = Move
        for move in overdue:
            rule = self._rule_for(move)
            if not rule:
                continue
            target = rule._late_fee(move.amount_total, move.invoice_date_due, today)
            charged = sum(
                Move.search(
                    [
                        ('edu_late_fee_origin_id', '=', move.id),
                        ('state', '=', 'posted'),
                        ('move_type', '=', 'out_invoice'),
                    ]
                ).mapped('amount_total')
            )
            missing = move.currency_id.round(target - charged)
            if missing <= 0:
                continue
            created |= rule._invoice(move, missing, today)
        return created

    def _invoice(self, origin, amount, today):
        self.ensure_one()
        product = self.env.ref('edu_fees.product_late_fee')
        line = origin.invoice_line_ids[:1]
        move = (
            self.env['account.move']
            .with_company(origin.company_id)
            .create(
                {
                    'move_type': 'out_invoice',
                    'partner_id': origin.partner_id.id,
                    'journal_id': origin.journal_id.id,
                    'invoice_date': today,
                    'invoice_date_due': today,
                    'edu_student_id': origin.edu_student_id.id,
                    'edu_enrollment_id': origin.edu_enrollment_id.id,
                    'edu_category': 'late_fee',
                    'edu_late_fee_origin_id': origin.id,
                    'invoice_line_ids': [
                        fields.Command.create(
                            {
                                'product_id': product.id,
                                'name': self.env._(
                                    'Multa por atraso: %(origin)s (%(label)s)', origin=origin.name, label=line.name
                                ),
                                'quantity': 1,
                                'price_unit': amount,
                                'tax_ids': [fields.Command.set(self.tax_id.ids)],
                            }
                        )
                    ],
                }
            )
        )
        move.action_post()
        return move

    @api.model
    def _cron_overdue(self):
        try:
            with self.env.cr.savepoint():
                self._apply_late_fees()
        except Exception:
            _logger.exception('Propinas: erro no cálculo das multas')
        self.env['edu.student']._edu_update_standing()
