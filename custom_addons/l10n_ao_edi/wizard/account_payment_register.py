from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        # Art. 6.º do DP n.º 71/25: cada recebimento de facturas dá lugar a um recibo.
        payments = super()._create_payments()
        payments._l10n_ao_edi_issue_receipt()
        return payments
