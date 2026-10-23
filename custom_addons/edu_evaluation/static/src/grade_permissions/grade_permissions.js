import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * «Autorizações para alterar notas», como a página do secPed-Express: o professor só lança no trimestre corrente;
 * para um trimestre passado ainda aberto (ou futuro), a secretaria dá-lhe uma autorização para a turma, a
 * disciplina e o trimestre, com motivo e prazo. Separadores «Activas» e «Todas», a situação de cada uma, revogar
 * com confirmação e «Nova autorização» guiada (o professor, depois as turmas e disciplinas que ele dá, depois os
 * trimestres que se podem autorizar).
 */
export class GradePermissions extends Component {
    static template = "edu_evaluation.GradePermissions";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = proxy({
            mode: "list",
            tab: "active",
            rows: [],
            activeCount: 0,
            busy: false,
            options: null,
            form: { teacherId: false, key: "", trimesterId: false, until: "", reason: "" },
        });
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        const data = await this.orm.call("edu.grade.permission.page", "permissions", [this.state.tab === "active"]);
        this.state.rows = data.rows;
        this.state.activeCount = data.active_count;
    }

    async selectTab(tab) {
        this.state.tab = tab;
        await this.load();
    }

    toneClass(tone) {
        return { pos: "text-success", muted: "text-muted" }[tone];
    }

    revoke(row) {
        this.dialog.add(ConfirmationDialog, {
            title: "Revogar a autorização?",
            body: `${row.teacher} deixa de poder alterar as notas de ${row.subject} da ${row.class} no ${row.trimester.split(",")[0]}. As notas que já lançou ficam.`,
            confirmLabel: "Revogar",
            confirm: async () => {
                await this.orm.call("edu.grade.permission.page", "revoke", [row.id]);
                this.notification.add("Autorização revogada.", { type: "success" });
                await this.load();
            },
            cancel: () => {},
        });
    }

    // Nova autorização

    async openNew() {
        this.state.options = await this.orm.call("edu.grade.permission.page", "form_options", []);
        this.state.form = {
            teacherId: false,
            key: "",
            trimesterId: false,
            until: this.state.options.default_until,
            reason: "",
        };
        this.state.mode = "new";
    }

    async backToList() {
        this.state.mode = "list";
        await this.load();
    }

    get teacher() {
        return (this.state.options?.teachers || []).find((t) => t.id === this.state.form.teacherId);
    }

    get assignment() {
        return (this.teacher?.options || []).find((o) => o.key === this.state.form.key);
    }

    onTeacher(ev) {
        this.state.form.teacherId = parseInt(ev.target.value, 10) || false;
        this.state.form.key = "";
    }

    onField(field, ev) {
        const value = ev.target.value;
        this.state.form[field] = field === "trimesterId" ? parseInt(value, 10) || false : value;
    }

    get canSave() {
        const f = this.state.form;
        return Boolean(this.assignment && f.trimesterId && f.until && f.reason.trim().length >= 5 && !this.state.busy);
    }

    async save() {
        if (!this.canSave) {
            return;
        }
        this.state.busy = true;
        try {
            const f = this.state.form;
            await this.orm.call("edu.grade.permission.page", "create_permission", [
                {
                    teacher_id: f.teacherId,
                    class_id: this.assignment.class_id,
                    subject_id: this.assignment.subject_id,
                    trimester_id: f.trimesterId,
                    until: f.until,
                    reason: f.reason,
                },
            ]);
            this.notification.add("Autorização dada.", { type: "success" });
            this.state.tab = "active";
            await this.backToList();
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("edu_evaluation.grade_permissions", GradePermissions);
