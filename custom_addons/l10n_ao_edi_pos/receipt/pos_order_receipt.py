from odoo import models


class PosOrderReceipt(models.AbstractModel):
    _inherit = 'pos.order.receipt'

    def _l10n_ao_edi_copy_label(self):
        return 'Original' if not self.l10n_ao_edi_print_count else '2.ª via'

    def order_receipt_generate_data(self, basic_receipt=False):
        """Espelho de GeneratePrinterData.generateReceiptData (static/src/app/utils/printer)."""
        data = super().order_receipt_generate_data(basic_receipt)
        if not self.company_id.l10n_ao_edi_enabled:
            return data
        number = self.l10n_ao_edi_receipt_number
        data['conditions'].update(
            {
                'l10n_ao_edi': True,
                'l10n_ao_edi_provisional': not number and self.state != 'draft',
                # A factura de uma venda com talão não é permitida: sem convite à auto-facturação.
                'use_self_invoicing': False,
            }
        )
        data['image']['l10n_ao_edi_qr_code'] = (
            self._order_receipt_generate_qr_code(self.l10n_ao_edi_receipt_qr_url) if number else False
        )
        data['extra_data']['l10n_ao_edi_copy_label'] = self._l10n_ao_edi_copy_label()
        return data
