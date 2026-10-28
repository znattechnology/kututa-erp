from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import is_trusted, trusted
from odoo.exceptions import AccessError, UserError


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

    _PROTECTED = frozenset(
        {
            'move_id',
            'reason',
            'requested_by_id',
            'state',
            'decided_by_id',
            'decided_date',
            'decision_notes',
            'refund_id',
        }
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not is_trusted(self.env):
            # Quem pede é quem cria (não um colega escolhido pelo cliente): outro decide.
            vals_list = [
                dict(vals, requested_by_id=self.env.uid, state='pending', decided_by_id=False, refund_id=False)
                for vals in vals_list
            ]
        return super().create(vals_list)

    def write(self, vals):
        if not is_trusted(self.env) and self._PROTECTED & set(vals):
            raise AccessError(self.env._('O pedido de anulação só muda pela decisão (aprovar ou recusar).'))
        return super().write(vals)

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
        with trusted(self.env):
            self.write(values)
        return True
