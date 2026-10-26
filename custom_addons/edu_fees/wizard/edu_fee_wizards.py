import logging
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import split_every

from ..models.edu_fee_plan import BATCH, ENROLLED, MONTHS

_logger = logging.getLogger(__name__)


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


class EduFeeGenerate(models.TransientModel):
    """«Gerar agora»: as propinas em falta dos planos escolhidos até ao mês corrente, com o resumo antes de confirmar
    (alunos, facturas e total por mês). É o mesmo que a tarefa diária faz; não se gera nada enquanto a escola não
    puder emitir facturas certificadas pela AGT."""

    _name = 'edu.fee.generate'
    _description = 'Gerar as propinas'

    def _default_plans(self):
        plans = self.env['edu.fee.plan'].browse(self.env.context.get('active_ids') or [])
        if self.env.context.get('active_model') == 'edu.fee.plan' and plans:
            return plans
        return self.env['edu.fee.plan'].search([('academic_year_id.is_current', '=', True)])

    plan_ids = fields.Many2many(
        'edu.fee.plan', string='Planos', required=True, default=lambda self: self._default_plans()
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(string='Até ao mês de', default=fields.Date.context_today, readonly=True)
    issue = fields.Char(compute='_compute_preview')
    student_count = fields.Integer(string='Alunos', compute='_compute_preview')
    invoice_count = fields.Integer(string='Facturas', compute='_compute_preview')
    amount_total = fields.Monetary(string='Total', compute='_compute_preview')
    summary = fields.Html(compute='_compute_preview', sanitize=False)

    def _pending(self):
        """As cobranças em falta: [(plano, matrícula, linha, mês, chave, vencimento)]."""
        self.ensure_one()
        Plan = self.env['edu.fee.plan'].sudo()
        enrollments = (
            self.env['edu.enrollment']
            .sudo()
            .search(
                [
                    ('company_id', '=', self.company_id.id),
                    ('state', 'in', ENROLLED),
                    ('academic_year_id', 'in', self.plan_ids.academic_year_id.ids),
                ]
            )
        )
        pending = []
        for enrollment in enrollments:
            plan = Plan._for_enrollment(enrollment)
            if plan and plan in self.plan_ids:
                pending += [(plan, enrollment, *item) for item in plan._pending(enrollment, self.date)]
        return pending

    @api.depends('plan_ids', 'date')
    def _compute_preview(self):
        Plan = self.env['edu.fee.plan']
        for wizard in self:
            wizard.issue = Plan._edu_billing_issue(wizard.company_id, wizard.date) or False
            pending = wizard._pending() if wizard.plan_ids else []
            months = defaultdict(lambda: [0, 0.0])
            for _plan, enrollment, line, due, _key, _due_date in pending:
                cell = months[(due.year, due.month)]
                cell[0] += 1
                cell[1] += line._payable(enrollment, due)[0]
            wizard.student_count = len({item[1] for item in pending})
            wizard.invoice_count = len(pending)
            wizard.amount_total = sum(cell[1] for cell in months.values())
            money = wizard.currency_id.format if wizard.currency_id else str
            rows = ''.join(
                f'<tr><td>{MONTHS[month - 1]} {year}</td><td class="text-end">{count}</td>'
                f'<td class="text-end">{money(total)}</td></tr>'
                for (year, month), (count, total) in sorted(months.items())
            )
            wizard.summary = (
                '<table class="table table-sm mb-0"><thead><tr><th>Mês</th><th class="text-end">Facturas</th>'
                f'<th class="text-end">Total</th></tr></thead><tbody>{rows}</tbody></table>'
                if rows
                else False
            )

    def action_generate(self):
        self.ensure_one()
        if self.issue:
            raise UserError(self.issue)
        by_plan = defaultdict(lambda: self.env['edu.enrollment'])
        for plan, enrollment, *_rest in self._pending():
            by_plan[plan] |= enrollment
        created = self.env['account.move']
        failed = 0
        for plan, enrollments in by_plan.items():
            for ids in split_every(BATCH, enrollments.ids):
                for enrollment in enrollments.browse(ids):
                    try:
                        with self.env.cr.savepoint():
                            created |= plan.with_company(self.company_id)._generate(enrollment, self.date)
                    except Exception:
                        failed += 1
                        _logger.exception('Propinas: erro na geração da matrícula %s', enrollment.id)
        if not created:
            raise UserError(self.env._('Não há propinas em falta: está tudo facturado até %s.', self.date))
        message = self.env._('%s facturas emitidas.', len(created))
        if failed:
            message += ' ' + self.env._('%s matrículas deram erro (ver o registo do servidor).', failed)
        return {
            'type': 'ir.actions.act_window',
            'name': message,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
            'context': {'create': False},
        }
