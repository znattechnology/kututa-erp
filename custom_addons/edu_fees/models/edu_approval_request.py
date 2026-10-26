from odoo import fields, models
from odoo.exceptions import UserError


class EduApprovalRequest(models.Model):
    """Pedido de anulação de uma factura, para o segundo par de olhos do secPed: anular reduz dívida, por isso fica
    pedido (com a justificação) até outro utilizador o aprovar; aprovar emite a nota de crédito. Quem pediu não pode
    decidir o próprio pedido. (As bolsas e o numerário alto têm o seu próprio pedido: a bolsa por aprovar e o
    pagamento em numerário por validar.)"""

    _name = 'edu.approval.request'
    _description = 'Pedido de aprovação'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    kind = fields.Selection([('void', 'Anular uma factura')], string='Pedido', default='void', required=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, readonly=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    move_id = fields.Many2one('account.move', string='Factura', required=True, readonly=True, check_company=True)
    student_id = fields.Many2one(related='move_id.edu_student_id', store=True)
    amount = fields.Monetary(related='move_id.amount_total', string='Valor')
    reason = fields.Text(string='Justificação', required=True, readonly=True)
    requested_by_id = fields.Many2one(
        'res.users', string='Pedido por', required=True, readonly=True, default=lambda self: self.env.user
    )
    state = fields.Selection(
        [('pending', 'Pendente'), ('approved', 'Aprovado'), ('rejected', 'Recusado')],
        string='Estado',
        default='pending',
        required=True,
        readonly=True,
        tracking=True,
    )
    decided_by_id = fields.Many2one('res.users', string='Decidido por', readonly=True)
    decided_date = fields.Datetime(string='Decidido em', readonly=True)
    decision_notes = fields.Text(string='Notas da decisão', readonly=True)
    refund_id = fields.Many2one('account.move', string='Nota de crédito', readonly=True)

    def _decide(self, approve, notes=False):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(self.env._('O pedido já foi decidido.'))
        if self.requested_by_id == self.env.user:
            raise UserError(self.env._('Quem pede não pode decidir o próprio pedido.'))
        if not approve and not (notes or '').strip():
            raise UserError(self.env._('Escreva porque recusa o pedido.'))
        values = {
            'state': 'approved' if approve else 'rejected',
            'decided_by_id': self.env.uid,
            'decided_date': fields.Datetime.now(),
            'decision_notes': notes or False,
        }
        if approve:
            values['refund_id'] = self.move_id._edu_void(self.reason).id
        self.write(values)
        return True
