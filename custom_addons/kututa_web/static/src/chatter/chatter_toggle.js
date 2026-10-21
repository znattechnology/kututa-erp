import { Component, useListener } from "@odoo/owl";
import { SIZES } from "@web/core/ui/ui_utils";
import { patch } from "@web/core/utils/patch";
import { render } from "@web/owl2/utils";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";

import { getPreference, setPreference } from "../ui_preferences";

const TOGGLE_EVENT = "KUTUTA:CHATTER-TOGGLED";

export function isChatterOpen() {
    return getPreference("chatter_open", false);
}

/**
 * Botão «Mensagens» no topo do formulário: abre e fecha o painel de mensagens e actividades.
 */
export class ChatterToggle extends Component {
    static template = "kututa_web.ChatterToggle";

    setup() {
        useListener(this.env.bus, TOGGLE_EVENT, () => render(this));
    }

    get open() {
        return isChatterOpen();
    }

    toggle() {
        setPreference("chatter_open", !this.open);
        this.env.bus.trigger(TOGGLE_EVENT);
    }
}

FormController.components = { ...FormController.components, ChatterToggle };

patch(FormController.prototype, {
    /** O formulário tem painel de mensagens (<chatter/> na vista). */
    get kututaHasChatter() {
        const xmlDoc = this.archInfo?.xmlDoc;
        return Boolean(
            !this.env.inDialog && xmlDoc && xmlDoc.querySelector("chatter, div.oe_chatter, .o-mail-Form-chatter")
        );
    },
});

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        useListener(this.env.bus, TOGGLE_EVENT, () => render(this));
    },
    mailLayout(hasAttachmentContainer) {
        const layout = super.mailLayout(...arguments);
        if (layout === "NONE" || this.env.inDialog) {
            return layout;
        }
        if (!isChatterOpen()) {
            return "NONE";
        }
        // Aberto: ao lado a partir dos ecrãs médios (o painel é mais estreito do que no Odoo).
        if (layout === "BOTTOM_CHATTER" && this.uiService.size >= SIZES.XL) {
            return "SIDE_CHATTER";
        }
        return layout;
    },
});
