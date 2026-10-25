import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { feedWhen, StudentAbsences, StudentExams, StudentFees, StudentGrades } from "@edu_portal/student/student_pages";

const list = (items) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} e ${items[items.length - 1]}` : items[0] || "");
const count = (n, one, many) => (n === 1 ? one : `${n} ${many}`);

// O educando escolhido fica escolhido ao mudar de página, como o «?educando=» do secPed.
let currentChild = null;

/**
 * A Área do Encarregado, como a do secPed-Express: cada página pede os seus dados a ``edu.guardian.portal.page_data``
 * e, nas que falam de um educando, mostra os separadores com os educandos (com um só não há o que escolher). As notas,
 * as faltas, as provas e as propinas usam as tabelas da área do estudante.
 */
const GuardianPage = (Base) =>
    class extends Base {
        async load(options = {}) {
            const context = this.props.action?.context || {};
            const studentId = this.state.data ? this.state.data.child_id : context.student_id || currentChild;
            const data = await this.orm.call("edu.guardian.portal", "page_data", [
                this.constructor.page,
                { student_id: studentId, ...options },
            ]);
            if (data.child_id) {
                currentChild = data.child_id;
            }
            this.state.data = data;
        }

        selectChild(child) {
            return this.load({ student_id: child.id });
        }

        /** Outra página da área, já com o educando de que se fala. */
        openFor(xmlid, studentId) {
            return this.action.doAction(xmlid, { additionalContext: { student_id: studentId || this.state.data.child_id } });
        }
    };

class GuardianBase extends Component {
    static components = { Layout };
    static page = "";

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null });
        this.list = list;
        this.count = count;
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    open(xmlid) {
        return this.action.doAction(xmlid);
    }
}

const FEED_ACTIONS = {
    grades: "edu_portal.action_guardian_grades",
    absences: "edu_portal.action_guardian_absences",
    exams: "edu_portal.action_guardian_exams",
    fees: "edu_portal.action_guardian_fees",
    rdec: "edu_portal.action_guardian_rdec",
};

export class GuardianHome extends GuardianPage(GuardianBase) {
    static template = "edu_portal.GuardianHome";
    static page = "home";

    get greeting() {
        const hour = new Date().getHours();
        const hello = hour < 12 ? "Bom dia" : hour < 19 ? "Boa tarde" : "Boa noite";
        return `${hello}, ${this.state.data.first_name}`;
    }

    /** «Encarregado de Ana e Bento.» */
    get subtitle() {
        const children = this.state.data.children;
        if (!children.length) {
            return "Ainda sem educandos ligados à tua conta.";
        }
        return `Encarregado de ${list(children.map((c) => c.first_name))}.`;
    }

    /** A frase de cima: quantos, e se há propinas em atraso. */
    get summary() {
        const rows = this.state.data.summaries;
        const debtors = rows.filter((c) => c.overdue > 0);
        const who = rows.length === 1 ? `Acompanhas ${rows[0].name}.` : `Acompanhas ${rows.length} educandos.`;
        if (!debtors.length) {
            return { text: `${who} As propinas estão em dia.`, debt: "" };
        }
        const debt =
            rows.length === 1
                ? `Tem ${rows[0].overdue_total} de propinas em atraso.`
                : `${list(debtors.map((c) => c.first_name))} ${debtors.length === 1 ? "tem" : "têm"} propinas em atraso.`;
        return { text: who, debt };
    }

    attendanceText(c) {
        const a = c.attendance;
        const missed = a.total - a.present;
        if (!missed) {
            return a.total === 1 ? "esteve na única aula com chamada" : `esteve nas ${a.total} aulas com chamada`;
        }
        return `faltou a ${missed} de ${a.total} ${a.total === 1 ? "aula" : "aulas"} com chamada`;
    }

    /** O que pede atenção, como no secPed: propinas em atraso, faltas no limite e médias negativas. */
    get warnings() {
        const out = [];
        for (const c of this.state.data.summaries) {
            if (c.overdue > 0) {
                out.push({
                    key: `${c.id}-fees`,
                    child: c,
                    text: `${c.overdue_total} de propinas em atraso (${count(c.overdue, "uma factura", "facturas")}).`,
                    action: "edu_portal.action_guardian_fees",
                });
            }
            // No técnico reprova-se ao passar o limite; no geral, ao atingi-lo (os nomes da página das faltas).
            const technical = c.regime === "technical";
            if (c.failed.length) {
                out.push({
                    key: `${c.id}-failed`,
                    child: c,
                    text: `${technical ? "Passou" : "Atingiu"} o limite de faltas a ${list(c.failed)}.`,
                    action: "edu_portal.action_guardian_absences",
                });
            }
            if (c.at_risk.length) {
                out.push({
                    key: `${c.id}-risk`,
                    child: c,
                    text: `${technical ? "Está no limite de faltas" : "Está a uma falta do limite"} a ${list(c.at_risk)}.`,
                    action: "edu_portal.action_guardian_absences",
                });
            }
            if (c.average && !c.average.pos && !c.blocked) {
                out.push({
                    key: `${c.id}-average`,
                    child: c,
                    text: `A média do ano está negativa (${c.average.text}).`,
                    action: "edu_portal.action_guardian_grades",
                });
            }
        }
        return out;
    }

    when(item) {
        return feedWhen(item.date);
    }

    openItem(item) {
        return this.openFor(FEED_ACTIONS[item.page], item.student_id);
    }
}

export class GuardianChildren extends GuardianPage(GuardianBase) {
    static template = "edu_portal.GuardianChildren";
    static page = "children";
}

export class GuardianGrades extends GuardianPage(StudentGrades) {
    static template = "edu_portal.GuardianGrades";
    static page = "grades";
}

const RDEC_LEVEL_CLASS = {
    not_satisfactory: "text-bg-danger",
    satisfactory: "text-bg-warning",
    good: "text-bg-info",
    very_good: "text-bg-success",
};

/** O RDEC do educando da Iniciação, só para ler, como no secPed; «Ver RDEC» abre o documento da escola. */
export class GuardianRdec extends GuardianPage(GuardianBase) {
    static template = "edu_portal.GuardianRdec";
    static page = "rdec";

    selectTrimester(ev) {
        return this.load({ trimester_id: parseInt(ev.target.value, 10) });
    }

    levelClass(area) {
        return RDEC_LEVEL_CLASS[area.level] || "text-bg-light";
    }

    async openReport() {
        const r = this.state.data.rdec;
        const action = await this.orm.call("edu.guardian.portal", "rdec_report", [this.state.data.child_id, r.trimester_id]);
        return this.action.doAction(action);
    }
}

export class GuardianAbsences extends GuardianPage(StudentAbsences) {
    static template = "edu_portal.GuardianAbsences";
    static page = "absences";

    get sentence() {
        const d = this.state.data;
        const a = d.absences;
        const name = d.child.first_name;
        let text = `${name} esteve em ${a.present} das ${a.total} aulas com chamada (${a.rate}%). `;
        if (!a.absent && !a.excused) {
            text += "Não tem faltas.";
        } else if (!a.excused) {
            text += `Faltou a ${count(a.absent, "uma aula", "aulas")}, sem justificação.`;
        } else if (!a.absent) {
            text += `Faltou a ${count(a.excused, "uma aula", "aulas")}, com justificação.`;
        } else {
            text += `Faltou a ${a.absent + a.excused} aulas: ${count(a.absent, "uma injustificada", "injustificadas")} e ${count(a.excused, "uma justificada", "justificadas")}.`;
        }
        if (a.late) {
            text += ` Chegou tarde ${a.late === 1 ? "uma vez" : a.late + " vezes"}.`;
        }
        return text;
    }
}

export class GuardianExams extends GuardianPage(StudentExams) {
    static template = "edu_portal.GuardianExams";
    static page = "exams";
}

export class GuardianFees extends GuardianPage(StudentFees) {
    static template = "edu_portal.GuardianFees";
    static page = "fees";

    selectChild(child) {
        this.state.tab = null;
        return super.selectChild(child);
    }
}

export class GuardianNotifications extends GuardianPage(GuardianBase) {
    static template = "edu_portal.GuardianNotifications";
    static page = "notifications";

    when(item) {
        return feedWhen(item.date);
    }

    openItem(item) {
        return this.openFor(FEED_ACTIONS[item.page], item.student_id);
    }
}

export class GuardianProfile extends GuardianPage(GuardianBase) {
    static template = "edu_portal.GuardianProfile";
    static page = "profile";

    async changePassword() {
        const action = await this.orm.call("edu.student.portal", "change_password", []);
        return this.action.doAction(action);
    }
}

/** A ajuda, como no secPed: perguntas por tema, com o caminho para a página que responde. */
export class GuardianHelp extends GuardianBase {
    static template = "edu_portal.GuardianHelp";

    async load() {
        this.state.data = {};
    }
}

const actions = registry.category("actions");
actions.add("edu_portal.guardian_home", GuardianHome);
actions.add("edu_portal.guardian_children", GuardianChildren);
actions.add("edu_portal.guardian_grades", GuardianGrades);
actions.add("edu_portal.guardian_rdec", GuardianRdec);
actions.add("edu_portal.guardian_absences", GuardianAbsences);
actions.add("edu_portal.guardian_exams", GuardianExams);
actions.add("edu_portal.guardian_fees", GuardianFees);
actions.add("edu_portal.guardian_notifications", GuardianNotifications);
actions.add("edu_portal.guardian_profile", GuardianProfile);
actions.add("edu_portal.guardian_help", GuardianHelp);
