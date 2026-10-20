import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import {
    REFUND_REASONS,
    RefundReasonPopup,
} from "@l10n_ao_edi_pos/app/components/refund_reason_popup/refund_reason_popup";

patch(TicketScreen.prototype, {
    async addAdditionalRefundInfo(order, destinationOrder) {
        if (this.pos.company.l10n_ao_edi_enabled) {
            // Art. 8.º do DP n.º 71/25: a nota de crédito indica o motivo.
            const payload = await makeAwaitable(this.dialog, RefundReasonPopup, {
                order: destinationOrder,
            });
            // Sem motivo escolhido (janela fechada), fica o motivo genérico: a NC não pode seguir sem motivo.
            destinationOrder.l10n_ao_edi_reason = payload?.reason || REFUND_REASONS[0];
        }
        await super.addAdditionalRefundInfo(...arguments);
    },
});
