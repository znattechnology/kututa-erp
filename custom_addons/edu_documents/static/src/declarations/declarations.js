import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * «Declarações», como a página do secPed-Express: escolhe-se o aluno pela turma (a lista dos alunos, pelo número)
 * ou pelo nome, no ano lectivo; depois o tipo de declaração. Os dados de identificação que faltam completam-se aqui
 * e ficam na ficha do aluno; o que continuar vazio sai como linha para preencher à mão. «Ver a declaração» mostra-a
 * sem a emitir; «Emitir e imprimir» dá-lhe o número do registo e gera o PDF. As já emitidas reimprimem-se (2.ª via).
 */
export class Declarations extends Component {
    static template = "edu_documents.Declarations";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            yearId: false,
            years: [],
            classes: [],
            classId: false,
            students: [],
            query: "",
            results: [],
            searching: false,
            types: [],
            states: [],
            fields: [],
            pick: null,
            type: "frequency",
            data: null,
            identity: {},
            saved: {},
            purpose: "",
            busy: false,
        });
        this.searchTimer = null;
        onWillUnmount(() => clearTimeout(this.searchTimer));
        onWillStart(() => this.loadYear(false));
    }

    get display() {
        return { controlPanel: {} };
    }

    // Ano, turma e aluno

    async loadYear(yearId) {
        const options = await this.orm.call("edu.declaration.page", "page_options", [yearId]);
        Object.assign(this.state, {
            yearId: options.year_id,
            years: options.years,
            classes: options.classes,
            types: options.types,
            states: options.states,
            fields: options.identity_fields,
            classId: false,
            students: [],
            results: [],
            query: "",
        });
    }

    async onYearChange(ev) {
        await this.loadYear(parseInt(ev.target.value, 10) || false);
    }

    async onClassChange(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        this.state.students = this.state.classId
            ? await this.orm.call("edu.declaration.page", "class_students", [this.state.classId])
            : [];
    }

    get selectedClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.search(), 300);
    }

    async search() {
        const query = this.state.query.trim();
        if (query.length < 2) {
            this.state.results = [];
            return;
        }
        this.state.searching = true;
        try {
            this.state.results = await this.orm.call("edu.declaration.page", "search_students", [
                this.state.yearId,
                query,
            ]);
        } finally {
            this.state.searching = false;
        }
    }

    async choose(row) {
        this.state.pick = row;
        await this.loadStudent();
    }

    onStudentSelect(ev) {
        const id = parseInt(ev.target.value, 10);
        const row = this.state.students.find((s) => s.enrollment_id === id);
        if (row) {
            this.choose(row);
        }
    }

    otherStudent() {
        if (this.changed && !window.confirm("Os dados de identificação alterados não foram guardados. Trocar de aluno?")) {
            return;
        }
        this.state.pick = null;
        this.state.data = null;
    }

    // A declaração

    async loadStudent() {
        const data = await this.orm.call("edu.declaration.page", "student_data", [
            this.state.pick.enrollment_id,
            this.state.type,
        ]);
        const sameStudent = this.state.data && this.state.data.enrollment.id === data.enrollment.id;
        this.state.data = data;
        if (!sameStudent) {
            this.state.identity = { ...data.identity };
            this.state.saved = { ...data.identity };
            this.state.purpose = "";
        }
    }

    async selectType(type) {
        this.state.type = type;
        await this.loadStudent();
    }

    onIdentity(key, ev) {
        const value = ev.target.value;
        this.state.identity[key] = key === "birth_state_id" ? parseInt(value, 10) || false : value;
    }

    onPurpose(ev) {
        this.state.purpose = ev.target.value;
    }

    get changed() {
        return this.state.fields.some((f) => (this.state.identity[f.key] || "") !== (this.state.saved[f.key] || ""));
    }

    get missing() {
        return this.state.fields.filter((f) => !this.state.identity[f.key]);
    }

    get typeName() {
        return (this.state.types.find((t) => t.key === this.state.type) || {}).name || "";
    }

    async save() {
        await this.run(async () => {
            await this.orm.call("edu.declaration.page", "save_identity", [
                this.state.data.enrollment.id,
                this.state.identity,
            ]);
            this.state.saved = { ...this.state.identity };
            this.notification.add("Dados do aluno guardados.", { type: "success" });
        });
    }

    async open(method) {
        await this.run(async () => {
            const action = await this.orm.call("edu.declaration.page", method, [
                this.state.data.enrollment.id,
                this.state.type,
                this.state.identity,
                this.state.purpose,
            ]);
            this.state.saved = { ...this.state.identity };
            await this.action.doAction(action);
            if (method === "issue_and_print") {
                await this.loadStudent();
            }
        });
    }

    async reprint(document) {
        await this.run(async () => {
            const action = await this.orm.call("edu.declaration.page", "reprint", [document.id]);
            await this.action.doAction(action);
            await this.loadStudent();
        });
    }

    async run(callback) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await callback();
        } finally {
            this.state.busy = false;
        }
    }

    openRegistry() {
        this.action.doAction("edu_documents.action_edu_document");
    }
}

registry.category("actions").add("edu_documents.declarations", Declarations);
