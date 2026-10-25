import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const LIMIT = 10;

/**
 * O Painel da secretaria, como o dos Serviços Académicos do secPed, num quadro: o que está à espera de tratamento
 * (cada linha abre a lista onde se resolve), os números do ano, os alunos por classe, as turmas (as que têm alguma
 * coisa por resolver primeiro, com a ocupação e as notas lançadas) e os eventos das próximas duas semanas.
 */
export class SecretariaHome extends Component {
    static template = "edu_roles.SecretariaHome";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, all: false });
        onWillStart(async () => {
            this.state.data = await this.orm.call("edu.secretaria.home", "home_data", []);
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async open(key, resId = false) {
        const action = await this.orm.call("edu.secretaria.home", "open", [key, resId]);
        return this.action.doAction(action);
    }

    openAction(xmlid) {
        return this.action.doAction(xmlid);
    }

    get occupancy() {
        const k = this.state.data.kpis;
        return k.capacity ? Math.round((100 * k.students) / k.capacity) : null;
    }

    get occupancyWidth() {
        return Math.min(100, this.occupancy || 0);
    }

    /** Os alunos por classe, em barras do maior número para 100%. */
    get perClass() {
        const rows = this.state.data.per_class;
        const max = Math.max(1, ...rows.map((r) => r.count));
        return rows.map((r) => ({ ...r, width: r.count ? Math.max(2, (100 * r.count) / max) : 0 }));
    }

    /** Os alunos por curso (os mais numerosos primeiro), nas mesmas barras. */
    get perCourse() {
        const rows = this.state.data.per_course || [];
        const max = Math.max(1, ...rows.map((r) => r.count));
        return rows.map((r) => ({ ...r, width: r.count ? Math.max(2, (100 * r.count) / max) : 0 }));
    }

    /** O ícone de cada linha de «Por tratar». */
    pendingIcon(key) {
        return (
            {
                applications: "inbox",
                enrollments: "person_add",
                documents: "description",
                directors: "person",
                schedules: "calendar_today",
                teachers: "person_search",
                capacity: "groups",
            }[key] || "info"
        );
    }

    /** As chamadas feitas hoje face às aulas do horário de hoje. */
    get todayWidth() {
        const t = this.state.data.today;
        return t.planned ? Math.min(100, (100 * t.rolled) / t.planned) : 0;
    }

    /** Quanto falta para um evento: «A decorrer», «Hoje», «Amanhã» ou «Daqui a N dias». */
    whenLabel(event) {
        const now = new Date();
        const today = `${now.getFullYear()}-${`${now.getMonth() + 1}`.padStart(2, "0")}-${`${now.getDate()}`.padStart(2, "0")}`;
        if (event.start <= today && today <= event.end) {
            return event.start === event.end ? "Hoje" : "A decorrer";
        }
        const [y, m, d] = event.start.split("-").map(Number);
        const days = Math.round((Date.UTC(y, m - 1, d) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
        return days === 1 ? "Amanhã" : `Daqui a ${days} dias`;
    }

    get shortcuts() {
        return [
            { action: "edu_evaluation.action_edu_grade_grid", icon: "edit_document", label: "Lançar e imprimir pautas" },
            { action: "edu_timetable.action_edu_schedule_editor", icon: "calendar_today", label: "Construir horários" },
            { action: "edu_timetable.action_edu_teaching_assignment", icon: "person_search", label: "Atribuir professores" },
            { action: "edu_documents.action_edu_student_history_page", icon: "history_edu", label: "Histórico do aluno" },
            { action: "edu_documents.action_edu_document", icon: "description", label: "Documentos" },
            { action: "edu_fees.action_edu_debtors", icon: "payments", label: "Devedores" },
        ];
    }

    get classes() {
        const rows = this.state.data.classes;
        return this.state.all ? rows : rows.slice(0, LIMIT);
    }

    get hiddenClasses() {
        return Math.max(0, this.state.data.classes.length - LIMIT);
    }

    toggleAll() {
        this.state.all = !this.state.all;
    }

    occupancyClass(row) {
        return row.over ? "o_edu_meter_bad" : row.occupancy >= 90 ? "o_edu_meter_warn" : "";
    }
}

registry.category("actions").add("edu_roles.secretaria_home", SecretariaHome);
