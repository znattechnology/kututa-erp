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
        // A aplicação encontrada pela acção passa para o Odoo, para a barra de topo mostrar o seu nome.
        useLayoutEffect(
            (app) => {
                if (app && !this.menuService.getCurrentApp()) {
                    this.menuService.setCurrentMenu(app);
                }
            },
            () => [this.app]
        );
        useLayoutEffect(
            (visible, collapsed) => {
                document.body.classList.toggle("o_kututa_with_sidebar", visible);
                document.body.classList.toggle("o_kututa_sidebar_collapsed", visible && collapsed);
            },
            () => [this.visible, this.collapsed]
        );
    }

    /**
     * A aplicação do menu lateral. Alguns ecrãs não pertencem a um menu (a pré-visualização de um relatório) e um
     * endereço aberto directamente não indica a aplicação: fica a última aplicação aberta ou, sem ela, a que tem a
     * acção aberta nos seus menus (ou a primeira, a de entrada).
     */
    get app() {
        const current = this.menuService.getCurrentApp();
        if (current) {
            this.lastApp = current;
        } else if (!this.lastApp) {
            this.lastApp = this.appForCurrentAction();
        }
        return current || this.lastApp;
    }

    appForCurrentAction() {
        const actionId = this.currentActionId;
        if (!actionId) {
            return undefined;
        }
        const apps = this.menuService.getApps();
        const contains = (menu) => menu.actionID === actionId || (menu.childrenTree || []).some(contains);
        // Sem menu com esta acção (por exemplo, aberta por uma acção de servidor): a primeira aplicação, a de entrada.
        return apps.find((app) => contains(this.menuService.getMenuAsTree(app.id))) || apps[0];
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

    /**
     * O item da página aberta. Os menus que abrem por uma acção de servidor (por exemplo Turmas, que abre no ano
     * em curso) chegam a uma acção com outro id: vale então o último item clicado.
     */
    isActive(menu) {
        const current = this.currentActionId;
        if (menu.actionID && menu.actionID === current) {
            return true;
        }
        const matched = this.blocks.some((block) => block.entries.some((entry) => entry.menu.actionID === current));
        return !matched && menu.id === this.selectedMenuId;
    }

    async onClickMenu(menu) {
        this.selectedMenuId = menu.id;
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
