import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    /**
     * O talão só se imprime depois de o servidor atribuir o n.º AGT (série e numeração sem falhas).
     * Sem ligação, o POS continua a vender e imprime um talão provisório.
     */
    waitForPushOrder() {
        return this.company.l10n_ao_edi_enabled ? true : super.waitForPushOrder(...arguments);
    },
});
