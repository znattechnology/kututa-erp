import { Component, useLayoutEffect, useListener } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { render } from "@web/owl2/utils";

/**
 * Barra de separadores do telemóvel, como a do secPed (BarraInferior): os atalhos que a área usa todos os dias e um
 * «Menu» que abre as secções da aplicação (o menu do Odoo no telemóvel). Cada área regista os seus atalhos em
 * ``edu_mobile_tabs`` com o xmlid da aplicação (o menu de topo); a barra aparece só nessa aplicação.
 */
export const mobileTabs = registry.category("edu_mobile_tabs");

export class EduMobileTabs extends Component {
    static template = "edu_roles.MobileTabs";

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        const refresh = () => render(this);
        useListener(this.env.bus, "MENUS:APP-CHANGED", refresh);
        useListener(this.env.bus, "ACTION_MANAGER:UI-UPDATED", refresh);
        // Espaço no fundo da página (só no telemóvel, pelo CSS) para a barra não tapar o fim do conteúdo.
        useLayoutEffect(
            (visible) => document.body.classList.toggle("o_edu_with_mobile_tabs", visible),
            () => [Boolean(this.tabs)]
        );
    }

    /** Os atalhos da aplicação aberta (a barra só se vê no telemóvel: ``d-md-none``). */
    get tabs() {
        const app = this.menuService.getCurrentApp();
        const area = app && mobileTabs.getAll().find((a) => a.app === app.xmlid);
        return area ? area.tabs : null;
    }

    isActive(tab) {
        // `currentAction` é assíncrono no Odoo 20; o controlador actual tem a acção já carregada.
        const action = this.actionService.currentController?.action;
        if (!action) {
            return false;
        }
        // As acções cliente reconhecem-se pela tag; as listas e os formulários pelo xmlid da acção.
        return tab.tag ? action.tag === tab.tag : action.xml_id === tab.action;
    }

    /** Fora dos atalhos, o «Menu» fica marcado: é por lá que se chegou. */
    get menuActive() {
        return !this.tabs.some((tab) => this.isActive(tab));
    }

    open(tab) {
        return this.actionService.doAction(tab.action, { clearBreadcrumbs: true });
    }

    openMenu() {
        document.querySelector(".o_navbar .o_menu_toggle")?.click();
    }
}

registry.category("main_components").add("edu_roles.MobileTabs", { Component: EduMobileTabs });

// O professor no telemóvel, como no secPed: o painel, as turmas, a chamada (que se faz na sala) e o horário.
mobileTabs.add("teacher", {
    app: "edu_roles.menu_edu_teacher_root",
    tabs: [
        { label: "Painel", icon: "home", action: "edu_roles.action_teacher_home", tag: "edu_roles.teacher_home" },
        { label: "Turmas", icon: "school", action: "edu_evaluation.action_edu_grade_grid", tag: "edu_evaluation.grade_grid" },
        { label: "Chamada", icon: "how_to_reg", action: "edu_roles.action_teacher_attendance", tag: "edu_roles.attendance" },
        { label: "Horário", icon: "calendar_month", action: "edu_roles.action_teacher_schedule", tag: "edu_roles.teacher_schedule" },
    ],
});

// A secretaria no telemóvel (os «Serviços académicos» do secPed): o painel, as matrículas, os alunos e as pautas.
mobileTabs.add("secretaria", {
    app: "edu_core.menu_edu_root",
    tabs: [
        { label: "Painel", icon: "home", action: "edu_roles.action_secretaria_home", tag: "edu_roles.secretaria_home" },
        { label: "Matrículas", icon: "assignment", action: "edu_enrollment.action_edu_enrollment" },
        { label: "Alunos", icon: "groups", action: "edu_people.action_edu_student" },
        { label: "Pautas", icon: "school", action: "edu_evaluation.action_edu_grade_grid", tag: "edu_evaluation.grade_grid" },
    ],
});
