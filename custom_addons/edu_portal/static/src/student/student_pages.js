import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const list = (items) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} e ${items[items.length - 1]}` : items[0] || "");
const count = (n, one, many) => (n === 1 ? one : `${n} ${many}`);

/**
 * A Área do Estudante, como a do secPed-Express e com o aspecto das páginas do professor: cada página pede os seus
 * dados a ``edu.student.portal.page_data`` (sempre os do aluno do utilizador) e mostra-os em cartões.
 */
class StudentPage extends Component {
    static components = { Layout };
    static page = "";

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, busy: false });
        this.list = list;
        this.count = count;
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load(options = {}) {
        this.state.data = await this.orm.call("edu.student.portal", "page_data", [this.constructor.page, options]);
    }

    open(xmlid) {
        return this.action.doAction(xmlid);
    }

    /** Uma nota a azul se é positiva e a vermelho se é negativa (a cor do sistema, como na grelha do professor). */
    gradeClass(grade, strong = false) {
        if (!grade) {
            return "text-muted";
        }
        return `${grade.pos ? "text-primary" : "text-danger"}${strong ? " fw-semibold" : ""}`;
    }

    gradeText(grade) {
        return grade ? grade.text : "—";
    }
}

export class StudentHome extends StudentPage {
    static template = "edu_portal.StudentHome";
    static page = "home";

    get greeting() {
        const hour = new Date().getHours();
        const hello = hour < 12 ? "Bom dia" : hour < 19 ? "Boa tarde" : "Boa noite";
        return `${hello}, ${this.state.data.first_name}`;
    }

    get missed() {
        const a = this.state.data.absences;
        return a.total - a.present;
    }
}

export class StudentGrades extends StudentPage {
    static template = "edu_portal.StudentGrades";
    static page = "grades";

    selectTrimester(trimester) {
        return this.load({ enrollment_id: this.state.data.grades.enrollment_id, trimester_id: trimester.id });
    }

    /** Outro ano lectivo: as notas desse ano, a abrir no último trimestre com notas. */
    selectYear(ev) {
        return this.load({ enrollment_id: parseInt(ev.target.value, 10) });
    }

    get macLabel() {
        return this.state.data.grades.technical ? "NPP" : "MAC";
    }

    get examLabel() {
        return this.state.data.grades.technical ? "NPT" : "Prova";
    }

    get components() {
        return [...Array(this.state.data.grades.components).keys()];
    }

    component(cell, index) {
        return cell.components[index] ? cell.components[index].value : null;
    }
}

export class StudentSchedule extends StudentPage {
    static template = "edu_portal.StudentSchedule";
    static page = "schedule";

    lessonsOn(day) {
        return this.state.data.lessons.filter((lesson) => lesson.weekday === day.number);
    }

    /** A folha A4 da secretaria: na aplicação (Visualizar) ou em PDF (Exportar PDF), como no horário do professor. */
    async openReport(preview) {
        const action = await this.orm.call("edu.student.portal", "schedule_report", [preview]);
        return this.action.doAction(action);
    }
}

export class StudentExams extends StudentPage {
    static template = "edu_portal.StudentExams";
    static page = "exams";

    /** «3 provas em 2 dias. A próxima: hoje, às 08:00, Matemática, Sala 3.», como no secPed. */
    get sentence() {
        const e = this.state.data.exams;
        let text = `${count(e.count, "Uma prova", "provas")} em ${count(e.days, "um dia", "dias")}.`;
        const next = e.next;
        if (next) {
            const day = next.today ? "hoje" : next.day.charAt(0).toLowerCase() + next.day.slice(1);
            // Sem template literals aninhados: o empacotador do Odoo comia o espaço depois da vírgula.
            const room = next.rooms ? ", " + next.rooms : "";
            text += ` A próxima: ${day}, às ${next.start}, ${next.subject}${room}.`;
        } else {
            text += " Já não há provas por fazer.";
        }
        return text;
    }

    async print() {
        const action = await this.orm.call("edu.student.portal", "exams_report", []);
        return this.action.doAction(action);
    }
}

const ABSENCE_RULES = {
    technical:
        "No ensino técnico, cada disciplina admite até ao triplo dos seus tempos semanais em faltas injustificadas, no ano inteiro. Quem passa o limite numa disciplina fica excluído de frequência (Despacho 60/08).",
    general:
        "No ensino geral, cada disciplina admite 3, 4 ou 5 faltas injustificadas por trimestre, conforme tem 1, 2 ou mais tempos por semana. Passar o limite leva à retenção (Decreto Executivo 424/25).",
};

export class StudentAbsences extends StudentPage {
    static template = "edu_portal.StudentAbsences";
    static page = "absences";

    get sentence() {
        const a = this.state.data.absences;
        let text = `Estiveste em ${a.present} das ${a.total} aulas com chamada (${a.rate}%). `;
        if (!a.absent && !a.excused) {
            text += "Não tens faltas.";
        } else if (!a.excused) {
            text += `Faltaste a ${count(a.absent, "uma aula", "aulas")}, sem justificação.`;
        } else if (!a.absent) {
            text += `Faltaste a ${count(a.excused, "uma aula", "aulas")}, com justificação.`;
        } else {
            text += `Faltaste a ${a.absent + a.excused}: ${count(a.absent, "uma injustificada", "injustificadas")} e ${count(a.excused, "uma justificada", "justificadas")}.`;
        }
        if (a.late) {
            const times = a.late === 1 ? "uma vez" : a.late + " vezes";
            text += ` Chegaste atrasado ${times}.`;
        }
        return text;
    }

    get rule() {
        return ABSENCE_RULES[this.state.data.absences.regime] || "";
    }

    statusClass(subject) {
        return { at_risk: "text-warning", failed: "text-danger" }[subject.status] || "text-muted";
    }
}

export class StudentFees extends StudentPage {
    static template = "edu_portal.StudentFees";
    static page = "fees";

    setup() {
        super.setup();
        this.state.tab = "due";
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    get rows() {
        return this.state.data.fees[this.state.tab];
    }

    /** O que está em atraso, a vermelho na frase de cima (como no secPed). */
    get overdueText() {
        const f = this.state.data.fees;
        const n = f.due.length;
        if (!f.overdue) {
            return "";
        }
        if (f.overdue === n) {
            return n === 1 ? "está em atraso" : "estão todas em atraso";
        }
        return f.overdue + " em atraso";
    }

    get dateHeader() {
        return { due: "Vence a", paid: "Paga a", other: "Vencia a" }[this.state.tab];
    }

    /** Telemóvel: «Vence a 10 de outubro de 2026, com 1 000 Kz de multa.» */
    whenText(row) {
        const tab = this.state.tab;
        const parts = [];
        if (tab === "paid" ? row.paid_date : row.due_date) {
            parts.push(tab === "paid" ? "Paga a " + row.paid_date : (tab === "other" ? "Vencia a " : "Vence a ") + row.due_date);
        }
        if (tab === "due" && row.fine) {
            parts.push("com " + row.fine + " de multa");
        }
        return parts.length ? parts.join(", ") + ". " : "";
    }

    statusClass(row) {
        return { bad: "text-danger", warn: "text-warning", good: "text-success", muted: "text-muted" }[row.css] || "";
    }
}

export class StudentProfile extends StudentPage {
    static template = "edu_portal.StudentProfile";
    static page = "profile";

    get sentence() {
        const d = this.state.data;
        const p = d.profile;
        if (!p.enrollment) {
            return `${d.first_name}, não tens matrícula activa neste ano lectivo. Se for engano, fala com a secretaria.`;
        }
        const course = p.enrollment.course ? ` (${p.enrollment.course})` : "";
        return `${d.first_name}, estás na turma ${p.enrollment.class}${course} no ano lectivo ${p.enrollment.year}, com ${count(p.enrollment.subjects.length, "uma disciplina", "disciplinas")}.`;
    }

    async changePassword() {
        const action = await this.orm.call("edu.student.portal", "change_password", []);
        return this.action.doAction(action);
    }
}

const actions = registry.category("actions");
actions.add("edu_portal.student_home", StudentHome);
actions.add("edu_portal.student_grades", StudentGrades);
actions.add("edu_portal.student_schedule", StudentSchedule);
actions.add("edu_portal.student_exams", StudentExams);
actions.add("edu_portal.student_absences", StudentAbsences);
actions.add("edu_portal.student_fees", StudentFees);
actions.add("edu_portal.student_profile", StudentProfile);
