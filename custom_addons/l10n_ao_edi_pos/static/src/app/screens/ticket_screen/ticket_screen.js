import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { RefundReasonPopup } from "@l10n_ao_edi_pos/app/components/refund_reason_popup/refund_reason_popup";

patch(TicketScreen.prototype, {
    async addAdditionalRefundInfo(order, destinationOrder) {
        if (this.pos.company.l10n_ao_edi_enabled) {
            // Art. 8.º do DP n.º 71/25: a nota de crédito indica o motivo.
            const payload = await makeAwaitable(this.dialog, RefundReasonPopup, {
                order: destinationOrder,
            });
            if (payload) {
                destinationOrder.l10n_ao_edi_reason = payload.reason;
            }
        }
        await super.addAdditionalRefundInfo(...arguments);
    },
});
