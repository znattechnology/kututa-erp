from odoo import api, models
from odoo.exceptions import UserError

from .account_move import EDI_LOCKED_STATES


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.ondelete(at_uninstall=False)
    def _unlink_except_l10n_ao_edi_receipt(self):
        # O recibo comunicado à AGT refere as facturas que liquidou: o pagamento não pode ser desligado delas.
        # Só a reconciliação com as facturas (contas a receber); a reconciliação bancária pode ser desfeita.
        receivable = self.filtered(lambda p: p.debit_move_id.account_id.account_type == 'asset_receivable')
        moves = receivable.debit_move_id.move_id | receivable.credit_move_id.move_id
        payments = moves.origin_payment_id.filtered(lambda p: p.l10n_ao_edi_state in EDI_LOCKED_STATES)
        if payments:
            raise UserError(
                self.env._(
                    'O recibo %s já foi emitido e comunicado à AGT: o pagamento não pode ser desconciliado.',
                    ', '.join(payments.mapped('l10n_ao_edi_document_no')),
                )
            )
