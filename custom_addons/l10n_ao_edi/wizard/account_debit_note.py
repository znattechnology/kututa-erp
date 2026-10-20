from odoo import models


class AccountDebitNote(models.TransientModel):
    _inherit = 'account.debit.note'

    def _prepare_default_values(self, move):
        # O motivo da nota de débito vai à AGT tal como o utilizador o escreveu (referenceInfo.reason).
        values = super()._prepare_default_values(move)
        if self.reason:
            values['l10n_ao_edi_reason'] = self.reason
        return values
