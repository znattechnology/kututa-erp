import { registry } from "@web/core/registry";
import { AcademicCalendarPage, TYPES } from "@edu_roles/academic_calendar/academic_calendar";

/**
 * O «Calendário» do encarregado: o calendário académico da escola com as provas de cada educando (o nome dele em cada
 * prova) e os educandos por cima, para ver só as provas de um. As datas comemorativas começam escondidas: no mês do
 * encarregado importam as provas, os feriados e as reuniões.
 */
export class GuardianCalendar extends AcademicCalendarPage {
    setup() {
        super.setup();
        this.types = [{ key: "child_exam", label: "Provas dos educandos" }, ...TYPES];
        this.state.filter = "all";
    }

    loadData() {
        return this.orm.call("edu.guardian.portal", "calendar_data", []);
    }

    get showCommemorative() {
        return false;
    }

    get subtitle() {
        return "As provas dos teus educandos, os feriados, as pausas e as reuniões da escola.";
    }

    get filters() {
        const children = this.state.data.children;
        if (children.length < 2) {
            return null;
        }
        return [{ key: "all", label: "Todos" }, ...children.map((c) => ({ key: c.id, label: c.name }))];
    }

    /** Com um educando escolhido, as provas só desse (os eventos da escola ficam sempre). */
    matchesFilter(event) {
        return this.state.filter === "all" || !event.child_id || event.child_id === this.state.filter;
    }
}

registry.category("actions").add("edu_portal.guardian_calendar", GuardianCalendar);
