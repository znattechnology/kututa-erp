import { patch } from "@web/core/utils/patch";
import { PosTicketPrinterPlugin } from "@point_of_sale/app/plugins/pos_ticket_printer_plugin";

patch(PosTicketPrinterPlugin.prototype, {
    /**
     * Cada impressão do documento AGT fica registada no servidor: a primeira é o «Original»,
     * as seguintes levam a menção «2.ª via».
     */
    async printOrderReceipt({ order, printBillActionTriggered = false } = {}) {
        const result = await super.printOrderReceipt(...arguments);
        if (result && !printBillActionTriggered && order?.l10n_ao_edi_receipt_number) {
            order.l10n_ao_edi_print_count = (order.l10n_ao_edi_print_count || 0) + 1;
            if (order.isSynced) {
                try {
                    const [values] = await this.data.call("pos.order", "l10n_ao_edi_register_print", [
                        [order.id],
                    ]);
                    order.l10n_ao_edi_print_count = values?.l10n_ao_edi_print_count ?? order.l10n_ao_edi_print_count;
                } catch {
                    // Sem ligação: a contagem local mantém a «2.ª via» nas reimpressões deste posto.
                }
            }
        }
        return result;
    },
});
