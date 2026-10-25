import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { StudentPanel } from "../student_panel/student_panel";

/**
 * «Declarações», como a página do secPed-Express, no formato do Histórico do aluno: à esquerda escolhe-se o aluno
 * pela turma (a lista dos alunos, pelo número) ou pelo nome, no ano lectivo; à direita o tipo de declaração. Os dados de identificação que faltam completam-se aqui
 * e ficam na ficha do aluno; o que continuar vazio sai como linha para preencher à mão. «Ver a declaração» mostra-a
 * sem a emitir; «Emitir e imprimir» dá-lhe o número do registo e mostra-a para imprimir. As já emitidas reimprimem-se
 * (2.ª via).
 */
export class Declarations extends Component {
    static template = "edu_documents.Declarations";
    static components = { Layout, StudentPanel };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = proxy({
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
        onWillStart(async () => {
            const options = await this.orm.call("edu.declaration.page", "page_options", []);
            this.state.types = options.types;
            this.state.states = options.states;
            this.state.fields = options.identity_fields;
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    // O aluno

    choose(row) {
        if (this.state.pick && row.enrollment_id === this.state.pick.enrollment_id) {
            return;
        }
        if (this.state.data && this.changed) {
            this.dialog.add(ConfirmationDialog, {
                title: "Dados por guardar",
                body: `Os dados de identificação de ${this.state.data.student.name} foram alterados e não foram guardados.`,
                confirmLabel: "Trocar de aluno sem guardar",
                cancelLabel: "Continuar a editar",
                confirm: () => this.pickStudent(row),
                cancel: () => {},
            });
            return;
        }
        return this.pickStudent(row);
    }

    async pickStudent(row) {
        this.state.pick = row;
        this.state.data = null;
        await this.loadStudent();
    }

    // A declaração

    async loadStudent() {
        const pick = this.state.pick;
        const type = this.state.type;
        const data = await this.orm.call("edu.declaration.page", "student_data", [pick.enrollment_id, type]);
        // Escolheu outro aluno ou outro tipo entretanto: esta resposta já não serve.
        if (this.state.pick !== pick || this.state.type !== type) {
            return;
        }
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
