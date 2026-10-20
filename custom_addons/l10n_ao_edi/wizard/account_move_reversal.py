from odoo import models


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def _prepare_default_reversal(self, move):
        # O motivo da nota de crédito vai à AGT tal como o utilizador o escreveu (referenceInfo.reason, 60 caracteres),
        # sem o prefixo «Estorno de: …» que o Odoo junta à referência.
        values = super()._prepare_default_reversal(move)
        if self.reason:
            values['l10n_ao_edi_reason'] = self.reason
        return values
