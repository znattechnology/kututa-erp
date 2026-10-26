import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { FeeMonths, FeedFilters, feedGroups, feedWhen, HelpPage, StudentAbsences, StudentExams, StudentFees, StudentGrades } from "@edu_portal/student/student_pages";

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

export class GuardianHome extends GuardianPage(FeeMonths(GuardianBase)) {
    static template = "edu_portal.GuardianHome";
    static page = "home";

    get greeting() {
        const hour = new Date().getHours();
        const hello = hour < 12 ? "Bom dia" : hour < 19 ? "Boa tarde" : "Boa noite";
        return `${hello}, ${this.state.data.first_name}`;
    }

    /** «Os teus educandos: Ana e Bento.» (sem «encarregado de», que não diz se é encarregado ou encarregada). */
    get subtitle() {
        const children = this.state.data.children;
        if (!children.length) {
            return "Ainda sem educandos ligados à tua conta.";
        }
        return `${children.length === 1 ? "O teu educando" : "Os teus educandos"}: ${list(children.map((c) => c.first_name))}.`;
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

    /** A média de cada trimestre em colunas de 0 ao máximo da escala (só os trimestres com notas têm coluna). */
    trendCols(c) {
        return c.trend.map((t) => ({ ...t, height: t.value === null ? 0 : Math.max(2, (t.value / c.scale_max) * 100) }));
    }

    hasTrend(c) {
        return c.trend.some((t) => t.value !== null);
    }

    passBottom(c) {
        return (c.pass_grade / c.scale_max) * 100;
    }

    /** As aulas com chamada, em partes: presenças, faltas justificadas e injustificadas. */
    lessonParts(c) {
        const l = c.lessons;
        const total = l.present + l.excused + l.absent;
        const pct = (n) => (total ? (n / total) * 100 : 0);
        return [
            { key: "present", label: "Presenças", value: l.present, width: pct(l.present), css: "o_edu_stack_pos" },
            { key: "excused", label: "Justificadas", value: l.excused, width: pct(l.excused), css: "o_edu_stack_missing" },
            { key: "absent", label: "Injustificadas", value: l.absent, width: pct(l.absent), css: "o_edu_stack_neg" },
        ];
    }

    meterWidth(m) {
        return Math.min(100, (m.counted / m.limit) * 100);
    }

    meterClass(m) {
        return { at_risk: "o_edu_meter_warn", failed: "o_edu_meter_bad" }[m.status] || "";
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

    get feedGroups() {
        return feedGroups(this.state.data.feed);
    }

    openItem(item) {
        return this.openFor(FEED_ACTIONS[item.page], item.student_id);
    }
}

/** Meus educandos: a ficha do educando, os números do painel e quem o acompanha, a quem se escreve daqui. */
export class GuardianChildren extends GuardianPage(GuardianBase) {
    static template = "edu_portal.GuardianChildren";
    static page = "children";

    setup() {
        super.setup();
        this.store = useService("mail.store");
    }

    /** Os quatro números da ficha, cada um com o caminho para a sua página. */
    get tiles() {
        const d = this.state.data;
        const c = d.card.summary;
        const tiles = [];
        if (c.preschool) {
            const r = c.rdec;
            tiles.push({
                key: "rdec",
                label: "RDEC" + (r && r.trimester ? " do " + r.trimester : ""),
                value: r && r.applicable && !r.blocked ? `${r.done || 0} de ${r.total || 0}` : "—",
                detail: r && r.blocked ? "Bloqueado pelas propinas" : "áreas avaliadas",
                bad: r && r.blocked,
                action: "edu_portal.action_guardian_rdec",
            });
        } else {
            tiles.push({
                key: "grades",
                label: "Média do ano",
                value: c.blocked || !c.average ? "—" : c.average.text,
                detail: c.blocked ? "Bloqueada pelas propinas" : c.average ? (c.average.pos ? "Positiva, até agora" : "Abaixo de " + c.pass_text) : "Ainda sem notas",
                bad: c.blocked || (c.average && !c.average.pos),
                action: "edu_portal.action_guardian_grades",
            });
        }
        const a = c.attendance;
        tiles.push({
            key: "absences",
            label: "Assiduidade",
            value: a.total ? `${a.rate}%` : "—",
            detail: a.total ? `${a.present} de ${a.total} aulas com chamada` : "Ainda sem chamadas",
            bad: a.total && a.rate < 75,
            action: "edu_portal.action_guardian_absences",
        });
        const invoiced = c.months.some((m) => m.state !== "none");
        tiles.push({
            key: "fees",
            label: "Propinas",
            value: c.overdue ? c.overdue_total : invoiced ? "Em dia" : "Sem facturas",
            detail: c.overdue ? count(c.overdue, "uma factura em atraso", "facturas em atraso") : invoiced ? "Nada em atraso" : "Ainda sem propinas facturadas",
            bad: c.overdue > 0,
            small: true,
            action: "edu_portal.action_guardian_fees",
        });
        const e = d.card.next_exam;
        tiles.push({
            key: "exams",
            label: "Próxima prova",
            value: e ? (e.today ? "Hoje" : e.day.split(",")[1].trim()) : "—",
            detail: e ? `${e.subject}, às ${e.start}` : "Nenhuma marcada",
            small: Boolean(e),
            action: "edu_portal.action_guardian_exams",
        });
        return tiles;
    }

    /** Os professores da disciplina sem o director de turma (que já tem o seu cartão). */
    otherTeachers(subject) {
        const director = this.state.data.card.director;
        return subject.teachers.filter((p) => !director || p.name !== director.name);
    }

    /** No primário (e na iniciação) o director de turma dá tudo: em vez da grelha, uma frase com as disciplinas. */
    get directorTeachesAll() {
        const k = this.state.data.card;
        return Boolean(k.director && k.subjects.length && k.subjects.every((s) => s.teachers.length && !this.otherTeachers(s).length));
    }

    /** O curso só quando diz mais do que o nível («Ensino Primário» repetia o nível). */
    get course() {
        const k = this.state.data.card;
        return k.course && k.course.toLowerCase() !== (k.level || "").toLowerCase() ? k.course : "";
    }

    initials(name) {
        const parts = (name || "").split(" ").filter(Boolean);
        return (parts[0] ? parts[0][0] : "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
    }

    /** Abre a conversa com o professor nas Mensagens (a janela de conversa do Odoo). */
    writeTo(person) {
        return this.store.openChat({ partnerId: person.partner_id });
    }
}

export class GuardianGrades extends GuardianPage(StudentGrades) {
    static template = "edu_portal.GuardianGrades";
    static page = "grades";

    /** Outro educando no mesmo ano lectivo (se tiver matrícula nele; senão a página diz qual mostra). */
    selectChild(child) {
        const g = this.state.data.grades;
        return this.load({ student_id: child.id, academic_year_id: g ? g.academic_year_id : false });
    }
}

/** O RDEC do educando da Iniciação, só para ler, como no secPed; «Ver RDEC» abre o documento da escola. */
export class GuardianRdec extends GuardianPage(GuardianBase) {
    static template = "edu_portal.GuardianRdec";
    static page = "rdec";

    selectTrimester(ev) {
        return this.load({ trimester_id: parseInt(ev.target.value, 10) });
    }

    levelClass(level) {
        return "o_edu_lvl_" + (level || "none");
    }

    /** As áreas por nível, para a barra (só os níveis com áreas) e a legenda (por avaliar no fim). */
    get levelParts() {
        const r = this.state.data.rdec;
        const parts = r.levels.filter((l) => l.count).map((l) => ({ ...l, css: this.levelClass(l.key) }));
        const missing = (r.total || 0) - (r.done || 0);
        if (missing) {
            parts.push({ key: "none", label: "Por avaliar", count: missing, css: this.levelClass("") });
        }
        return parts;
    }

    /** «I: Bom, II: Muito bom» — os níveis da área nos trimestres anteriores. */
    historyText(area) {
        return area.history.map((h) => `${h.trimester.replace(" Trimestre", "")}: ${h.level_label}`).join(", ");
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
        this.state.paying = false;
        return super.selectChild(child);
    }

    submitPayment(values) {
        return this.orm.call("edu.guardian.portal", "submit_payment", [this.state.data.child_id, values]);
    }
}

export class GuardianNotifications extends FeedFilters(GuardianPage(GuardianBase)) {
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

    initials(name) {
        const parts = (name || "").split(" ").filter(Boolean);
        return (parts[0] ? parts[0][0] : "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
    }

    /** Os dados em grelha, com o ícone de cada um (os que faltam ficam «Por preencher»). */
    get fields() {
        const p = this.state.data.profile;
        return [
            { key: "phone", label: "Telefone", icon: "phone", value: p.phone },
            { key: "email", label: "Email", icon: "mail", value: p.email },
            { key: "address", label: "Morada", icon: "location_on", value: p.address },
            { key: "id_number", label: "BI ou passaporte", icon: "badge", value: p.id_number },
            { key: "vat", label: "NIF", icon: "receipt_long", value: p.vat },
            { key: "occupation", label: "Profissão", icon: "work", value: p.occupation },
        ];
    }

    openChild(child) {
        return this.openFor("edu_portal.action_guardian_children", child.id);
    }

    async changePassword() {
        const action = await this.orm.call("edu.student.portal", "change_password", []);
        return this.action.doAction(action);
    }
}

/** A ajuda do encarregado, como a do secPed: o que a área faz por ele. */
export class GuardianHelp extends HelpPage(GuardianBase) {
    static template = "edu_portal.GuardianHelp";

    get helpTopics() {
        return [
            {
                key: "children",
                label: "Os teus educandos",
                icon: "groups",
                questions: [
                    { q: "Tenho mais do que um educando. Como escolho de qual vejo?", a: "Nas notas, nas faltas, nas provas e nas propinas há separadores com o nome de cada educando por cima. O painel mostra todos ao mesmo tempo.", action: "edu_portal.action_guardian_home", actionLabel: "Abrir o painel" },
                    { q: "Falta um educando, ou aparece um que não é meu.", a: "Quem liga os educandos à tua conta é a secretaria da escola. Fala com ela para acrescentar ou retirar um educando, ou para te dar acesso ao portal dele." },
                    { q: "Quem são os professores e o director de turma?", a: "Em Meus educandos, cada ficha mostra a turma deste ano, o director de turma e o professor de cada disciplina, com o botão para lhes escrever.", action: "edu_portal.action_guardian_children", actionLabel: "Ver os educandos" },
                    { q: "Onde vejo as provas e os feriados?", a: "No Calendário estão as provas de cada educando, os feriados, as pausas e as reuniões da escola. Em Provas está o calendário de provas da turma.", action: "edu_portal.action_guardian_calendar", actionLabel: "Abrir o calendário" },
                ],
            },
            {
                key: "grades",
                label: "Notas e faltas",
                icon: "school",
                questions: [
                    { q: "Quando aparecem as notas?", a: "Assim que o professor as lança. Nas notificações aparece «Notas novas», com o nome do educando e a disciplina (sem a nota, que pode mudar até o trimestre fechar).", action: "edu_portal.action_guardian_grades", actionLabel: "Ver as notas" },
                    { q: "Porque é que as notas do meu educando estão bloqueadas?", a: "Algumas escolas escondem as notas enquanto houver propinas vencidas por pagar, depois dos dias de tolerância. Voltam a ver-se assim que as propinas em atraso forem pagas. Nas propinas vês exactamente o que está em atraso.", action: "edu_portal.action_guardian_fees", actionLabel: "Ver as propinas" },
                    { q: "O meu educando está na Iniciação. Onde vejo a avaliação?", a: "Na Iniciação não há notas: o educador escreve um relatório por trimestre (o RDEC), com o nível em cada área de desenvolvimento e uma apreciação global. Está em RDEC (Iniciação), que só aparece se um educando estiver na Iniciação." },
                    { q: "Como se contam as faltas?", a: "Só contam as aulas dadas em que o professor fez a chamada. Cada disciplina tem um limite de faltas injustificadas, que depende dos tempos semanais. No painel aparece um aviso quando o teu educando fica perto do limite ou o atinge.", action: "edu_portal.action_guardian_absences", actionLabel: "Ver as faltas" },
                    { q: "Como justifico uma falta?", a: "As faltas justificam-se junto do director de turma, com o documento que as justifica. Podes escrever-lhe nas mensagens.", action: "mail.action_discuss", actionLabel: "Abrir as mensagens" },
                ],
            },
            {
                key: "fees",
                label: "Propinas",
                icon: "payments",
                questions: [
                    { q: "Como pago as propinas?", a: "Na tesouraria da escola, ou por transferência ou depósito: nas propinas, carrega em «Pagar por transferência ou depósito», escolhe as facturas e envia o comprovativo. A tesouraria confere-o e, quando confirma, a factura passa para «Pagas». Se o comprovativo não for aceite, vês o motivo nos pagamentos enviados.", action: "edu_portal.action_guardian_fees", actionLabel: "Ver as propinas" },
                    { q: "Quando é que uma propina fica em atraso?", a: "No dia seguinte ao vencimento. A escola dá alguns dias de tolerância antes de aplicar restrições (o aviso e, em algumas escolas, o bloqueio das notas); a página das propinas diz quantos." },
                    { q: "Porque é que o valor de uma propina aumentou?", a: "Se a escola cobra multa por atraso, ela é somada à propina. Nas propinas a multa aparece à parte, factura a factura." },
                ],
            },
            {
                key: "account",
                label: "Mensagens e conta",
                icon: "forum",
                questions: [
                    { q: "A quem posso escrever?", a: "Aos professores e ao director de turma de cada educando, e à secretaria. Em Mensagens, começa uma conversa nova e escolhe a pessoa. Os professores que ainda não têm conta no sistema não recebem mensagens: para esses, escreve à secretaria.", action: "mail.action_discuss", actionLabel: "Abrir as mensagens" },
                    { q: "Esqueci-me da palavra-passe.", a: "Pede à secretaria uma palavra-passe nova. Depois de entrares, podes mudá-la em Meu perfil." },
                    { q: "Os meus dados estão errados.", a: "Vê-os em Meu perfil. Para os corrigir (o NIF, que vai nas facturas, o telefone, a morada), fala com a secretaria.", action: "edu_portal.action_guardian_profile", actionLabel: "Ver o perfil" },
                ],
            },
        ];
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
