import { patch } from "@web/core/utils/patch";
import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";

/**
 * Espelho de PosOrderReceipt.order_receipt_generate_data (l10n_ao_edi_pos/receipt).
 */
patch(GeneratePrinterData.prototype, {
    generateReceiptData() {
        const data = super.generateReceiptData(...arguments);
        if (!this.company.l10n_ao_edi_enabled) {
            return data;
        }
        // O talão sem preços (oferta) não é o documento fiscal: não leva o n.º AGT.
        const fiscal = !this.basicReceipt;
        const number = fiscal && this.order.l10n_ao_edi_receipt_number;
        Object.assign(data.conditions, {
            l10n_ao_edi: fiscal,
            l10n_ao_edi_provisional: fiscal && !number && this.order.finalized,
            use_self_invoicing: false,
        });
        data.image.l10n_ao_edi_qr_code = number
            ? this.generateQrCode(this.order.l10n_ao_edi_receipt_qr_url)
            : false;
        data.extra_data.l10n_ao_edi_copy_label = this.order.l10n_ao_edi_print_count
            ? "2.ª via"
            : "Original";
        // Motivos de isenção / não sujeição dos impostos usados (DP n.º 71/25).
        const notes = this.order.lines.flatMap((line) =>
            line.tax_ids.map((tax) => tax.l10n_ao_edi_legal_note).filter(Boolean)
        );
        data.extra_data.l10n_ao_edi_legal_notes = [...new Set(notes)];
        return data;
    },
});
