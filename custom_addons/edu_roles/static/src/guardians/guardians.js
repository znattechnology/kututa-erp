import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { StudentPicker } from "@edu_documents/student_picker/student_picker";

const AUTHORIZATIONS = [
    { key: "is_primary", label: "Encarregado principal", hint: "É a quem a escola liga primeiro; as facturas das propinas saem em nome dele se tiver NIF." },
    { key: "can_access_portal", label: "Pode ver o aluno no portal", hint: "Notas, faltas e propinas, com a conta do encarregado." },
    { key: "receive_notifications", label: "Recebe os avisos da escola", hint: "" },
    { key: "is_emergency", label: "Contacto de emergência", hint: "" },
    { key: "can_pickup", label: "Pode levantar o aluno na escola", hint: "" },
];

const EMPTY_GUARDIAN = { name: "", phone: "", email: "", id_number: "", vat: "", occupation: "", street: "", city: "" };

/**
 * «Encarregados de educação», como no secPed: a lista (contactos e educandos), «Criar encarregado», que segue logo
 * para o vincular, e «Vincular a aluno» num só ecrã: o aluno (com os encarregados que já tem, para não repetir), o
 * encarregado e a relação com as autorizações.
 */
export class GuardiansPage extends Component {
    static template = "edu_roles.GuardiansPage";
    static components = { Layout, StudentPicker };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.authorizations = AUTHORIZATIONS;
        const context = this.props.action.context || {};
        this.state = proxy({
            mode: "list",
            rows: [],
            query: "",
            busy: false,
            relationships: [],
            // Criar
            form: { ...EMPTY_GUARDIAN },
            // Vincular
            student: null,
            current: null,
            guardian: null,
            guardianQuery: "",
            guardianResults: [],
            relationship: "legal_guardian",
            options: {},
            primaryTouched: false,
            confirmUnlink: false,
        });
        this.searchTimer = null;
        onWillUnmount(() => clearTimeout(this.searchTimer));
        onWillStart(async () => {
            const options = await this.orm.call("edu.guardian.page", "options", []);
            this.state.relationships = options.relationships;
            if (context.guardian_mode === "new") {
                this.openNew();
            } else if (context.guardian_mode === "link") {
                await this.openLink(null);
            } else {
                await this.load();
            }
        });
    }

    get display() {
        return { controlPanel: {} };
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

    // Lista

    async load() {
        const data = await this.orm.call("edu.guardian.page", "listing", []);
        this.state.rows = data.rows;
    }

    async backToList() {
        this.state.mode = "list";
        await this.load();
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
    }

    get visibleRows() {
        const term = this.state.query.trim().toLowerCase();
        if (!term) {
            return this.state.rows;
        }
        return this.state.rows.filter((r) =>
            [r.name, r.phone, r.email, r.vat, ...r.links.map((l) => l.student)]
                .filter(Boolean)
                .some((s) => s.toLowerCase().includes(term))
        );
    }

    get summary() {
        const rows = this.visibleRows;
        if (!rows.length) {
            return null;
        }
        const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
        const noStudent = rows.filter((r) => !r.links.length).length;
        const noEmail = rows.filter((r) => !r.email).length;
        const term = this.state.query.trim();
        return {
            text:
                `${plural(rows.length, "encarregado", "encarregados")}${term ? ` com «${term}»` : ""}.` +
                (noEmail ? ` ${noEmail} sem e-mail: não poderão ter conta no portal.` : ""),
            alert: noStudent
                ? noStudent === 1
                    ? "1 não está vinculado a nenhum aluno."
                    : `${noStudent} não estão vinculados a nenhum aluno.`
                : "",
        };
    }

    openGuardian(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "edu.guardian",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // Criar

    openNew() {
        this.state.mode = "new";
        this.state.form = { ...EMPTY_GUARDIAN };
    }

    onForm(field, ev) {
        this.state.form[field] = ev.target.value;
    }

    get canCreate() {
        const f = this.state.form;
        return Boolean(f.name.trim() && f.phone.trim() && !this.state.busy);
    }

    async create() {
        if (!this.canCreate) {
            return;
        }
        await this.run(async () => {
            const guardian = await this.orm.call("edu.guardian.page", "create_guardian", [this.state.form]);
            this.notification.add(`${guardian.name} registado.`, { type: "success" });
            await this.openLink(guardian);
        });
    }

    // Vincular

    async openLink(guardian) {
        Object.assign(this.state, {
            mode: "link",
            student: null,
            current: null,
            guardian,
            guardianQuery: "",
            guardianResults: [],
            relationship: "legal_guardian",
            options: {
                is_primary: true,
                can_access_portal: true,
                receive_notifications: true,
                is_emergency: false,
                can_pickup: true,
            },
            primaryTouched: false,
        });
        if (!guardian) {
            await this.searchGuardians();
        }
    }

    linkFrom(row) {
        return this.openLink(row);
    }

    async pickStudent(row) {
        this.state.student = row;
        this.state.current = null;
        this.state.primaryTouched = false;
        // A resposta de um aluno escolhido antes não se sobrepõe à do aluno actual.
        const request = (this.studentRequest = (this.studentRequest || 0) + 1);
        const current = await this.orm.call("edu.guardian.page", "student_guardians", [row.student_id]);
        if (request !== this.studentRequest) {
            return;
        }
        this.state.current = current;
        if (!this.state.guardian) {
            await this.searchGuardians();
        }
        // Quem já tem encarregado principal: o novo não o substitui por omissão.
        this.state.options.is_primary = !current.some((l) => l.primary);
    }

    otherStudent() {
        this.state.student = null;
        this.state.current = null;
    }

    get currentPrimary() {
        return (this.state.current || []).find((l) => l.primary);
    }

    get alreadyLinked() {
        const g = this.state.guardian;
        return Boolean(g && (this.state.current || []).some((l) => l.guardian_id === g.id));
    }

    onGuardianQuery(ev) {
        this.state.guardianQuery = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.searchGuardians(), 300);
    }

    async searchGuardians() {
        const request = (this.searchRequest = (this.searchRequest || 0) + 1);
        const studentId = this.state.student ? this.state.student.student_id : false;
        const results = await this.orm.call("edu.guardian.page", "search_guardians", [
            this.state.guardianQuery,
            studentId,
        ]);
        if (request === this.searchRequest) {
            this.state.guardianResults = results;
        }
    }

    pickGuardian(row) {
        this.state.guardian = row;
    }

    async otherGuardian() {
        this.state.guardian = null;
        await this.searchGuardians();
    }

    contact(row) {
        return [row.phone, row.email].filter(Boolean).join(", ");
    }

    guardianLine(row) {
        const students = row.links.map((l) => l.student).join(", ");
        return [row.phone, row.email, students ? `encarregado de ${students}` : ""].filter(Boolean).join(" · ");
    }

    onRelationship(ev) {
        this.state.relationship = ev.target.value;
    }

    toggleOption(key) {
        if (key === "is_primary") {
            this.state.primaryTouched = true;
        }
        this.state.options[key] = !this.state.options[key];
    }

    get linkLabel() {
        if (!this.state.student) {
            return "Escolha o aluno";
        }
        if (!this.state.guardian) {
            return "Escolha o encarregado";
        }
        if (this.state.current === null) {
            return "A ler…";
        }
        return "Vincular";
    }

    get canLink() {
        return Boolean(
            this.state.student && this.state.guardian && this.state.current !== null && !this.alreadyLinked && !this.state.busy
        );
    }

    async link() {
        if (!this.canLink) {
            return;
        }
        await this.run(async () => {
            const s = this.state;
            await this.orm.call("edu.guardian.page", "link", [
                s.student.student_id,
                s.guardian.id,
                s.relationship,
                s.options,
            ]);
            this.notification.add(`${s.guardian.name} é agora encarregado de ${s.student.name}.`, { type: "success" });
            await this.backToList();
        });
    }

    askUnlink(link) {
        this.state.confirmUnlink = link.id;
    }

    cancelUnlink() {
        this.state.confirmUnlink = false;
    }

    async removeLink(link) {
        await this.run(async () => {
            const result = await this.orm.call("edu.guardian.page", "unlink_link", [link.id]);
            this.state.current = result.links;
            this.state.confirmUnlink = false;
            const promoted = result.promoted ? ` ${result.promoted} passa a ser o encarregado principal.` : "";
            this.notification.add(`${link.guardian} deixou de ser encarregado de ${link.student}.${promoted}`, {
                type: "success",
            });
        });
    }
}

registry.category("actions").add("edu_roles.guardians", GuardiansPage);
