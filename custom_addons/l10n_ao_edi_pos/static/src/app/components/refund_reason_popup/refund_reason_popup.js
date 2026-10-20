import { Dialog } from "@web/core/dialog/dialog";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { Component, proxy, t, useProps } from "@odoo/owl";

export const REFUND_REASONS = [
    "Devolução de artigos",
    "Artigo com defeito",
    "Erro de registo",
    "Anulação da venda",
];

export class RefundReasonPopup extends Component {
    static template = "l10n_ao_edi_pos.RefundReasonPopup";
    static components = { Dialog };

    props = useProps({
        close: t.function(),
        getPayload: t.function(),
        order: t.instanceOf(PosOrder),
    });

    setup() {
        this.reasons = REFUND_REASONS;
        this.state = proxy({ selected: REFUND_REASONS[0], custom: this.props.order.l10n_ao_edi_reason || "" });
    }

    get reason() {
        return (this.state.custom.trim() || this.state.selected).slice(0, 60);
    }

    get isValid() {
        return Boolean(this.reason);
    }

    confirm() {
        this.props.getPayload({ reason: this.reason });
        this.props.close();
    }
}
