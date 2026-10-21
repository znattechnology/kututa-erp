import { Component, useLayoutEffect, useListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { render } from "@web/owl2/utils";
import { WebClient } from "@web/webclient/webclient";

import { getPreference, setPreference } from "../ui_preferences";

/**
 * Menu lateral com as secções da aplicação aberta (as mesmas do menu de topo), todas abertas, com os títulos
 * destacados; o menu inteiro recolhe-se.
 */
export class KututaSidebar extends Component {
    static template = "kututa_web.Sidebar";

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.ui = useService("ui");
        this.collapsed = getPreference("sidebar_collapsed", false);
        const refresh = () => render(this);
        useListener(this.env.bus, "MENUS:APP-CHANGED", refresh);
        useListener(this.env.bus, "ACTION_MANAGER:UI-UPDATED", refresh);
        useListener(window, "resize", refresh);
        useLayoutEffect(
            (visible, collapsed) => {
                document.body.classList.toggle("o_kututa_with_sidebar", visible);
                document.body.classList.toggle("o_kututa_sidebar_collapsed", visible && collapsed);
            },
            () => [this.visible, this.collapsed]
        );
    }

    get app() {
        return this.menuService.getCurrentApp();
    }

    get sections() {
        const app = this.app;
        return app ? this.menuService.getMenuAsTree(app.id).childrenTree || [] : [];
    }

    /**
     * Secções com as entradas já achatadas: [{ section, entries: [{ menu, depth, isGroup }] }].
     * As secções sem filhos aparecem como uma entrada solta.
     */
    get blocks() {
        const flatten = (menus, depth, entries) => {
            for (const menu of menus) {
                const children = menu.childrenTree || [];
                entries.push({ menu, depth, isGroup: children.length > 0 });
                flatten(children, depth + 1, entries);
            }
            return entries;
        };
        return this.sections.map((section) => {
            const children = section.childrenTree || [];
            const entries = children.length ? flatten(children, 0, []) : [{ menu: section, depth: 0, isGroup: false }];
            return {
                section,
                hasTitle: children.length > 0,
                entries,
            };
        });
    }

    get visible() {
        return Boolean(this.app && this.sections.length && !this.ui.isSmall);
    }

    get currentActionId() {
        return this.actionService.currentController?.action?.id;
    }

    isActive(menu) {
        return Boolean(menu.actionID) && menu.actionID === this.currentActionId;
    }

    async onClickMenu(menu) {
        await this.menuService.selectMenu(menu);
        render(this);
    }

    toggle() {
        this.collapsed = !this.collapsed;
        setPreference("sidebar_collapsed", this.collapsed);
        render(this);
    }
}

WebClient.components = { ...WebClient.components, KututaSidebar };
