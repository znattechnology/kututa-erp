import { Component, onMounted, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const PAGE = 50;
const plural = (n, one, many) => (n === 1 ? one : `${n.toLocaleString("pt-PT")} ${many}`);

/**
 * O painel da tesouraria, como o das Finanças do secPed: em frases, o que já venceu e quanto se cobrou e o que está em
 * atraso (vencido há mais do que a tolerância da escola) e de quantos alunos; o que pede atenção (comprovativos por
 * validar e a facturação certificada); o facturado e o cobrado dos últimos seis meses; os maiores atrasos e os
 * últimos pagamentos. «Actualizar o vencimento» faz já o que a tarefa diária faz de noite (as multas e a situação).
 */
export class TreasuryHome extends Component {
    static template = "edu_roles.TreasuryHome";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.plural = plural;
        this.state = proxy({ data: null, running: false });
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        this.state.data = await this.orm.call("edu.treasury", "home_data", []);
    }

    async open(key, resId = false) {
        const action = await this.orm.call("edu.treasury", "open", [key, resId]);
        return this.action.doAction(action, { onClose: () => this.load() });
    }

    async runOverdue() {
        this.state.running = true;
        try {
            await this.orm.call("edu.treasury", "run_overdue", []);
            this.notification.add("Facturas vencidas e multas actualizadas.", { type: "success" });
            await this.load();
        } finally {
            this.state.running = false;
        }
    }

    /** Facturado e cobrado por mês: duas colunas por mês, à escala do maior valor dos seis meses. */
    get months() {
        const rows = this.state.data.monthly;
        const max = Math.max(1, ...rows.map((m) => Math.max(m.invoiced, m.collected)));
        return rows.map((m) => ({
            ...m,
            invoicedHeight: (100 * m.invoiced) / max,
            collectedHeight: (100 * m.collected) / max,
        }));
    }

    get hasMonthly() {
        return this.state.data.monthly.some((m) => m.invoiced || m.collected);
    }

    get currentMonth() {
        const rows = this.state.data.monthly;
        return rows[rows.length - 1];
    }

    rateText(value) {
        return value === null || value === undefined ? "—" : `${String(value).replace(".", ",")}%`;
    }
}

/**
 * Facturar e receber, como no secPed: à esquerda as turmas do ano (por curso, com quantos estão em atraso); à direita
 * os alunos da turma pelo número com a conta-corrente (em atraso, por pagar, já pago). «Só em atraso» funciona também
 * sem turma: os em atraso da escola inteira, do maior atraso para o menor. Abrir um aluno leva à ficha financeira.
 */
export class TreasuryStudents extends Component {
    static template = "edu_roles.TreasuryStudents";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const context = this.props.action.context || {};
        this.state = proxy({
            year: "",
            classes: [],
            classFilter: "",
            classId: false,
            debtOnly: Boolean(context.debt_only),
            query: "",
            rows: [],
            totals: null,
            page: 0,
            loading: false,
        });
        this.searchTimer = null;
        onWillStart(async () => {
            const data = await this.orm.call("edu.treasury", "classes", []);
            Object.assign(this.state, { year: data.year, classes: data.classes });
            await this.loadRows();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async loadRows() {
        // Uma resposta antiga (outra turma, outra pesquisa) não se sobrepõe à mais recente.
        const request = (this.request = (this.request || 0) + 1);
        this.state.loading = true;
        try {
            const data = await this.orm.call("edu.treasury", "students", [
                this.state.classId,
                this.state.debtOnly,
                this.state.query,
            ]);
            if (request === this.request) {
                Object.assign(this.state, { rows: data.rows, totals: data.totals, page: 0 });
            }
        } finally {
            if (request === this.request) {
                this.state.loading = false;
            }
        }
    }

    get classGroups() {
        const filter = this.state.classFilter.trim().toLowerCase();
        const groups = [];
        for (const c of this.state.classes) {
            if (filter && !`${c.name} ${c.course}`.toLowerCase().includes(filter)) {
                continue;
            }
            let group = groups.find((g) => g.course === (c.course || "Sem curso"));
            if (!group) {
                group = { course: c.course || "Sem curso", classes: [] };
                groups.push(group);
            }
            group.classes.push(c);
        }
        return groups;
    }

    get selectedClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    onClassFilter(ev) {
        this.state.classFilter = ev.target.value;
    }

    selectClass(classId) {
        this.state.classId = this.state.classId === classId ? false : classId;
        this.loadRows();
    }

    toggleDebt() {
        this.state.debtOnly = !this.state.debtOnly;
        this.loadRows();
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.loadRows(), 300);
    }

    get pageRows() {
        return this.state.rows.slice(this.state.page * PAGE, (this.state.page + 1) * PAGE);
    }

    get pages() {
        return Math.max(1, Math.ceil(this.state.rows.length / PAGE));
    }

    setPage(delta) {
        this.state.page = Math.min(this.pages - 1, Math.max(0, this.state.page + delta));
    }

    get pagerText() {
        const total = this.state.rows.length;
        const first = this.state.page * PAGE + 1;
        return `${first}–${Math.min(total, first + PAGE - 1)} de ${total}`;
    }

    get heading() {
        if (this.selectedClass) {
            return `Turma ${this.selectedClass.name}`;
        }
        if (this.state.query.trim()) {
            return "Resultados da pesquisa";
        }
        return this.state.debtOnly ? "Alunos em atraso, de toda a escola" : "";
    }

    openStudent(row) {
        return this.action.doAction({
            type: "ir.actions.client",
            tag: "edu_roles.treasury_student",
            name: row.name,
            context: { student_id: row.student_id },
        });
    }
}

/**
 * A ficha financeira de um aluno: o que deve e desde quando (em frases), se está bloqueado pelas propinas, as facturas
 * por pagar (escolhem-se e recebem-se; cada uma imprime-se), os documentos fiscais (facturas, notas de crédito e
 * recibos) e quem compra nas facturas (o aluno ou o encarregado, com o NIF e a morada).
 */
export class TreasuryStudent extends Component {
    static template = "edu_roles.TreasuryStudent";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const context = this.props.action.context || {};
        // O aluno fica no endereço (active_id): recarregar a página volta à mesma ficha.
        this.studentId = context.student_id || context.active_id;
        this.notification = useService("notification");
        this.state = proxy({ data: null, selected: [], voiding: null });
        onWillStart(() => this.load());
        onMounted(() => this.props.updateActionState?.({ active_id: this.studentId }));
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        this.state.data = await this.orm.call("edu.treasury", "student_data", [this.studentId]);
        this.state.selected = this.state.selected.filter((id) => this.state.data.open.some((m) => m.id === id));
    }

    isSelected(row) {
        return this.state.selected.includes(row.id);
    }

    toggle(row) {
        this.state.selected = this.isSelected(row)
            ? this.state.selected.filter((id) => id !== row.id)
            : [...this.state.selected, row.id];
    }

    async run(key, invoiceIds = null, resId = false) {
        const action = await this.orm.call("edu.treasury", "student_action", [this.studentId, key, invoiceIds, resId]);
        return this.action.doAction(action, { onClose: () => this.load() });
    }

    receive(ids) {
        return this.run("receive", ids);
    }

    // Anular uma factura: com a justificação; fica pedida a outro utilizador quando a escola o exige.

    startVoid(row) {
        this.state.voiding = { id: row.id, label: `${row.number}, ${row.label}`, reason: "" };
    }

    cancelVoid() {
        this.state.voiding = null;
    }

    onVoidReason(ev) {
        this.state.voiding.reason = ev.target.value;
    }

    async confirmVoid() {
        const voiding = this.state.voiding;
        if (!voiding || !voiding.reason.trim()) {
            return;
        }
        const result = await this.orm.call("edu.treasury", "request_void", [voiding.id, voiding.reason]);
        this.state.voiding = null;
        this.notification.add(
            result === "requested"
                ? "Anulação pedida: fica à espera de outro utilizador em Aprovações e caixa."
                : "Factura anulada: foi emitida a nota de crédito.",
            { type: result === "requested" ? "info" : "success" }
        );
        await this.load();
    }

    print(doc) {
        return this.run(doc.model === "account.payment" ? "print_payment" : "print_move", null, doc.id);
    }
}

/**
 * Aprovações e caixa, como no secPed: a caixa de quem recebe numerário (abre-se no início do turno; no fim conta-se o
 * dinheiro e declara-se sem ver o esperado, e a diferença aparece logo) e as operações que pedem um segundo par de
 * olhos: anular uma factura, conceder uma bolsa e o numerário acima do limite. Quem pediu não decide o seu pedido.
 */
export class TreasuryControls extends Component {
    static template = "edu_roles.TreasuryControls";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ data: null, closing: null, closed: null, deciding: null, busy: false });
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        this.state.data = await this.orm.call("edu.treasury", "controls_data", []);
    }

    async openCash() {
        await this.orm.call("edu.treasury", "open_cash", []);
        this.state.closed = null;
        this.notification.add("Caixa aberta.", { type: "success" });
        await this.load();
    }

    startClose() {
        this.state.closing = { declared: "", notes: "" };
    }

    cancelClose() {
        this.state.closing = null;
    }

    onClosing(key, ev) {
        this.state.closing[key] = ev.target.value;
    }

    async confirmClose() {
        const closing = this.state.closing;
        if (closing.declared === "" || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.closed = await this.orm.call("edu.treasury", "close_cash", [parseFloat(closing.declared), closing.notes]);
            this.state.closing = null;
            await this.load();
        } finally {
            this.state.busy = false;
        }
    }

    startDecide(item, approve) {
        this.state.deciding = { kind: item.kind, id: item.id, approve, title: item.title, what: item.what, notes: "" };
    }

    cancelDecide() {
        this.state.deciding = null;
    }

    onDecideNotes(ev) {
        this.state.deciding.notes = ev.target.value;
    }

    get canDecide() {
        const d = this.state.deciding;
        return Boolean(d && (d.approve || d.notes.trim()) && !this.state.busy);
    }

    async confirmDecide() {
        const d = this.state.deciding;
        if (!this.canDecide) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("edu.treasury", "decide", [d.kind, d.id, d.approve, d.notes]);
            this.notification.add(d.approve ? "Pedido aprovado." : "Pedido recusado.", { type: "success" });
            this.state.deciding = null;
            await this.load();
        } finally {
            this.state.busy = false;
        }
    }

    openDifferences() {
        return this.action.doAction("edu_roles.action_treasury_differences");
    }
}

/** Diferenças de caixa: os fechos dos últimos 30 dias em que o contado não bateu com o registado. */
export class TreasuryDifferences extends Component {
    static template = "edu_roles.TreasuryDifferences";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ data: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("edu.treasury", "differences", [30]);
        });
    }

    get display() {
        return { controlPanel: {} };
    }
}

/**
 * Controlos internos: as regras de segunda aprovação. Toda a tesouraria as lê (quem opera a caixa tem de saber o que
 * fica à espera de outra pessoa); só a direcção as altera.
 */
export class TreasuryRules extends Component {
    static template = "edu_roles.TreasuryRules";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ data: null, edit: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("edu.treasury", "rules", []);
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    startEdit() {
        const d = this.state.data;
        this.state.edit = {
            threshold: String(d.threshold),
            cash_approval: d.cash_approval,
            void_approval: d.void_approval,
            scholarship_approval: d.scholarship_approval,
        };
    }

    cancelEdit() {
        this.state.edit = null;
    }

    onEdit(key, ev) {
        this.state.edit[key] = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
    }

    async save() {
        this.state.data = await this.orm.call("edu.treasury", "save_rules", [this.state.edit]);
        this.state.edit = null;
        this.notification.add("Controlos internos guardados.", { type: "success" });
    }
}

registry.category("actions").add("edu_roles.treasury_home", TreasuryHome);
registry.category("actions").add("edu_roles.treasury_controls", TreasuryControls);
registry.category("actions").add("edu_roles.treasury_differences", TreasuryDifferences);
registry.category("actions").add("edu_roles.treasury_rules", TreasuryRules);
registry.category("actions").add("edu_roles.treasury_students", TreasuryStudents);
registry.category("actions").add("edu_roles.treasury_student", TreasuryStudent);
