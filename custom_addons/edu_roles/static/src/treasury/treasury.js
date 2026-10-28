import { Component, onMounted, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const PAGE = 50;
const plural = (n, one, many) => (n === 1 ? one : `${n.toLocaleString("pt-PT")} ${many}`);

// Como o servidor (2.500,00 Kz): o pt-PT do navegador não agrupa os milhares de quatro algarismos.
function formatMoney(amount, currency) {
    const [units, cents] = (Math.round(amount * 100) / 100).toFixed(2).split(".");
    return `${units.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${cents} ${currency}`;
}

// Uma linha como a factura a calcula: o preço sem IVA vezes a quantidade e o IVA arredondado por excesso (AGT).
function saleLine(item, quantity) {
    const net = Math.round(item.net * quantity * 100) / 100;
    const tax = Math.ceil(Math.round(net * item.rate * 1e4) / 1e4 - 1e-9) / 100;
    return { net, tax, gross: net + tax };
}

// Uma chave por visita e por escolha: repetir depois de um erro devolve a factura já emitida; mudar a escolha é outra
// venda.
function visitKey() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function saleKey(visit, signature) {
    let hash = 5381;
    for (let index = 0; index < signature.length; index++) {
        hash = ((hash << 5) + hash + signature.charCodeAt(index)) | 0;
    }
    return `${visit}-${(hash >>> 0).toString(36)}`;
}

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
        // Recarregada pelo endereço, a acção chega sem nome: o trilho mostra o nome do aluno.
        this.env.config.setDisplayName?.(this.state.data.student.name);
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
        return this.run("pay", ids);
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

/**
 * Cobrar, como o balcão do secPed: escolhem-se vários serviços e produtos do catálogo do aluno (batas, declarações,
 * certificados, uniformes…), com a quantidade de cada um, e sai uma só factura. O cartão de estudante cobra-se sozinho
 * (cada factura paga do cartão dá um cartão). Depois de emitida, a factura recebe-se logo ou fica por pagar na ficha.
 */
export class TreasuryCharge extends Component {
    static template = "edu_roles.TreasuryCharge";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const context = this.props.action.context || {};
        this.studentId = context.student_id || context.active_id;
        this.visit = visitKey();
        this.state = proxy({ data: null, qty: {}, dueDate: "", busy: false, done: null });
        onWillStart(() => this.load());
        onMounted(() => this.props.updateActionState?.({ active_id: this.studentId }));
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        this.state.data = await this.orm.call("edu.treasury", "catalog", [this.studentId]);
        this.env.config.setDisplayName?.(`Cobrar a ${this.state.data.student.name}`);
        this.state.dueDate = this.state.data.today;
    }

    get items() {
        return this.state.data.groups.flatMap((group) => group.items);
    }

    get selected() {
        return this.items.filter((item) => this.state.qty[item.id] > 0);
    }

    get hasCard() {
        return this.selected.some((item) => item.card);
    }

    get blocked() {
        // O cartão vai sozinho e numa unidade.
        return this.hasCard && (this.selected.length > 1 || this.selected.some((item) => this.state.qty[item.id] > 1));
    }

    line(item) {
        return saleLine(item, this.quantity(item));
    }

    get totals() {
        const totals = { gross: 0, net: 0, tax: 0 };
        for (const item of this.selected) {
            const line = this.line(item);
            totals.net += line.net;
            totals.tax += line.tax;
            totals.gross += line.gross;
        }
        return totals;
    }

    money(amount) {
        return formatMoney(amount, this.state.data.currency);
    }

    quantity(item) {
        return this.state.qty[item.id] || 0;
    }

    lineTotal(item) {
        return this.quantity(item) ? this.money(this.line(item).gross) : "—";
    }

    toggle(item) {
        const qty = { ...this.state.qty };
        if (qty[item.id]) {
            delete qty[item.id];
        } else {
            qty[item.id] = 1;
        }
        this.state.qty = qty;
    }

    bump(item, delta) {
        this.state.qty = { ...this.state.qty, [item.id]: Math.max(1, this.quantity(item) + delta) };
    }

    onDueDate(ev) {
        this.state.dueDate = ev.target.value;
    }

    key() {
        const signature = this.selected
            .map((item) => `${item.id}x${this.state.qty[item.id]}`)
            .sort()
            .join(",")
            .concat(this.state.dueDate || "");
        return saleKey(this.visit, signature);
    }

    async charge() {
        if (!this.selected.length || this.blocked || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const items = this.selected.map((item) => ({ id: item.id, quantity: this.state.qty[item.id] }));
            this.state.done = await this.orm.call("edu.treasury", "charge", [
                this.studentId,
                items,
                this.state.dueDate,
                this.key(),
            ]);
            this.notification.add(`Factura ${this.state.done.number} emitida.`, { type: "success" });
        } finally {
            this.state.busy = false;
        }
    }

    async receive() {
        const action = await this.orm.call("edu.treasury", "student_action", [
            this.studentId,
            "pay",
            [this.state.done.id],
            false,
        ]);
        // Toma o lugar do balcão no trilho: depois de registar, volta-se à ficha.
        return this.action.doAction(action, { stackPosition: "replaceCurrentAction" });
    }

    printInvoice() {
        return this.orm
            .call("edu.treasury", "student_action", [this.studentId, "print_move", null, this.state.done.id])
            .then((action) => this.action.doAction(action));
    }

    again() {
        this.visit = visitKey();
        this.state.qty = {};
        this.state.done = null;
    }

    back() {
        return this.action.restore();
    }
}

/**
 * Registar um pagamento, como no secPed: em cima as facturas por pagar (das mais antigas para as mais recentes; de cada
 * uma paga-se tudo ou parte), por baixo os serviços da escola (batas, cartão, declarações…), que se cobram e pagam no
 * mesmo acto, e no fim como foi pago. Sai um recibo com tudo. Em numerário acima do limite da escola, o pagamento fica à
 * espera de outra pessoa o aprovar. É tudo ou nada: se o pagamento falhar, a factura dos serviços também não fica.
 */
export class TreasuryPay extends Component {
    static template = "edu_roles.TreasuryPay";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const context = this.props.action.context || {};
        this.studentId = context.student_id || context.active_id;
        this.preselected = context.invoice_ids || [];
        this.visit = visitKey();
        this.state = proxy({
            data: null,
            alloc: {},
            services: {},
            method: "cash",
            reference: "",
            notes: "",
            busy: false,
        });
        onWillStart(() => this.load());
        onMounted(() => this.props.updateActionState?.({ active_id: this.studentId }));
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        const data = await this.orm.call("edu.treasury", "payment_data", [this.studentId]);
        this.env.config.setDisplayName?.(`Registar um pagamento de ${data.student.name}`);
        // Vindo do «Receber» de uma factura (ou das escolhidas na ficha), elas vêm já escolhidas, por inteiro.
        const alloc = {};
        for (const invoice of data.invoices) {
            if (this.preselected.includes(invoice.id)) {
                alloc[invoice.id] = invoice.residual.toFixed(2);
            }
        }
        const available = data.methods.find((method) => method.available);
        this.state.method = available ? available.key : "cash";
        this.state.alloc = alloc;
        this.state.data = data;
    }

    money(amount) {
        return formatMoney(amount, this.state.data.currency);
    }

    // As facturas

    isChosen(invoice) {
        return invoice.id in this.state.alloc;
    }

    toggleInvoice(invoice) {
        const alloc = { ...this.state.alloc };
        if (invoice.id in alloc) {
            delete alloc[invoice.id];
        } else {
            alloc[invoice.id] = invoice.residual.toFixed(2);
        }
        this.state.alloc = alloc;
    }

    onAmount(invoice, ev) {
        this.state.alloc = { ...this.state.alloc, [invoice.id]: ev.target.value };
    }

    amountOf(invoice) {
        return Number(this.state.alloc[invoice.id]) || 0;
    }

    exceeds(invoice) {
        return this.isChosen(invoice) && this.amountOf(invoice) > invoice.residual + 0.009;
    }

    get excessive() {
        return this.chosenInvoices.some((invoice) => this.exceeds(invoice));
    }

    get chosenInvoices() {
        return this.state.data.invoices.filter((invoice) => this.isChosen(invoice));
    }

    get invoicesTotal() {
        return this.chosenInvoices.reduce((total, invoice) => total + this.amountOf(invoice), 0);
    }

    get olderLeft() {
        // Aviso (não impede): saldam-se meses recentes e ficam por pagar outros mais antigos.
        const paid = this.chosenInvoices.filter((invoice) => this.amountOf(invoice) > 0);
        if (!paid.length) {
            return 0;
        }
        const oldest = paid.map((invoice) => invoice.due_key).sort()[0];
        return this.state.data.invoices.filter(
            (invoice) => invoice.due_key < oldest && !(this.amountOf(invoice) > 0)
        ).length;
    }

    get invoicesHint() {
        const count = this.chosenInvoices.length;
        if (!count) {
            return "Escolha as facturas a saldar. Pode pagar só parte de uma.";
        }
        return `${plural(count, "Uma factura escolhida", "facturas escolhidas")}, ${this.money(this.invoicesTotal)}.`;
    }

    get olderHint() {
        const count = this.olderLeft;
        return `Está a saldar meses mais recentes e a deixar ${plural(
            count,
            "uma factura mais antiga",
            "facturas mais antigas"
        )} por pagar. O habitual é pagar primeiro a dívida mais antiga.`;
    }

    // Os serviços

    isService(item) {
        return Boolean(this.state.services[item.id]);
    }

    toggleService(item) {
        this.state.services = { ...this.state.services, [item.id]: !this.state.services[item.id] };
    }

    get chosenServices() {
        return this.state.data.services.filter((item) => this.isService(item));
    }

    get servicesTotal() {
        return this.chosenServices.reduce((total, item) => total + saleLine(item, 1).gross, 0);
    }

    get cardBlocked() {
        // O cartão cobra-se sozinho: cada factura paga do cartão dá um cartão.
        return this.chosenServices.length > 1 && this.chosenServices.some((item) => item.card);
    }

    // Como foi pago

    onMethod(ev) {
        this.state.method = ev.target.value;
    }

    onReference(ev) {
        this.state.reference = ev.target.value;
    }

    onNotes(ev) {
        this.state.notes = ev.target.value;
    }

    get total() {
        return Math.round((this.invoicesTotal + this.servicesTotal) * 100) / 100;
    }

    get needsApproval() {
        const data = this.state.data;
        return this.state.method === "cash" && data.cash_approval && this.total > data.cash_threshold;
    }

    get submitLabel() {
        return this.total > 0 ? `Registar ${this.money(this.total)}` : "Registar o pagamento";
    }

    get canSubmit() {
        const method = this.state.data.methods.find((m) => m.key === this.state.method);
        return (
            this.total > 0 &&
            method?.available &&
            // No TPA e no depósito, a referência do talão confere o pagamento na conciliação bancária.
            (this.state.method === "cash" || this.state.reference.trim()) &&
            !this.cardBlocked &&
            !this.excessive &&
            !this.state.busy
        );
    }

    async submit() {
        if (!this.canSubmit) {
            return;
        }
        this.state.busy = true;
        try {
            const services = this.chosenServices.map((item) => item.id).sort();
            const result = await this.orm.call("edu.treasury", "register_payment", [
                this.studentId,
                {
                    allocations: this.chosenInvoices.map((invoice) => ({
                        id: invoice.id,
                        amount: this.amountOf(invoice),
                    })),
                    service_ids: services,
                    method: this.state.method,
                    reference: this.state.reference,
                    notes: this.state.notes,
                    key: saleKey(this.visit, services.join(",")),
                },
            ]);
            if (result.status === "pending") {
                this.notification.add(
                    `O pagamento de ${result.total} ficou registado, mas em numerário acima do limite da escola fica à ` +
                        "espera de outra pessoa o aprovar, em Aprovações e caixa. Até lá as facturas continuam por " +
                        "pagar: não o registe outra vez.",
                    { type: "warning", sticky: true, title: "À espera de aprovação" }
                );
            } else {
                this.notification.add(
                    `Pagamento de ${result.total} registado. O recibo está na ficha do aluno.`,
                    { type: "success" }
                );
            }
            return this.back();
        } finally {
            this.state.busy = false;
        }
    }

    back() {
        return this.action.restore();
    }
}

registry.category("actions").add("edu_roles.treasury_home", TreasuryHome);
registry.category("actions").add("edu_roles.treasury_pay", TreasuryPay);
registry.category("actions").add("edu_roles.treasury_charge", TreasuryCharge);
registry.category("actions").add("edu_roles.treasury_controls", TreasuryControls);
registry.category("actions").add("edu_roles.treasury_differences", TreasuryDifferences);
registry.category("actions").add("edu_roles.treasury_rules", TreasuryRules);
registry.category("actions").add("edu_roles.treasury_students", TreasuryStudents);
registry.category("actions").add("edu_roles.treasury_student", TreasuryStudent);
