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
        this.state = proxy({ data: null });
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

    /** Uma nota com a cor primária se é positiva e a vermelho se é negativa, como na grelha do professor. */
    gradeClass(grade, strong = false) {
        if (!grade) {
            return "text-muted";
        }
        return `${grade.pos ? "text-primary" : "text-danger"}${strong ? " fw-semibold" : ""}`;
    }

    gradeText(grade) {
        return grade ? grade.text : "—";
    }
    /** As notas do trimestre por disciplina, em barras de 0 ao máximo da escala (as sem nota ficam sem barra). */
    get gradeBars() {
        const g = this.state.data.grades;
        if (!g.active || !g.subjects) {
            return [];
        }
        const max = g.scale_max || 20;
        return g.subjects.map((s) => {
            const ct = s.by_trimester[g.active.id].ct;
            return {
                id: s.id,
                name: s.name,
                grade: ct,
                width: ct ? Math.max(2, Math.min(100, (ct.value / max) * 100)) : 0,
            };
        });
    }

    get passLeft() {
        const g = this.state.data.grades;
        return ((g.pass_grade || 10) / (g.scale_max || 20)) * 100;
    }

    /** A média de cada trimestre, em colunas (só os trimestres com notas têm coluna). */
    get trend() {
        const g = this.state.data.grades;
        const max = g.scale_max || 20;
        return (g.trend || []).map((t) => ({ ...t, height: t.value === null ? 0 : Math.max(2, (t.value / max) * 100) }));
    }

    get hasTrend() {
        return this.trend.some((t) => t.value !== null);
    }

    /** As faltas injustificadas face ao limite de cada disciplina (só as que têm limite no plano). */
    get absenceMeters() {
        const a = this.state.data.absences;
        return (a.subjects || [])
            .filter((s) => s.limit)
            .map((s) => ({ ...s, width: Math.min(100, (s.counted / s.limit) * 100) }))
            .sort((x, y) => y.width - x.width || x.name.localeCompare(y.name));
    }

    statusClass(subject) {
        return { at_risk: "text-warning", failed: "text-danger" }[subject.status] || "text-muted";
    }

    meterClass(subject) {
        return { at_risk: "o_edu_meter_warn", failed: "o_edu_meter_bad" }[subject.status] || "";
    }

    /** Os números das faltas, por cima da tabela (o aluno e o encarregado). */
    get absenceTiles() {
        const a = this.state.data.absences;
        const technical = a.regime === "technical";
        return [
            {
                key: "rate",
                label: "Assiduidade",
                value: `${a.rate}%`,
                detail: `${a.present} de ${a.total} aulas com chamada`,
                bad: a.rate < 75,
            },
            {
                key: "absent",
                label: "Faltas injustificadas",
                value: String(a.absent),
                detail: a.failed.length
                    ? `${technical ? "Limite ultrapassado" : "Limite atingido"} a ${count(a.failed.length, "uma disciplina", "disciplinas")}`
                    : a.at_risk.length
                      ? `${technical ? "No limite" : "A uma falta do limite"} a ${count(a.at_risk.length, "uma disciplina", "disciplinas")}`
                      : a.regime === "primary" ? "Sem limite por disciplina" : "Dentro do limite",
                bad: a.failed.length > 0,
                warn: !a.failed.length && a.at_risk.length > 0,
            },
            { key: "excused", label: "Faltas justificadas", value: String(a.excused), detail: "Não contam para o limite" },
            { key: "late", label: "Atrasos", value: String(a.late), detail: "Contam como presença" },
        ];
    }

    /** As aulas com chamada em partes: presenças, justificadas e injustificadas. */
    get absenceParts() {
        const a = this.state.data.absences;
        return [
            { key: "present", label: "Presenças", value: a.present, css: "o_edu_stack_pos" },
            { key: "excused", label: "Justificadas", value: a.excused, css: "o_edu_stack_missing" },
            { key: "absent", label: "Injustificadas", value: a.absent, css: "o_edu_stack_neg" },
        ];
    }

    /** As faltas de cada mês em colunas empilhadas, na escala do mês com mais. */
    get absenceMonths() {
        const months = this.state.data.absence_months || [];
        const max = Math.max(1, ...months.map((m) => m.absent + m.excused + m.late));
        return months.map((m) => ({
            ...m,
            total: m.absent + m.excused + m.late,
            parts: [
                { key: "absent", label: "Injustificadas", value: m.absent, css: "o_edu_stack_neg" },
                { key: "excused", label: "Justificadas", value: m.excused, css: "o_edu_stack_missing" },
                { key: "late", label: "Atrasos", value: m.late, css: "o_edu_stack_partial" },
            ].filter((p) => p.value),
            height: ((m.absent + m.excused + m.late) / max) * 100,
        }));
    }

    /** «Pagas 2 de 3, uma em atraso.» — o que a fila dos meses mostra, em palavras. */
    monthsText(c) {
        const issued = c.months.filter((m) => m.state !== "none");
        if (!issued.length) {
            return "Ainda sem propinas facturadas neste ano lectivo.";
        }
        const n = (state) => c.months.filter((m) => m.state === state).length;
        const paid = n("paid");
        const parts = [`${paid === 1 ? "Paga" : "Pagas"} ${paid} de ${issued.length}`];
        if (n("overdue")) {
            parts.push(count(n("overdue"), "uma em atraso", "em atraso"));
        }
        if (n("due")) {
            parts.push(count(n("due"), "uma por pagar", "por pagar"));
        }
        return `${parts.join(", ")}.`;
    }

    /** Há propinas facturadas neste ano (sem nenhuma, «Em dia» e uma fila vazia não diziam nada). */
    hasInvoices(c) {
        return c.months.some((m) => m.state !== "none");
    }

    monthTitle(m) {
        const state = { paid: "paga", due: "por pagar", overdue: "em atraso", exempt: "isenta", none: "ainda sem factura" }[m.state];
        return `Propina de ${m.name}: ${state}${m.due ? ", faltam " + m.due : ""}`;
    }

    /** Os números das propinas, por cima das facturas (o aluno e o encarregado). */
    get feeTiles() {
        const f = this.state.data.fees;
        return [
            {
                key: "due",
                label: "Por pagar",
                value: f.due.length ? f.total_due : "Nada",
                detail: f.due.length ? count(f.due.length, "uma factura", "facturas") : "Está tudo pago",
            },
            {
                key: "overdue",
                label: "Em atraso",
                value: f.overdue ? f.overdue_total : "Nada",
                detail: !f.overdue
                    ? "Nenhuma factura em atraso"
                    : count(f.overdue, "uma factura", "facturas") +
                      (!f.restricted && f.grace_days ? `, dentro da tolerância de ${f.grace_days} dias (sem restrições)` : f.has_fines ? ", com multas" : ""),
                bad: f.overdue > 0,
            },
            { key: "paid", label: "Já pago", value: f.total_paid, detail: "Em todas as facturas pagas" },
            {
                key: "next",
                label: "Próximo vencimento",
                value: f.next_due ? f.next_due.date.split(" de ").slice(0, 2).join(" de ") : "—",
                detail: f.next_due ? `${f.next_due.name}, ${f.next_due.amount}` : "Nada a vencer",
            },
        ];
    }

    /** «Subiu de 14,5 no 1.º trimestre» (a comparação com o trimestre anterior, quando é possível). */
    trendText(previous) {
        if (!previous) {
            return "";
        }
        const verb = previous.trend.startsWith("subiu") ? "Subiu de" : previous.trend.startsWith("desceu") ? "Desceu de" : "Igual ao";
        return `${verb} ${previous.average} no ${previous.name}`;
    }

    /** O resumo do trimestre escolhido, por cima da pauta: a média (e se subiu ou desceu), as positivas, as negativas
     * e a média do ano. */
    get gradeTiles() {
        const g = this.state.data.grades;
        const sp = g.summary_parts || {};
        const cells = g.subjects.map((s) => s.by_trimester[g.active.id].ct);
        const graded = cells.filter(Boolean);
        const negatives = graded.filter((ct) => !ct.pos).length;
        const trimester = g.active.name.replace("Trimestre", "trimestre");
        return [
            {
                key: "average",
                label: "Média do " + trimester,
                value: sp.empty ? "—" : sp.average,
                detail: sp.empty ? "Ainda sem notas" : this.trendText(sp.previous) || `Positiva a partir de ${g.pass_text}`,
                bad: !sp.empty && !sp.average_pos,
            },
            {
                key: "positives",
                label: "Positivas",
                value: graded.length ? String(graded.length - negatives) : "—",
                detail: graded.length ? `de ${count(graded.length, "uma disciplina com nota", "disciplinas com nota")}` : "Ainda sem notas",
            },
            {
                key: "negatives",
                label: "Negativas",
                value: graded.length ? String(negatives) : "—",
                detail: negatives ? list(g.subjects.filter((s) => s.by_trimester[g.active.id].ct && !s.by_trimester[g.active.id].ct.pos).map((s) => s.name)) : graded.length ? "Nenhuma" : "Ainda sem notas",
                bad: negatives > 0,
            },
            {
                key: "year",
                label: "Média do ano",
                value: g.year_average ? g.year_average.text : "—",
                detail: g.year_average ? (g.past ? "Ano lectivo fechado" : "Até agora") : "Ainda sem notas",
                bad: g.year_average && !g.year_average.pos,
            },
        ];
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

    get absenceTile() {
        const a = this.state.data.absences;
        if (!a.total) {
            return { value: "—", detail: "Ainda sem chamadas este ano" };
        }
        if (a.regime === "primary") {
            return { value: String(a.absent), detail: a.preschool ? "Sem limite na Iniciação" : "Sem limite por disciplina no primário" };
        }
        // No técnico reprova-se ao passar o limite; no geral, ao atingi-lo (os nomes da página das faltas).
        const technical = a.regime === "technical";
        const subjects = (n) => count(n, "uma disciplina", "disciplinas");
        const detail = a.failed.length
            ? `${technical ? "Limite ultrapassado" : "Limite atingido"} a ${subjects(a.failed.length)}`
            : a.at_risk.length
              ? `${technical ? "No limite" : "A uma falta do limite"} a ${subjects(a.at_risk.length)}`
              : "Dentro do limite em todas as disciplinas";
        return { value: String(a.absent), detail, bad: a.failed.length > 0, warn: !a.failed.length && a.at_risk.length > 0 };
    }

    get feesTile() {
        const f = this.state.data.fees_summary;
        if (!f || !f.count) {
            return { value: "Em dia", detail: "Não tens nada por pagar" };
        }
        const detail = f.overdue ? `${count(f.overdue, "uma factura", "facturas")} em atraso` : `${count(f.count, "uma factura", "facturas")} por pagar`;
        return { value: f.total, detail, bad: f.overdue > 0 };
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

    /** Quantos dias faltam para uma prova: «Hoje», «Amanhã», «Daqui a 3 dias». */
    countdown(row) {
        const [y, m, d] = row.date.split("-").map((part) => parseInt(part, 10));
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const days = Math.round((new Date(y, m - 1, d) - today) / 86400000);
        return days <= 0 ? "Hoje" : days === 1 ? "Amanhã" : `Daqui a ${days} dias`;
    }

    /** Os números das provas: marcadas, feitas, por fazer e em quantos dias. */
    get examTiles() {
        const e = this.state.data.exams;
        const done = e.rows.filter((r) => r.done).length;
        return [
            { key: "count", label: "Provas marcadas", value: String(e.count), detail: count(e.days, "num só dia", "dias de provas").replace(/^(\d+)/, "em $1") },
            { key: "done", label: "Já feitas", value: String(done), detail: done ? "Os resultados ficam nas notas" : "Ainda nenhuma" },
            { key: "left", label: "Por fazer", value: String(e.count - done), detail: e.next ? "A próxima: " + this.countdown(e.next).toLowerCase() : "Não há mais provas" },
        ];
    }

    /** Os dias de provas numa fila: o dia, o mês, quantas provas e se já passou. */
    get examDays() {
        const days = [];
        for (const row of this.state.data.exams.rows) {
            let day = days.find((d) => d.date === row.date);
            if (!day) {
                const [, month] = row.day.split(" de ");
                day = { date: row.date, num: row.date.slice(8, 10), month: (month || "").slice(0, 3), weekday: row.day.split(",")[0].slice(0, 3), count: 0, done: true, today: row.today, subjects: [] };
                days.push(day);
            }
            day.count++;
            day.done = day.done && row.done;
            day.subjects.push(row.subject);
        }
        return days;
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
            text += `Faltaste a ${a.absent + a.excused} aulas: ${count(a.absent, "uma injustificada", "injustificadas")} e ${count(a.excused, "uma justificada", "justificadas")}.`;
        }
        if (a.late) {
            text += ` Chegaste tarde ${a.late === 1 ? "uma vez" : a.late + " vezes"}.`;
        }
        return text;
    }

    get rule() {
        return ABSENCE_RULES[this.state.data.absences.regime] || "";
    }

}

export class StudentFees extends StudentPage {
    static template = "edu_portal.StudentFees";
    static page = "fees";

    setup() {
        super.setup();
        this.state.tab = null;
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    /** O separador escolhido; por omissão o das facturas por pagar, ou o das pagas quando não há nada por pagar. */
    get tab() {
        const f = this.state.data.fees;
        return this.state.tab || (f.due.length || !f.rows.length ? "due" : f.paid.length ? "paid" : "other");
    }

    get rows() {
        return this.state.data.fees[this.tab];
    }

    get dateHeader() {
        return { due: "Vence a", paid: "Paga a", other: "Vencia a" }[this.tab];
    }

    /** Telemóvel: «Vence a 10 de outubro de 2026 (há 3 dias), com 1 000 Kz de multa.» */
    whenText(row) {
        const tab = this.tab;
        const parts = [];
        if (tab === "paid" ? row.paid_date : row.due_date) {
            parts.push(tab === "paid" ? "Paga a " + row.paid_date : (tab === "other" ? "Vencia a " : "Vence a ") + row.due_date);
        }
        if (tab === "due" && row.late_days) {
            const late = row.late_days === 1 ? "há 1 dia" : "há " + row.late_days + " dias";
            if (parts.length) {
                parts[0] += " (" + late + ")";
            } else {
                parts.push("Em atraso " + late);
            }
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
        const n = p.enrollment.subjects.length;
        const subjects = n ? `, com ${count(n, "uma disciplina", "disciplinas")}` : "";
        return `${d.first_name}, estás na turma ${p.enrollment.class}${course} no ano lectivo ${p.enrollment.year}${subjects}.`;
    }

    async changePassword() {
        const action = await this.orm.call("edu.student.portal", "change_password", []);
        return this.action.doAction(action);
    }
}

const TRAINING_STATE_CLASS = {
    planned: "text-bg-light",
    proposed: "text-bg-light",
    ongoing: "text-bg-info",
    submitted: "text-bg-info",
    defended: "text-bg-info",
    passed: "text-bg-success",
    failed: "text-bg-danger",
};

/** «O Meu Estágio», como no secPed: o estágio curricular do aluno do técnico, só para ler. */
export class StudentInternship extends StudentPage {
    static template = "edu_portal.StudentInternship";
    static page = "internship";

    stateClass(record) {
        return TRAINING_STATE_CLASS[record.state] || "text-bg-light";
    }
}

/** «A Minha PAP», como no secPed: a Prova de Aptidão Profissional do aluno do técnico, só para ler. */
export class StudentProject extends StudentPage {
    static template = "edu_portal.StudentProject";
    static page = "project";

    stateClass(record) {
        return TRAINING_STATE_CLASS[record.state] || "text-bg-light";
    }
}

const HISTORY_STATUS_CLASS = { promoted: "text-primary", graduated: "text-primary", retained: "text-danger" };
const HISTORY_VERBS = {
    promoted: "transitaste",
    graduated: "concluíste o curso",
    conditional: "transitaste com disciplinas em atraso",
    exam: "foste admitido a exame de recurso",
    retained: "ficaste retido",
};

/** O Histórico, como no secPed: o percurso ano a ano, com a média final, a assiduidade e a decisão do ano. */
export class StudentHistory extends StudentPage {
    static template = "edu_portal.StudentHistory";
    static page = "history";

    /** «Tens 3 anos lectivos no histórico: transitaste em 2 anos e ficaste retido em um.» */
    get sentence() {
        const rows = this.state.data.history.rows;
        const counts = Object.keys(HISTORY_VERBS)
            .map((status) => [status, rows.filter((r) => r.status === status).length])
            .filter(([, n]) => n);
        // Com uma só decisão em todos os anos, não é preciso contar.
        const parts = counts.map(([status, n]) =>
            counts.length === 1 || status === "graduated" ? HISTORY_VERBS[status] : `${HISTORY_VERBS[status]} em ${count(n, "um", "anos")}`
        );
        return `Tens ${count(rows.length, "um ano lectivo", "anos lectivos")} no histórico: ${list(parts)}.`;
    }

    statusClass(row) {
        return HISTORY_STATUS_CLASS[row.status] || "text-warning";
    }
}

/** «hoje», «ontem», «há 3 dias», como nas notificações do secPed. */
export function feedWhen(isoDate) {
    const [y, m, d] = isoDate.split("-").map((part) => parseInt(part, 10));
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Math.round((today - new Date(y, m - 1, d)) / 86400000);
    return days <= 0 ? "Hoje" : days === 1 ? "Ontem" : `Há ${days} dias`;
}

// O ícone de cada tipo de novidade (a cor fica para o estado: as novidades são todas neutras).
const FEED_ICONS = { grades: "school", absences: "person_off", exams: "edit_note", fees: "payments", rdec: "child_care" };

/** As novidades agrupadas por dia: hoje, ontem, nos últimos 7 dias e as mais antigas. */
export function feedGroups(items) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const groups = [
        { key: "today", label: "Hoje", items: [] },
        { key: "yesterday", label: "Ontem", items: [] },
        { key: "week", label: "Esta semana", items: [] },
        { key: "older", label: "Mais antigas", items: [] },
    ];
    for (const item of items) {
        const [y, m, d] = item.date.split("-").map((part) => parseInt(part, 10));
        const days = Math.round((today - new Date(y, m - 1, d)) / 86400000);
        const group = days <= 0 ? groups[0] : days === 1 ? groups[1] : days < 7 ? groups[2] : groups[3];
        group.items.push({ ...item, icon: FEED_ICONS[item.page] || "info", days });
    }
    return groups.filter((g) => g.items.length);
}

// Os tipos de novidade, pela ordem dos filtros, com o nome no plural e na frase de resumo.
const FEED_TYPES = [
    { key: "grades", label: "Notas", phrase: "de notas" },
    { key: "absences", label: "Faltas", phrase: "de faltas" },
    { key: "exams", label: "Provas", phrase: "de provas" },
    { key: "fees", label: "Propinas", phrase: "de propinas" },
    { key: "rdec", label: "RDEC", phrase: "do RDEC" },
];

/**
 * Os filtros das notificações (o aluno e o encarregado): por tipo, com quantas há de cada (só os tipos com
 * novidades), e por educando (no encarregado, com mais de um). Mistura-se numa página que tenha ``state.data.feed``.
 */
export const FeedFilters = (Base) =>
    class extends Base {
        setup() {
            super.setup();
            this.state.feedType = "all";
            this.state.feedChild = "all";
        }

        get feedTypeFilters() {
            const feed = this.feedForChild;
            const types = FEED_TYPES.map((t) => ({ ...t, count: feed.filter((i) => i.page === t.key).length })).filter((t) => t.count);
            return types.length > 1 ? [{ key: "all", label: "Todas", count: feed.length }, ...types] : [];
        }

        get feedChildFilters() {
            const children = this.state.data.children || [];
            return children.length > 1 ? [{ id: "all", first_name: "Todos" }, ...children] : [];
        }

        get feedForChild() {
            const child = this.state.feedChild;
            return (this.state.data.feed || []).filter((i) => child === "all" || i.student_id === child);
        }

        get filteredFeed() {
            const type = this.state.feedType;
            return this.feedForChild.filter((i) => type === "all" || i.page === type);
        }

        get feedGroups() {
            return feedGroups(this.filteredFeed);
        }

        /** «11 novidades: 2 de notas, 3 de provas e 6 de propinas.» (os 30 dias estão no subtítulo) */
        get feedSummary() {
            const feed = this.feedForChild;
            const parts = FEED_TYPES.map((t) => [t, feed.filter((i) => i.page === t.key).length])
                .filter(([, n]) => n)
                .map(([t, n]) => `${n} ${t.phrase}`);
            return `${count(feed.length, "Uma novidade", "novidades")}${parts.length ? ": " + list(parts) : ""}.`;
        }

        setFeedType(key) {
            this.state.feedType = key;
        }

        setFeedChild(key) {
            this.state.feedChild = key;
            this.state.feedType = "all";
        }
    };

const STUDENT_FEED_ACTIONS = {
    grades: "edu_portal.action_student_grades",
    rdec: "edu_portal.action_student_grades",
    absences: "edu_portal.action_student_absences",
    exams: "edu_portal.action_student_exams",
    fees: "edu_portal.action_student_fees",
};

/** As notificações: as notas novas, as faltas, as provas marcadas, as facturas e os pagamentos dos últimos 30 dias. */
export class StudentNotifications extends FeedFilters(StudentPage) {
    static template = "edu_portal.StudentNotifications";
    static page = "notifications";

    when(item) {
        return feedWhen(item.date);
    }

    openItem(item) {
        return this.open(STUDENT_FEED_ACTIONS[item.page]);
    }
}

/** Sem acentos e em minúsculas, para a procura da ajuda («palavra-passe» encontra «Palavra-passe»). */
const plain = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

/**
 * A ajuda, como a do secPed (o aluno e o encarregado): os temas no topo, a procura nas perguntas e nas respostas, as
 * perguntas a abrir uma a uma, cada uma com o caminho para a página que responde, e no fim a secretaria nas
 * Mensagens. A página dá ``helpTopics``: [{key, label, icon, questions: [{q, a, action?, actionLabel?}]}].
 */
export const HelpPage = (Base) =>
    class extends Base {
        setup() {
            super.setup();
            this.state.search = "";
        }

        async load() {
            this.state.data = {};
        }

        onSearch(ev) {
            this.state.search = ev.target.value;
        }

        get filteredTopics() {
            // A raiz de cada palavra (sem as duas últimas letras, nas de 5 ou mais): «pagar» encontra «pago» e «pagamento».
            const words = plain(this.state.search)
                .split(/\s+/)
                .filter(Boolean)
                .map((w) => (w.length >= 5 ? w.slice(0, -2) : w));
            return this.helpTopics
                .map((topic) => ({
                    ...topic,
                    questions: topic.questions.filter((item) => {
                        const text = plain(`${item.q} ${item.a}`);
                        return words.every((w) => text.includes(w));
                    }),
                }))
                .filter((topic) => topic.questions.length);
        }

        scrollTo(key) {
            document.getElementById(`o_edu_help_${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    };

/** A ajuda do aluno. */
export class StudentHelp extends HelpPage(StudentPage) {
    static template = "edu_portal.StudentHelp";

    get helpTopics() {
        return [
            {
                key: "grades",
                label: "Notas e faltas",
                icon: "school",
                questions: [
                    { q: "Quando aparecem as notas?", a: "Assim que o professor as lança. Nas notificações aparece «Notas novas» da disciplina (sem a nota, que pode mudar até o trimestre fechar). O mínimo para a positiva está escrito por baixo da pauta.", action: "edu_portal.action_student_grades", actionLabel: "Ver as notas" },
                    { q: "O que querem dizer NPP, NPT, CT, MAC e MT?", a: "No ensino técnico, NPP é a nota do professor e NPT a da prova do trimestre; a classificação do trimestre (CT) junta as duas. No ensino geral, MAC é a média das avaliações contínuas e MT a média do trimestre. A legenda completa está por baixo da pauta.", action: "edu_portal.action_student_grades", actionLabel: "Ver as notas" },
                    { q: "Como se conta a minha assiduidade?", a: "Só contam as aulas dadas em que o professor fez a chamada. Chegar atrasado conta como presença e como atraso. Cada disciplina tem um limite de faltas injustificadas, que depende dos tempos semanais; no painel e nas faltas vês quando estás perto dele.", action: "edu_portal.action_student_absences", actionLabel: "Ver as faltas" },
                    { q: "Onde vejo o horário, as provas e os anos anteriores?", a: "O horário da turma está em Horário, as provas marcadas em Provas e o resultado de cada ano em Histórico. Se a escola ainda não publicou o horário, a página diz isso.", action: "edu_portal.action_student_history", actionLabel: "Ver o histórico" },
                ],
            },
            {
                key: "fees",
                label: "Propinas",
                icon: "payments",
                questions: [
                    { q: "Quem paga as propinas?", a: "O teu encarregado de educação, na tesouraria da escola. Aqui vês as facturas e o que está por pagar; quando um pagamento é confirmado, a factura passa para «Pagas».", action: "edu_portal.action_student_fees", actionLabel: "Ver as propinas" },
                    { q: "Porque é que o valor de uma propina aumentou?", a: "Se a escola cobra multa por atraso, ela é somada à propina depois do vencimento. Na página das propinas a multa aparece numa coluna própria, factura a factura." },
                    { q: "O que acontece se houver propinas em atraso?", a: "Depende da escola: durante os dias de tolerância vês só um aviso; depois, algumas páginas, como as notas e o histórico, podem ficar fechadas até as propinas vencidas serem pagas. A tua matrícula continua activa e continuas a ter aulas." },
                ],
            },
            {
                key: "account",
                label: "Mensagens e conta",
                icon: "forum",
                questions: [
                    { q: "A quem posso escrever?", a: "Aos professores da tua turma, ao director de turma e à secretaria. Em Mensagens, começa uma conversa nova e escolhe a pessoa.", action: "mail.action_discuss", actionLabel: "Abrir as mensagens" },
                    { q: "Como peço uma declaração ou um certificado?", a: "Na secretaria da escola. Antes, vê em Meu perfil se os teus dados estão completos: são os que vão nos documentos.", action: "edu_portal.action_student_profile", actionLabel: "Ver o perfil" },
                    { q: "Os meus dados estão errados ou em falta. O que faço?", a: "Vê-os em Meu perfil. Para os corrigir ou completar, fala com a secretaria.", action: "edu_portal.action_student_profile", actionLabel: "Ver o perfil" },
                    { q: "Esqueci-me da palavra-passe.", a: "Pede à secretaria uma palavra-passe nova. Depois de entrares, podes mudá-la em Meu perfil, em Segurança." },
                ],
            },
        ];
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
actions.add("edu_portal.student_internship", StudentInternship);
actions.add("edu_portal.student_project", StudentProject);
actions.add("edu_portal.student_history", StudentHistory);
actions.add("edu_portal.student_notifications", StudentNotifications);
actions.add("edu_portal.student_help", StudentHelp);
