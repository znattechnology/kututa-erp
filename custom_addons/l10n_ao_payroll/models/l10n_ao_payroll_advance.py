from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

MAX_SALARIES = 3  # LGT, art. 248.º, n.º 6


class L10nAoPayrollAdvance(models.Model):
    _name = 'l10n_ao_payroll.advance'
    _description = 'Adiantamento ao trabalhador (LGT, art. 248.º)'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    employee_id = fields.Many2one(
        'hr.employee', string='Trabalhador', required=True, index=True, tracking=True, check_company=True
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary(string='Valor', required=True, tracking=True)
    monthly_deduction = fields.Monetary(
        string='Desconto mensal',
        required=True,
        help='Descontado em cada folha até saldar, com o limite de 25% do líquido (art. 248.º, n.º 7).',
    )
    deduction_ids = fields.One2many('l10n_ao_payroll.advance.deduction', 'advance_id', string='Amortizações')
    deducted = fields.Monetary(string='Amortizado', compute='_compute_balance', store=True)
    balance = fields.Monetary(string='Saldo', compute='_compute_balance', store=True)
    state = fields.Selection(
        [('draft', 'Rascunho'), ('approved', 'Concedido'), ('settled', 'Liquidado'), ('cancelled', 'Anulado')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Pago por',
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    move_id = fields.Many2one('account.move', string='Lançamento', readonly=True, copy=False)
    note = fields.Char(string='Motivo')

    @api.depends('amount', 'deduction_ids.amount', 'deduction_ids.payslip_id.state')
    def _compute_balance(self):
        for advance in self:
            advance.deducted = sum(
                advance.deduction_ids.filtered(lambda d: d.payslip_id.state != 'cancelled').mapped('amount')
            )
            advance.balance = advance.amount - advance.deducted

    @api.constrains('amount', 'monthly_deduction')
    def _check_amounts(self):
        for advance in self:
            if advance.amount <= 0 or advance.monthly_deduction <= 0:
                raise ValidationError(self.env._('O valor e o desconto mensal têm de ser positivos.'))

    def action_approve(self):
        for advance in self:
            if advance.state != 'draft':
                continue
            base = advance.employee_id.version_id.wage
            outstanding = sum(
                self.search(
                    [('employee_id', '=', advance.employee_id.id), ('state', '=', 'approved'), ('id', '!=', advance.id)]
                ).mapped('balance')
            )
            if base and outstanding + advance.amount > MAX_SALARIES * base:
                raise UserError(
                    self.env._(
                        'Os adiantamentos em dívida (%(outstanding)s) mais este (%(amount)s) excedem 3 salários-base '
                        '(%(limit)s), o máximo do art. 248.º, n.º 6 da LGT.',
                        outstanding=outstanding,
                        amount=advance.amount,
                        limit=MAX_SALARIES * base,
                    )
                )
            if advance.journal_id:
                company = advance.company_id
                company._l10n_ao_payroll_ensure_accounting()
                label = self.env._('Adiantamento a %s', advance.employee_id.name)
                partner = advance.employee_id.work_contact_id
                move = self.env['account.move'].create(
                    {
                        'move_type': 'entry',
                        'journal_id': advance.journal_id.id,
                        'date': advance.date,
                        'ref': label,
                        'line_ids': [
                            fields.Command.create(
                                {
                                    'account_id': company.l10n_ao_payroll_advance_account_id.id,
                                    'partner_id': partner.id,
                                    'name': label,
                                    'debit': advance.amount,
                                }
                            ),
                            fields.Command.create(
                                {
                                    'account_id': advance.journal_id.default_account_id.id,
                                    'partner_id': partner.id,
                                    'name': label,
                                    'credit': advance.amount,
                                }
                            ),
                        ],
                    }
                )
                move.action_post()
                advance.move_id = move
            advance.state = 'approved'

    def action_cancel(self):
        for advance in self:
            if advance.deduction_ids.filtered(lambda d: d.payslip_id.state != 'cancelled'):
                raise UserError(self.env._('O adiantamento já foi amortizado numa folha.'))
            if advance.move_id and advance.move_id.state == 'posted':
                advance.move_id.button_draft()
                advance.move_id.button_cancel()
            advance.state = 'cancelled'

    def _settle_if_done(self):
        for advance in self:
            if advance.state == 'approved' and advance.currency_id.is_zero(advance.balance):
                advance.state = 'settled'


class L10nAoPayrollAdvanceDeduction(models.Model):
    _name = 'l10n_ao_payroll.advance.deduction'
    _description = 'Amortização de adiantamento'

    advance_id = fields.Many2one(
        'l10n_ao_payroll.advance', string='Adiantamento', required=True, ondelete='cascade', index=True
    )
    payslip_id = fields.Many2one(
        'l10n_ao_payroll.payslip', string='Recibo', required=True, ondelete='cascade', index=True
    )
    currency_id = fields.Many2one(related='advance_id.currency_id')
    amount = fields.Monetary(string='Valor', required=True)
