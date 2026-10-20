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
        # O talão sem preços (oferta) não é o documento fiscal: não leva o n.º AGT nem conta como impressão.
        number = not basic_receipt and self.l10n_ao_edi_receipt_number
        data['conditions'].update(
            {
                'l10n_ao_edi': not basic_receipt,
                'l10n_ao_edi_provisional': not basic_receipt and not number and self.state != 'draft',
                # A factura de uma venda com talão não é permitida: sem convite à auto-facturação.
                'use_self_invoicing': False,
            }
        )
        data['image']['l10n_ao_edi_qr_code'] = (
            self._order_receipt_generate_qr_code(self.l10n_ao_edi_receipt_qr_url) if number else False
        )
        data['extra_data']['l10n_ao_edi_copy_label'] = self._l10n_ao_edi_copy_label()
        # Motivos de isenção / não sujeição dos impostos usados (DP n.º 71/25).
        data['extra_data']['l10n_ao_edi_legal_notes'] = list(
            dict.fromkeys(filter(None, self.lines.tax_ids_after_fiscal_position.mapped('l10n_ao_edi_legal_note')))
        )
        return data

    def order_receipt_generate_image(self, basic_receipt=False, width=500, height=0):
        """Talão gerado no servidor (impressão no backend, envio por email): conta como impressão."""
        image = super().order_receipt_generate_image(basic_receipt, width, height)
        if not basic_receipt and self.l10n_ao_edi_receipt_number:
            self.sudo().l10n_ao_edi_print_count += 1
        return image
