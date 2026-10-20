from odoo import api, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.depends('pos_session_sales_id', 'pos_session_refunds_id', 'pos_session_correction_id', 'reversed_pos_order_id')
    def _compute_l10n_ao_edi_required(self):
        return super()._compute_l10n_ao_edi_required()

    def _l10n_ao_edi_is_internal_move(self):
        # Movimentos de fecho de sessão (e as suas correcções): as vendas já foram comunicadas nos talões.
        if self.env.context.get('l10n_ao_edi_pos_session_move'):
            return True
        move = self.sudo()
        return (
            bool(
                move.pos_session_sales_id
                or move.pos_session_refunds_id
                or move.pos_session_correction_id
                or move.reversed_pos_order_id
            )
            or super()._l10n_ao_edi_is_internal_move()
        )
