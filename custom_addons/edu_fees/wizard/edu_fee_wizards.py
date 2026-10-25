from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class EduFeePayment(models.TransientModel):
    """Pagamento ao balcão: imputado às facturas em aberto do aluno, da mais antiga para a mais recente; o excedente
    fica como crédito do adquirente para as próximas facturas. Cada pagamento dá o recibo (RC) pela AGT."""

    _name = 'edu.fee.payment'
    _description = 'Pagamento de propinas'

    student_id = fields.Many2one('edu.student', string='Aluno', required=True)
    company_id = fields.Many2one(related='student_id.company_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    journal_id = fields.Many2one(
        'account.journal',
        string='Forma de pagamento',
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', self.env.company.id)], limit=1
        ),
    )
    amount = fields.Monetary(string='Valor recebido', required=True)
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    reference = fields.Char(string='Referência', help='N.º do talão do TPA, da transferência ou do depósito.')
    open_amount = fields.Monetary(related='student_id.edu_open_amount', string='Em aberto')
    invoice_ids = fields.Many2many('account.move', string='Facturas em aberto', compute='_compute_invoice_ids')

    @api.depends('student_id')
    def _compute_invoice_ids(self):
        for wizard in self:
            wizard.invoice_ids = wizard.student_id._edu_open_invoices().sorted(lambda m: (m.invoice_date_due, m.id))

    def action_confirm(self):
        self.ensure_one()
        if self.amount <= 0:
            raise ValidationError(self.env._('O valor recebido tem de ser positivo.'))
        invoices = self.invoice_ids
        partners = invoices.partner_id or self.student_id._edu_billing_partner()
        payments = self.env['account.payment']
        remaining = self.amount
        # Um pagamento por adquirente (o aluno ou o encarregado), pela ordem de antiguidade das suas facturas.
        for partner in partners:
            mine = invoices.filtered(lambda m, p=partner: m.partner_id == p)
            due = sum(mine.mapped('amount_residual'))
            value = remaining if partner == partners[-1] else min(remaining, due)
            if value <= 0:
                continue
            payment = self.env['account.payment'].create(
                {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': partner.id,
                    'amount': value,
                    'date': self.date,
                    'journal_id': self.journal_id.id,
                    'memo': self.reference or self.env._('Propinas de %s', self.student_id.name),
                }
            )
            payment.action_post()
            self._reconcile_oldest_first(payment, mine)
            payments |= payment
            remaining = self.currency_id.round(remaining - value)
        if not payments:
            raise UserError(self.env._('Não há nada a receber.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payments.ids)],
        }

    def _reconcile_oldest_first(self, payment, invoices):
        """Reconcilia o pagamento com as facturas, uma a uma, da mais antiga para a mais recente."""
        payment_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
        )
        for invoice in invoices.sorted(lambda m: (m.invoice_date_due, m.id)):
            if not payment_lines.filtered(lambda line: not line.reconciled):
                break
            invoice_lines = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
            )
            (payment_lines | invoice_lines).filtered(lambda line: not line.reconciled).reconcile()


class EduFeeService(models.TransientModel):
    """Cobrança de serviços a pedido (declarações, segundas vias, cartão, exames especiais…): uma factura."""

    _name = 'edu.fee.service'
    _description = 'Cobrança de serviço escolar'

    student_id = fields.Many2one('edu.student', string='Aluno', required=True)
    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', compute='_compute_enrollment_id', store=True, readonly=False
    )
    fee_line_id = fields.Many2one(
        'edu.fee.plan.line',
        string='Serviço',
        required=True,
        domain="[('plan_id.academic_year_id', '=', academic_year_id), "
        "('category', 'in', ('service', 'card', 'other', 'exam', 'application', 'transfer'))]",
    )
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id')
    quantity = fields.Float(string='Quantidade', default=1.0)
    reference = fields.Char(string='Referência', help='Evita cobrar duas vezes o mesmo pedido.')

    @api.depends('student_id')
    def _compute_enrollment_id(self):
        for wizard in self:
            wizard.enrollment_id = wizard.student_id.current_enrollment_id or wizard.student_id.enrollment_ids[:1]

    def action_confirm(self):
        self.ensure_one()
        if not self.enrollment_id:
            raise UserError(self.env._('O aluno não tem matrícula.'))
        if self.quantity <= 0:
            raise ValidationError(self.env._('A quantidade tem de ser positiva.'))
        key = False
        if self.reference:
            key = f'SVC-{self.fee_line_id.id}-{self.enrollment_id.id}-{self.reference}'
            existing = self.env['account.move'].search([('edu_generation_key', '=', key)], limit=1)
            if existing:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.move',
                    'res_id': existing.id,
                    'view_mode': 'form',
                }
        line = self.fee_line_id
        move = line._create_invoice(self.enrollment_id, fields.Date.context_today(self), key, quantity=self.quantity)
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': move.id, 'view_mode': 'form'}


class EduStudentCardRevoke(models.TransientModel):
    """Revogação do cartão (perda, roubo, dados errados). A 2.ª via segue o caminho de sempre: pagar e emitir."""

    _name = 'edu.student.card.revoke'
    _description = 'Revogar o cartão de estudante'

    student_id = fields.Many2one('edu.student', string='Aluno', required=True)
    reason = fields.Char(string='Motivo', required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.student_id.edu_card_id:
            raise UserError(self.env._('O aluno não tem cartão activo.'))
        self.student_id.edu_card_id.sudo()._revoke(self.reason)
        return {'type': 'ir.actions.act_window_close'}
