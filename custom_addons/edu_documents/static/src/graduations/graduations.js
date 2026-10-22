import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * «Diplomas e certificados», como a página do secPed-Express: os alunos que concluíram o curso, por ano lectivo e
 * curso, e o resumo (quantos com o diploma assinado, quantos por verificar). Em cada linha: emitir (dá o número do
 * diploma), o diploma e o certificado, verificar e assinar (a direcção). «Registar conclusões» mostra os alunos da
 * turma da classe final a quem o conselho de turma deu a conclusão do curso.
 */
export class Graduations extends Component {
    static template = "edu_documents.Graduations";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            mode: "list",
            years: [],
            courses: [],
            isManager: false,
            yearId: false,
            courseId: false,
            rows: [],
            summary: null,
            busy: false,
            // Registar conclusões
            regYearId: false,
            classes: [],
            classId: false,
            finishers: [],
        });
        onWillStart(async () => {
            const options = await this.orm.call("edu.graduation.page", "page_options", []);
            Object.assign(this.state, {
                years: options.years,
                courses: options.courses,
                isManager: options.is_manager,
                yearId: options.year_id,
                regYearId: options.year_id,
            });
            await this.load();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    // Lista

    async load() {
        const data = await this.orm.call("edu.graduation.page", "graduations", [
            this.state.yearId,
            this.state.courseId,
        ]);
        this.state.rows = data.rows;
        this.state.summary = data.summary;
    }

    get yearName() {
        return (this.state.years.find((y) => y.id === this.state.yearId) || {}).name || "";
    }

    async onYearChange(ev) {
        this.state.yearId = parseInt(ev.target.value, 10) || false;
        await this.load();
    }

    async onCourseChange(ev) {
        this.state.courseId = parseInt(ev.target.value, 10) || false;
        await this.load();
    }

    get summaryText() {
        const s = this.state.summary;
        if (!s || !s.total) {
            return "";
        }
        const head = `${s.total} ${s.total === 1 ? "aluno concluiu" : "alunos concluíram"}${this.yearName ? ` em ${this.yearName}` : ""}`;
        if (s.signed === s.total) {
            return `${head}: todos com o diploma assinado.`;
        }
        const parts = [`${s.signed} com o diploma assinado`];
        if (s.to_verify) {
            parts.push(`${s.to_verify} por verificar`);
        }
        if (s.draft) {
            parts.push(`${s.draft} por emitir`);
        }
        return `${head}: ${parts.join(", ")}.`;
    }

    get emptyText() {
        if (this.state.courseId) {
            return "Nenhum aluno deste curso concluiu neste ano lectivo.";
        }
        return `Ainda não há conclusões registadas${this.yearName ? ` em ${this.yearName}` : ""}. «Registar conclusões» mostra os alunos a quem o conselho de turma deu a conclusão do curso.`;
    }

    toneClass(tone) {
        return { pos: "text-success", warn: "text-warning", muted: "text-muted" }[tone];
    }

    fmtAverage(value) {
        return value ? String(Math.round(value)) : "—";
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

    replace(row) {
        const index = this.state.rows.findIndex((r) => r.id === row.id);
        if (index >= 0) {
            this.state.rows[index] = row;
        }
    }

    async rowAction(method, row) {
        if (method === "issue" && !window.confirm(`Emitir a conclusão de ${row.student}? Atribui o número do diploma.`)) {
            return;
        }
        await this.run(async () => {
            this.replace(await this.orm.call("edu.graduation.page", method, [row.id]));
            await this.load();
        });
    }

    async printDocument(row, kind) {
        await this.run(async () => {
            const action = await this.orm.call("edu.graduation.page", "print_document", [row.id, kind]);
            await this.action.doAction(action);
        });
    }

    async openForm(row) {
        const action = await this.orm.call("edu.graduation.page", "open_form", [row.id]);
        await this.action.doAction(action, { onClose: () => this.load() });
    }

    // Registar conclusões

    async openRegister() {
        this.state.mode = "register";
        this.state.classId = false;
        this.state.finishers = [];
        await this.loadClasses();
    }

    async backToList() {
        this.state.mode = "list";
        await this.load();
    }

    async loadClasses() {
        this.state.classes = this.state.regYearId
            ? await this.orm.call("edu.graduation.page", "final_classes", [this.state.regYearId])
            : [];
    }

    async onRegYearChange(ev) {
        this.state.regYearId = parseInt(ev.target.value, 10) || false;
        this.state.classId = false;
        this.state.finishers = [];
        await this.loadClasses();
    }

    async onRegClassChange(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        await this.loadFinishers();
    }

    async loadFinishers() {
        this.state.finishers = this.state.classId
            ? await this.orm.call("edu.graduation.page", "finishers", [this.state.classId])
            : [];
    }

    get selectedRegClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    get pendingFinishers() {
        return this.state.finishers.filter((f) => !f.registered && f.average !== null);
    }

    async register(rows) {
        await this.run(async () => {
            const result = await this.orm.call("edu.graduation.page", "register", [rows.map((r) => r.result_id)]);
            for (const error of result.errors) {
                this.notification.add(error, { type: "danger" });
            }
            if (result.done) {
                this.notification.add(
                    result.done === 1 ? "Conclusão registada." : `${result.done} conclusões registadas.`,
                    { type: "success" }
                );
            }
            await this.loadFinishers();
        });
    }
}

registry.category("actions").add("edu_documents.graduations", Graduations);
