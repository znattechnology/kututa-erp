from odoo import api, fields, models
from odoo.exceptions import UserError

METHODS = [('transfer', 'Transferência bancária'), ('deposit', 'Depósito bancário')]


class EduFeePaymentRequest(models.Model):
    """Pagamento enviado pelo portal, como no secPed: o encarregado (ou o aluno) diz que pagou por transferência ou
    depósito, com o comprovativo e as facturas que paga (sem escolha, as mais antigas). A tesouraria confere o
    comprovativo e valida, o que regista o pagamento, o imputa às facturas e emite o recibo; ou rejeita, com o motivo,
    e quem enviou é avisado."""

    _name = 'edu.fee.payment.request'
    _description = 'Pagamento enviado pelo portal'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    student_id = fields.Many2one('edu.student', string='Aluno', required=True, readonly=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, readonly=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    submitted_by_id = fields.Many2one('res.users', string='Enviado por', readonly=True)
    method = fields.Selection(METHODS, string='Forma de pagamento', required=True, readonly=True)
    amount = fields.Monetary(string='Valor', required=True, readonly=True)
    date = fields.Date(string='Data do pagamento', required=True, readonly=True)
    reference = fields.Char(string='Referência', readonly=True, help='N.º da transferência ou do talão do depósito.')
    proof = fields.Binary(string='Comprovativo', attachment=True, readonly=True)
    proof_name = fields.Char(string='Ficheiro do comprovativo', readonly=True)
    invoice_ids = fields.Many2many(
        'account.move',
        string='Facturas indicadas',
        readonly=True,
        help='As facturas que quem pagou escolheu; sem escolha, o pagamento vai para as mais antigas.',
    )
    state = fields.Selection(
        [('pending', 'Por validar'), ('confirmed', 'Validado'), ('rejected', 'Rejeitado')],
        string='Estado',
        default='pending',
        required=True,
        readonly=True,
        tracking=True,
        index=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Conta onde entrou',
        check_company=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.env.company.id)], limit=1
        ),
    )
    reject_reason = fields.Text(string='Motivo da rejeição')
    verified_by_id = fields.Many2one('res.users', string='Tratado por', readonly=True)
    verified_date = fields.Datetime(string='Tratado em', readonly=True)
    payment_ids = fields.Many2many('account.payment', string='Pagamentos', readonly=True, copy=False)
    open_amount = fields.Monetary(related='student_id.edu_open_amount', string='Em aberto do aluno')

    @api.depends('student_id', 'amount', 'date')
    def _compute_display_name(self):
        for request in self:
            amount = request.currency_id.format(request.amount) if request.currency_id else request.amount
            request.display_name = f'{request.student_id.name} · {amount} · {request.date or ""}'

    def action_confirm(self):
        """Regista o pagamento na conta indicada, imputa-o às facturas (as escolhidas primeiro, depois as mais
        antigas) e emite o recibo, como o «Receber pagamento» da tesouraria."""
        for request in self:
            if request.state != 'pending':
                raise UserError(self.env._('Este pagamento já foi tratado.'))
            if not request.journal_id:
                raise UserError(self.env._('Escolha a conta onde o pagamento entrou.'))
            wizard = self.env['edu.fee.payment'].create(
                {
                    'student_id': request.student_id.id,
                    'journal_id': request.journal_id.id,
                    'amount': request.amount,
                    'date': request.date,
                    'reference': request.reference or self.env._('Pagamento pelo portal'),
                    'selected_invoice_ids': [fields.Command.set(request.invoice_ids.ids)],
                }
            )
            action = wizard.action_confirm()
            payments = self.env['account.payment'].search(action['domain'])
            request.write(
                {
                    'state': 'confirmed',
                    'payment_ids': [fields.Command.set(payments.ids)],
                    'verified_by_id': self.env.user.id,
                    'verified_date': fields.Datetime.now(),
                }
            )
            request._notify_submitter(
                self.env._(
                    'O pagamento de %(amount)s de %(date)s foi validado pela tesouraria.',
                    amount=request.currency_id.format(request.amount),
                    date=request.date.strftime('%d/%m/%Y'),
                )
            )
        return True

    def action_reject(self):
        for request in self:
            if request.state != 'pending':
                raise UserError(self.env._('Este pagamento já foi tratado.'))
            if not (request.reject_reason or '').strip():
                raise UserError(self.env._('Escreva o motivo da rejeição: quem pagou vai lê-lo no portal.'))
            request.write(
                {'state': 'rejected', 'verified_by_id': self.env.user.id, 'verified_date': fields.Datetime.now()}
            )
            request._notify_submitter(
                self.env._(
                    'O pagamento de %(amount)s de %(date)s não foi aceite: %(reason)s',
                    amount=request.currency_id.format(request.amount),
                    date=request.date.strftime('%d/%m/%Y'),
                    reason=request.reject_reason,
                )
            )
        return True

    def _notify_submitter(self, body):
        """Deixa a nota no histórico; quem enviou vê o estado (e o motivo) nas propinas e nas novidades do portal."""
        self.ensure_one()
        self.message_post(body=body)
