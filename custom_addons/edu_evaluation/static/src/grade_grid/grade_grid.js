import { Component, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const LAST_CLASS_KEY = "edu_evaluation.grade_grid.class";
const COLLAPSED_KEY = "edu_evaluation.grade_grid.collapsed";

function remember(key, value) {
    try {
        window.localStorage.setItem(key, String(value));
    } catch {
        // Sem armazenamento: fica só nesta visita.
    }
}

function remembered(key) {
    try {
        return window.localStorage.getItem(key);
    } catch {
        return null;
    }
}

/** Arredondamento às unidades, metade para cima (9,5 → 10), como o servidor. */
function roundUnits(value) {
    return Math.floor(value + 0.5 + 1e-9);
}

function mean(values) {
    const present = values.filter((v) => v !== null && v !== undefined);
    return present.length ? present.reduce((a, b) => a + b, 0) / present.length : null;
}

function fmtDecimal(value) {
    return value === null || value === undefined ? "" : (Math.round(value * 10) / 10).toFixed(1).replace(".", ",");
}

function fmtInt(value) {
    return value === null || value === undefined ? "" : String(roundUnits(value));
}

/**
 * «Notas da turma», como a pauta por disciplina do secPed-Express: a turma, as disciplinas à esquerda e a grelha à
 * direita — os alunos nas linhas e, por trimestre, MAC/NPP, NPT, MT/CT e as faltas, seguidos da classificação do ano.
 * «Editar notas» abre no lugar as colunas que se lançam (NPT; no técnico também a NPP; PG e exame nacional no fim do
 * ano) nos trimestres em que o utilizador pode lançar. Enter e as setas mudam de aluno, «F» marca falta, Esc desfaz a
 * célula. A média do trimestre vê-se enquanto se escreve; o servidor grava tudo ou nada, com as regras de sempre.
 */
export class GradeGrid extends Component {
    static template = "edu_evaluation.GradeGrid";
    static components = { Layout };

    props = useProps(standardActionServiceProps);
    table = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            year: false,
            yearId: false,
            years: [],
            collapsed: remembered(COLLAPSED_KEY) === "1",
            classes: [],
            classId: false,
            subjects: [],
            subjectId: false,
            data: null,
            editing: false,
            edits: {},
            errors: {},
            busy: false,
            version: 0,
            printTrimesterId: false,
        });
        onWillStart(async () => {
            const context = this.props.action.context || {};
            await this.loadYear(context.default_academic_year_id || false, context.default_class_id, context.default_subject_id);
        });
    }

    // Ano lectivo

    async loadYear(yearId, classId = false, subjectId = false) {
        const options = await this.orm.call("edu.grade.grid", "grid_classes", [yearId]);
        this.state.year = options.year;
        this.state.yearId = options.year_id;
        this.state.years = options.years;
        this.state.classes = options.classes;
        this.state.classId = false;
        this.state.subjects = [];
        this.state.subjectId = false;
        this.state.data = null;
        const wanted = classId || parseInt(remembered(LAST_CLASS_KEY), 10);
        const pick = this.state.classes.find((c) => c.id === wanted) || this.state.classes[0];
        if (pick) {
            await this.openClass(pick.id, subjectId);
        }
    }

    async onYearChange(ev) {
        const yearId = parseInt(ev.target.value, 10) || false;
        if (yearId && this.confirmDiscard()) {
            this.state.editing = false;
            this.resetEdits();
            await this.loadYear(yearId);
        }
    }

    get pastYear() {
        const year = this.state.years.find((y) => y.id === this.state.yearId);
        return Boolean(year && !year.is_current);
    }

    /** O que se abre a partir da turma escolhida (mini-pauta, conselho, faltas do director, RDEC), como no secPed. */
    get classLinks() {
        const current = this.state.classes.find((c) => c.id === this.state.classId);
        return (current && current.links) || [];
    }

    async openClassLink(key) {
        const action = await this.orm.call("edu.grade.grid", "class_link_action", [this.state.classId, key]);
        return this.action.doAction(action);
    }

    toggleSubjects() {
        this.state.collapsed = !this.state.collapsed;
        remember(COLLAPSED_KEY, this.state.collapsed ? "1" : "0");
    }

    get display() {
        return { controlPanel: {} };
    }

    // Turma e disciplina

    get selectedClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    async openClass(classId, subjectId = false) {
        if (!this.confirmDiscard()) {
            return;
        }
        this.state.classId = classId;
        remember(LAST_CLASS_KEY, classId);
        this.state.subjects = await this.orm.call("edu.grade.grid", "grid_subjects", [classId]);
        const pick =
            this.state.subjects.find((s) => s.id === subjectId) ||
            this.state.subjects.find((s) => s.editable) ||
            this.state.subjects[0];
        this.state.data = null;
        if (pick) {
            await this.openSubject(pick.id);
        }
    }

    async onClassChange(ev) {
        const classId = parseInt(ev.target.value, 10) || false;
        if (classId) {
            await this.openClass(classId);
        }
    }

    async openSubject(subjectId) {
        if (subjectId !== this.state.subjectId && !this.confirmDiscard()) {
            return;
        }
        this.state.subjectId = subjectId;
        this.state.editing = false;
        this.resetEdits();
        this.state.data = await this.orm.call("edu.grade.grid", "grid_data", [this.state.classId, subjectId]);
        const trimesters = this.state.data.trimesters;
        if (!trimesters.some((t) => t.id === this.state.printTrimesterId)) {
            const current = trimesters.find((t) => t.is_current) || trimesters[trimesters.length - 1];
            this.state.printTrimesterId = current ? current.id : false;
        }
    }

    // Pauta da turma (secretaria): visualizar na aplicação ou imprimir em PDF, até ao trimestre escolhido.

    onPrintTrimesterChange(ev) {
        this.state.printTrimesterId = parseInt(ev.target.value, 10) || false;
    }

    async printPauta(preview) {
        const action = await this.orm.call("edu.grade.grid", "grid_print", [
            this.state.classId,
            this.state.printTrimesterId,
            preview,
        ]);
        await this.action.doAction(action);
    }

    confirmDiscard() {
        return !this.dirtyCount || window.confirm("Há notas por guardar. Sair sem guardar?");
    }

    // Edição

    resetEdits() {
        this.state.edits = {};
        this.state.errors = {};
    }

    get dirtyCount() {
        return Object.keys(this.state.edits).length;
    }

    get errorCount() {
        return Object.keys(this.state.errors).length;
    }

    toggleEditing() {
        if (this.state.editing && this.dirtyCount && !this.confirmDiscard()) {
            return;
        }
        this.state.editing = !this.state.editing;
        this.resetEdits();
        this.state.version++;
    }

    term(student, trimester) {
        return student.terms[String(trimester.id)];
    }

    key(student, trimesterId, column) {
        return `${student.enrollment_id}|${trimesterId || 0}|${column}`;
    }

    /** As colunas que se lançam neste trimestre (NPP no técnico, NPT onde há prova). */
    canEdit(student, trimester, column) {
        const data = this.state.data;
        if (!this.state.editing || student.exit) {
            return false;
        }
        if (column === "pg") {
            return data.subject.pg_editable;
        }
        if (column === "en") {
            return data.subject.en_editable;
        }
        if (!trimester.editable) {
            return false;
        }
        if (column === "npp") {
            return data.technical && trimester.npp_editable;
        }
        return column === "npt" && trimester.has_npt;
    }

    original(student, trimesterId, column) {
        if (column === "pg" || column === "en") {
            return { value: student[column], absent: student[`${column}_absent`] };
        }
        const term = student.terms[String(trimesterId)];
        return { value: term[`${column}_grade`], absent: term[`${column}_absent`] };
    }

    inputValue(student, trimesterId, column) {
        const edit = this.state.edits[this.key(student, trimesterId, column)];
        if (edit) {
            return edit.text;
        }
        const original = this.original(student, trimesterId, column);
        return original.absent ? "F" : fmtDecimal(original.value);
    }

    /**
     * O campo identifica-se pela sua chave (data-key): as variáveis do modelo (a coluna, o trimestre) só se lêem no
     * desenho — no momento do evento já têm o último valor do ciclo, e a NPP gravava-se como NPT.
     */
    cellFromKey(key) {
        const [enrollment, trimester, column] = key.split("|");
        const student = this.state.data.students.find((s) => s.enrollment_id === parseInt(enrollment, 10));
        return { student, trimesterId: parseInt(trimester, 10) || 0, column };
    }

    onCellInput(ev) {
        const { student, trimesterId, column } = this.cellFromKey(ev.target.dataset.key);
        return this.onInput(student, trimesterId, column, ev);
    }

    onInput(student, trimesterId, column, ev) {
        const key = this.key(student, trimesterId, column);
        const text = ev.target.value.trim();
        const original = this.original(student, trimesterId, column);
        const originalText = original.absent ? "F" : fmtDecimal(original.value);
        if (text === originalText) {
            delete this.state.edits[key];
            delete this.state.errors[key];
            return;
        }
        const max = this.state.data.policy.scale_max;
        const edit = { text, enrollment_id: student.enrollment_id, trimester_id: trimesterId || false, column };
        if (text.toUpperCase() === "F") {
            edit.absent = true;
            edit.value = null;
        } else if (text === "") {
            edit.value = null;
        } else {
            const value = Number(text.replace(",", "."));
            if (Number.isNaN(value) || value < 0 || value > max) {
                this.state.errors[key] = `Vai de 0 a ${max}; «F» marca a falta.`;
            } else {
                delete this.state.errors[key];
            }
            edit.value = value;
        }
        if (edit.absent || edit.value === null) {
            delete this.state.errors[key];
        }
        this.state.edits[key] = edit;
    }

    onKeydown(ev) {
        const input = ev.target;
        const row = parseInt(input.dataset.row, 10);
        const col = input.dataset.col;
        if (ev.key === "Escape") {
            const { student, trimesterId, column } = this.cellFromKey(input.dataset.key);
            delete this.state.edits[input.dataset.key];
            delete this.state.errors[input.dataset.key];
            input.value = this.inputValue(student, trimesterId, column);
            ev.preventDefault();
            return;
        }
        const down = ev.key === "Enter" || ev.key === "ArrowDown";
        if (!down && ev.key !== "ArrowUp") {
            return;
        }
        ev.preventDefault();
        // O aluno seguinte (ou anterior) com campo nesta coluna: quem saiu da turma não tem campo.
        const inputs = [...(this.table()?.querySelectorAll(`input[data-col="${col}"]`) || [])];
        const ordered = inputs
            .map((el) => ({ el, row: parseInt(el.dataset.row, 10) }))
            .filter((item) => (down ? item.row > row : item.row < row))
            .sort((a, b) => (down ? a.row - b.row : b.row - a.row));
        if (ordered.length) {
            ordered[0].el.focus();
            ordered[0].el.select();
        }
    }

    /** O valor que conta para a pré-visualização (o escrito, ou o que está gravado). */
    current(student, trimester, column, fallback) {
        const edit = this.state.edits[this.key(student, trimester.id, column)];
        if (edit && !this.state.errors[this.key(student, trimester.id, column)]) {
            return edit.absent ? 0 : edit.value;
        }
        return fallback;
    }

    /** A MT/CT do trimestre: a do servidor, ou o cálculo com as notas escritas (o mesmo do servidor). */
    termAverage(student, trimester) {
        const term = student.terms[String(trimester.id)];
        const data = this.state.data;
        const touched =
            this.state.edits[this.key(student, trimester.id, "npt")] ||
            this.state.edits[this.key(student, trimester.id, "npp")];
        if (!touched) {
            return { value: term.mt, preview: false };
        }
        const npt = this.current(student, trimester, "npt", term.npt);
        if (data.technical) {
            const npp = this.current(student, trimester, "npp", term.mac);
            const value = mean([npp, npt]);
            return { value: value === null ? null : roundUnits(value), preview: true };
        }
        if (term.mac === null || npt === null) {
            return { value: null, preview: true };
        }
        const w = data.policy.mac_weight;
        return { value: roundUnits(term.mac * w + npt * (1 - w)), preview: true };
    }

    /**
     * A classificação do trimestre na grelha. No técnico é o CT do Despacho 60/08 (art. 17.º, n.º 5, e o resumo do
     * regime): CT1 = (NPP + NPT)/2, CT2 = (CT1 + média do 2.º)/2, CT3 = (CT2 + média do 3.º)/2 — cada trimestre
     * engloba os anteriores, como a CF. No geral, a MT do trimestre.
     */
    termClassification(student, trimester) {
        const own = this.termAverage(student, trimester);
        if (!this.state.data.technical || own.value === null || own.value === undefined) {
            return own;
        }
        let running = null;
        let preview = false;
        for (const t of this.state.data.trimesters) {
            const avg = t.id === trimester.id ? own : this.termAverage(student, t);
            preview = preview || avg.preview;
            if (avg.value !== null && avg.value !== undefined) {
                running = running === null ? roundUnits(avg.value) : roundUnits((running + avg.value) / 2);
            }
            if (t.id === trimester.id) {
                break;
            }
        }
        return { value: running, preview };
    }

    gradeClass(value, integer = true) {
        if (value === null || value === undefined) {
            return "text-muted";
        }
        const shown = integer ? roundUnits(value) : value;
        return shown >= this.state.data.policy.pass_grade ? "text-primary" : "text-danger fw-bold";
    }

    fmtDecimal(value) {
        return fmtDecimal(value);
    }

    fmtInt(value) {
        return fmtInt(value);
    }

    cellError(student, trimesterId, column) {
        return this.state.errors[this.key(student, trimesterId, column)] || "";
    }

    async save() {
        if (this.errorCount || !this.dirtyCount || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const changes = Object.values(this.state.edits).map((e) => ({
                enrollment_id: e.enrollment_id,
                trimester_id: e.trimester_id,
                column: e.column,
                value: e.value,
                absent: !!e.absent,
            }));
            const result = await this.orm.call("edu.grade.grid", "grid_save", [
                this.state.classId,
                this.state.subjectId,
                changes,
            ]);
            if (!result.ok) {
                for (const error of result.errors) {
                    const key = `${error.enrollment_id}|${error.trimester_id || 0}|${error.column}`;
                    this.state.errors[key] = error.message;
                }
                this.notification.add("Nenhuma nota foi guardada: corrija as células assinaladas.", {
                    type: "danger",
                });
                return;
            }
            this.state.data = result.data;
            this.resetEdits();
            this.state.version++;
            this.notification.add("Notas guardadas.", { type: "success" });
        } finally {
            this.state.busy = false;
        }
    }

    discard() {
        this.resetEdits();
        // A tabela refaz-se e os inputs voltam aos valores gravados.
        this.state.version++;
    }

    async openContinuous(trimester) {
        const action = await this.orm.call("edu.grade.grid", "grid_open_continuous", [
            this.state.classId,
            this.state.subjectId,
            trimester.id,
        ]);
        await this.action.doAction(action, {
            onClose: () => this.openSubject(this.state.subjectId),
        });
    }

    get editableTrimesters() {
        return (this.state.data?.trimesters || []).filter((t) => t.editable);
    }

    get notices() {
        const data = this.state.data;
        if (!data) {
            return [];
        }
        const notices = [];
        const current = data.trimesters.find((t) => t.is_current);
        if (current && current.editable) {
            notices.push(`Pode alterar o ${current.name}, que é o corrente.`);
        }
        for (const t of data.trimesters.filter((t) => t.closed)) {
            notices.push(`O ${t.name} já foi encerrado: as notas só se corrigem por reapreciação.`);
        }
        for (const t of data.trimesters.filter((t) => t.permission_until)) {
            notices.push(`A secretaria autorizou-o a alterar o ${t.name} até ${t.permission_until}.`);
        }
        if (!data.trimesters.every((t) => t.editable || t.closed)) {
            notices.push("Para mudar notas de outro trimestre, peça autorização à secretaria.");
        }
        return notices;
    }

    /** As colunas da classificação do ano; PG e exame nacional lançam-se aqui. */
    get yearColumns() {
        const data = this.state.data;
        const columns = [];
        if (data.technical) {
            columns.push({ key: "cf", label: "CF", title: "Classificação de frequência: engloba os três trimestres", integer: true });
            if (data.subject.has_pg) {
                columns.push({ key: "pg", label: "PG", title: "Prova global", editable: true });
            }
            // As siglas do Despacho 60/08 (art. 17.º e a pauta do anexo): CF, PG, CA e, no ano terminal, CFD.
            columns.push({ key: "final", label: "CA", title: "Classificação anual (60% CF + 40% PG nas disciplinas com prova global), com a bonificação do conselho de turma", integer: true, strong: true });
            if (data.subject.terminal) {
                columns.push({ key: "cfd", label: "CFD", title: "Classificação final da disciplina (no ano terminal)", integer: true, strong: true });
            }
            return columns;
        } else {
            columns.push({ key: "annual", label: "CA", title: "Classificação anual (média dos trimestres)", integer: true });
            if (data.subject.has_en) {
                columns.push({ key: "en", label: "EN", title: "Exame nacional", editable: true });
            }
            columns.push({ key: "final", label: "CF", title: "Classificação final, com o exame e o conselho de turma", integer: true, strong: true });
        }
        if (data.subject.terminal && data.subject.span.length > 1) {
            columns.push({ key: "cfd", label: "CFD", title: "Classificação final da disciplina (todas as classes)", integer: true, strong: true });
        }
        return columns;
    }

    get legend() {
        return this.state.data.technical
            ? "NPP é a nota do professor e NPT a prova trimestral. CT1 é a média das duas; CT2 e CT3 juntam o trimestre aos anteriores (CT2 = (CT1 + média do 2.º trimestre)/2), como manda o Despacho 60/08."
            : "MAC é a média das avaliações contínuas, NPT a prova do trimestre e MT1, MT2 e MT3 a média de cada trimestre.";
    }

    /** As colunas do trimestre: a média leva o número (CT1, CT2, CT3 no técnico; MT1… no geral). */
    headers(trimester) {
        const n = trimester.number;
        return this.state.data.technical
            ? ["NPP", "NPT", `CT${n}`, "FJ", "FI"]
            : ["MAC", "NPT", `MT${n}`, "FJ", "FI"];
    }
}

registry.category("actions").add("edu_evaluation.grade_grid", GradeGrid);
