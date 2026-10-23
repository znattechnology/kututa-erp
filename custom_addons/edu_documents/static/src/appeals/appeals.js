import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { StudentPicker } from "../student_picker/student_picker";

/**
 * «Reapreciações», conforme a lei (Despacho 60/08, art. 15.º; DE 424/25, art. 36.º): a secretaria regista o pedido e
 * informa o interessado; a direcção admite (ou indefere liminarmente, fora de prazo ou sem fundamento) e regista a
 * deliberação do conselho de turma extraordinário ou da comissão e, sem provimento no técnico, a do Conselho
 * Pedagógico. Deferido, a nota corrige-se e a pauta recalcula-se.
 */
export class Appeals extends Component {
    static template = "edu_documents.Appeals";
    static components = { Layout, StudentPicker };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            mode: "list",
            tab: "open",
            rows: [],
            openCount: 0,
            alerts: 0,
            isManager: false,
            busy: false,
            // Novo pedido
            pick: null,
            options: null,
            form: {},
            // Processo
            detail: null,
            action: { meeting: "", reason: "", text: "", minutes: "", gradeId: false, newScore: "", notified: "" },
        });
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        const data = await this.orm.call("edu.appeal.page", "appeals", [this.state.tab]);
        Object.assign(this.state, {
            rows: data.rows,
            openCount: data.open_count,
            alerts: data.alerts,
            isManager: data.is_manager,
        });
    }

    async selectTab(tab) {
        this.state.tab = tab;
        await this.load();
    }

    stateClass(state) {
        return {
            granted: "text-bg-success",
            denied: "text-bg-secondary",
            rejected: "text-bg-secondary",
            appealed: "text-bg-warning",
            review: "text-bg-info",
        }[state] || "text-bg-light";
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

    async backToList() {
        this.state.mode = "list";
        this.state.detail = null;
        await this.load();
    }

    // Novo pedido

    openNew() {
        this.state.mode = "new";
        this.state.pick = null;
        this.state.options = null;
    }

    async choose(row) {
        this.state.pick = row;
        const options = await this.orm.call("edu.appeal.page", "request_options", [row.enrollment_id]);
        this.state.options = options;
        this.state.form = {
            subjectId: false,
            momentId: options.moments.length === 1 ? options.moments[0].id : "",
            requesterType: "guardian",
            requesterName: options.guardian,
            requestDate: options.today,
            postingDate: "",
            reason: "",
            attachments: [],
        };
    }

    otherStudent() {
        this.state.pick = null;
        this.state.options = null;
    }

    onForm(field, ev) {
        let value = ev.target.value;
        if (field === "subjectId") {
            value = parseInt(value, 10) || false;
        } else if (field === "momentId") {
            value = value === "" ? "" : parseInt(value, 10);
        }
        this.state.form[field] = value;
        if (field === "requesterType") {
            this.state.form.requesterName = value === "guardian" ? this.state.options.guardian : this.state.pick.name;
        }
    }

    async onFiles(ev) {
        const files = [...ev.target.files];
        const read = (file) =>
            new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = () => resolve({ name: file.name, datas: reader.result.split(",")[1] });
                reader.readAsDataURL(file);
            });
        this.state.form.attachments = await Promise.all(files.map(read));
    }

    get canSubmit() {
        const f = this.state.form;
        return Boolean(f.subjectId && f.momentId !== "" && f.reason.trim() && f.requestDate && !this.state.busy);
    }

    async submit() {
        if (!this.canSubmit) {
            return;
        }
        await this.run(async () => {
            const f = this.state.form;
            const detail = await this.orm.call("edu.appeal.page", "create_request", [
                {
                    enrollment_id: this.state.pick.enrollment_id,
                    subject_id: f.subjectId,
                    trimester_id: f.momentId || false,
                    requester_type: f.requesterType,
                    requester_name: f.requesterName,
                    request_date: f.requestDate,
                    posting_date: f.postingDate || false,
                    reason: f.reason,
                    attachments: f.attachments,
                },
            ]);
            this.notification.add("Pedido registado.", { type: "success" });
            this.showDetail(detail);
        });
    }

    // Processo

    showDetail(detail) {
        this.state.detail = detail;
        this.state.mode = "detail";
        this.state.action = {
            meeting: detail.meeting_iso || "",
            reason: "",
            text: "",
            minutes: detail.minutes_ref || "",
            gradeId: false,
            newScore: "",
            notified: "",
        };
    }

    async open(row) {
        this.showDetail(await this.orm.call("edu.appeal.page", "detail", [row.id]));
    }

    onAction(field, ev) {
        const value = ev.target.value;
        this.state.action[field] = field === "gradeId" ? parseInt(value, 10) || false : value;
    }

    async call(method, args, message) {
        await this.run(async () => {
            this.showDetail(await this.orm.call("edu.appeal.page", method, [this.state.detail.id, ...args]));
            this.notification.add(message, { type: "success" });
        });
    }

    admit() {
        return this.call("admit", [this.state.action.meeting || false], "Pedido admitido.");
    }

    reject() {
        return this.call("reject", [this.state.action.reason], "Pedido indeferido liminarmente.");
    }

    deliberate(outcome) {
        const a = this.state.action;
        return this.call(
            "deliberate",
            [{ outcome, text: a.text, minutes_ref: a.minutes, grade_id: a.gradeId, new_score: a.newScore }],
            outcome === "grant" ? "Deferido: a nota foi corrigida." : "Deliberação registada."
        );
    }

    notify() {
        return this.call("notify", [this.state.action.notified || false], "Registado: o interessado foi informado.");
    }
}

registry.category("actions").add("edu_documents.appeals", Appeals);
