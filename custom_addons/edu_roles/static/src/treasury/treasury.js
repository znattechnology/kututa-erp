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
        this.state = proxy({ data: null, selected: [] });
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

    print(doc) {
        return this.run(doc.model === "account.payment" ? "print_payment" : "print_move", null, doc.id);
    }
}

registry.category("actions").add("edu_roles.treasury_home", TreasuryHome);
registry.category("actions").add("edu_roles.treasury_students", TreasuryStudents);
registry.category("actions").add("edu_roles.treasury_student", TreasuryStudent);
