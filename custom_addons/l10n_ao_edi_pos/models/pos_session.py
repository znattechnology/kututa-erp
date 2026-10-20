from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    # Os movimentos de fecho de sessão (e as correcções quando uma venda é facturada depois do fecho) são
    # lançamentos contabilísticos das vendas já comunicadas nos talões: não são documentos AGT.
    def _create_session_account_move(self, orders):
        return super(PosSession, self.with_context(l10n_ao_edi_pos_session_move=True))._create_session_account_move(
            orders
        )

    def _create_partial_reversal_move_from_session_closing(self, orders):
        return super(
            PosSession, self.with_context(l10n_ao_edi_pos_session_move=True)
        )._create_partial_reversal_move_from_session_closing(orders)
