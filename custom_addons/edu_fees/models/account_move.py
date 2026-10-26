from odoo import fields, models
from odoo.exceptions import UserError

from .edu_fee_plan import CATEGORIES


class AccountMove(models.Model):
    _inherit = 'account.move'

    edu_student_id = fields.Many2one('edu.student', string='Aluno', index=True, copy=False)
    edu_enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', index=True, copy=False)
    edu_fee_line_id = fields.Many2one('edu.fee.plan.line', string='Taxa', copy=False)
    edu_category = fields.Selection(CATEGORIES + [('late_fee', 'Multa')], string='Categoria escolar', copy=False)
    edu_due_period = fields.Date(string='Vencimento da taxa', copy=False)
    edu_generation_key = fields.Char(string='Chave de geração', copy=False, index=True)
    edu_discount = fields.Monetary(string='Desconto da bolsa', copy=False)
    edu_exempt = fields.Boolean(string='Isenta pela bolsa', copy=False)
    edu_late_fee_origin_id = fields.Many2one('account.move', string='Factura em atraso', copy=False, index=True)

    _edu_generation_key_uniq = models.UniqueIndex(
        '(company_id, edu_generation_key) WHERE edu_generation_key IS NOT NULL',
        'Esta cobrança já foi gerada.',
    )

    def action_edu_request_void(self, reason):
        """Anular a factura (nota de crédito): já, ou pedida a outro utilizador quando a escola o exige."""
        self.ensure_one()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(self.env._('A justificação é obrigatória.'))
        self._edu_check_voidable()
        if not self.company_id.edu_void_approval:
            self._edu_void(reason)
            return 'voided'
        Request = self.env['edu.approval.request']
        if Request.search_count([('move_id', '=', self.id), ('state', '=', 'pending')]):
            raise UserError(self.env._('Já existe um pedido pendente para anular esta factura.'))
        Request.create({'move_id': self.id, 'reason': reason})
        return 'requested'

    def _edu_check_voidable(self):
        if self.move_type != 'out_invoice' or self.state != 'posted' or not self.edu_student_id:
            raise UserError(self.env._('Só se anulam facturas escolares emitidas.'))
        if self.payment_state != 'not_paid':
            raise UserError(
                self.env._(
                    'A factura %s já tem pagamentos: não se anula (o pagamento teria de ser devolvido).', self.name
                )
            )

    def _edu_void(self, reason):
        """A nota de crédito da factura inteira, com o motivo (a AGT pede-o), reconciliada com a factura."""
        self.ensure_one()
        self._edu_check_voidable()
        refund = self._reverse_moves(
            [
                {
                    'l10n_ao_edi_reason': reason[:250],
                    'invoice_date': fields.Date.context_today(self),
                    'edu_student_id': self.edu_student_id.id,
                    'edu_enrollment_id': self.edu_enrollment_id.id,
                    'edu_category': self.edu_category,
                }
            ],
            cancel=True,
        )
        return refund
