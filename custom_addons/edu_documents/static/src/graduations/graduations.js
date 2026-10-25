import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * «Diplomas e certificados», como a página do secPed-Express: os alunos que concluíram o curso, por ano lectivo e
 * curso, em cartões, com separadores por estado do diploma (por emitir, por verificar, por assinar, assinados). Em cada
 * cartão: os três passos do diploma (emitido, verificado, assinado), emitir (dá o número do diploma), o diploma e o
 * certificado (com pré-visualização), verificar e assinar (a direcção). «Registar conclusões» mostra as turmas da
 * classe final à esquerda e os alunos a quem o conselho de turma deu a conclusão do curso.
 */
export class Graduations extends Component {
    static template = "edu_documents.Graduations";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = proxy({
            mode: "list",
            tab: "all",
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

    /** Os separadores por estado do diploma, com as contagens. */
    get tabs() {
        const s = this.state.summary || {};
        const cancelled = this.state.rows.filter((r) => r.state === "cancelled").length;
        const tabs = [
            { key: "all", label: "Todas", count: s.total || 0 },
            { key: "draft", label: "Por emitir", count: s.draft || 0 },
            { key: "to_verify", label: "Por verificar", count: s.to_verify || 0 },
            { key: "to_sign", label: "Por assinar", count: s.to_sign || 0 },
            { key: "signed", label: "Assinados", count: s.signed || 0 },
        ];
        if (cancelled) {
            tabs.push({ key: "cancelled", label: "Anulados", count: cancelled });
        }
        return tabs;
    }

    get visibleRows() {
        const tab = this.state.tab;
        if (tab === "all") {
            return this.state.rows.filter((r) => r.state !== "cancelled");
        }
        return this.state.rows.filter((r) => r.diploma_state === tab);
    }

    /** Os passos do diploma: emitido (com o número), verificado e assinado. */
    steps(row) {
        const issued = row.state === "issued";
        return [
            { key: "issued", label: "Emitido", done: issued, detail: "" },
            { key: "verified", label: "Verificado", done: issued && row.verified, detail: row.verified_label },
            { key: "signed", label: "Assinado", done: issued && row.signed, detail: row.signed_label },
        ];
    }

    get summaryText() {
        const s = this.state.summary;
        if (!s || !s.total) {
            return "";
        }
        const head = `${s.total} ${s.total === 1 ? "aluno concluiu" : "alunos concluíram"}` + (this.yearName ? ` em ${this.yearName}` : "");
        if (s.signed === s.total) {
            return `${head}: todos com o diploma assinado.`;
        }
        const parts = [`${s.signed} com o diploma assinado`];
        if (s.to_verify) {
            parts.push(`${s.to_verify} por verificar`);
        }
        if (s.to_sign) {
            parts.push(`${s.to_sign} por assinar`);
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
        return (
            "Ainda não há conclusões registadas" +
            (this.yearName ? ` em ${this.yearName}` : "") +
            ". «Registar conclusões» mostra os alunos a quem o conselho de turma deu a conclusão do curso."
        );
    }

    badgeClass(tone) {
        return { pos: "text-bg-success", warn: "text-bg-warning", muted: "text-bg-light" }[tone];
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

    rowAction(method, row) {
        if (method === "issue") {
            this.dialog.add(ConfirmationDialog, {
                title: "Emitir a conclusão",
                body: `A conclusão de ${row.student} fica emitida e recebe o número do diploma, que não se repete.`,
                confirmLabel: "Emitir",
                confirm: () => this.doRowAction(method, row),
                cancel: () => {},
            });
            return;
        }
        return this.doRowAction(method, row);
    }

    async doRowAction(method, row) {
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

    async loadFinishers() {
        this.state.finishers = this.state.classId
            ? await this.orm.call("edu.graduation.page", "finishers", [this.state.classId])
            : [];
    }

    /** As turmas da classe final por curso, para o painel. */
    get classGroups() {
        const groups = [];
        for (const c of this.state.classes) {
            const course = c.course || "Sem curso";
            let group = groups.find((g) => g.course === course);
            if (!group) {
                group = { course, classes: [] };
                groups.push(group);
            }
            group.classes.push(c);
        }
        return groups;
    }

    async selectRegClass(classId) {
        this.state.classId = classId;
        await this.loadFinishers();
    }

    get selectedRegClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    get finishersText() {
        const total = this.state.finishers.length;
        const pending = this.pendingFinishers.length;
        const head = total === 1 ? "1 aluno concluiu o curso" : `${total} alunos concluíram o curso`;
        return pending ? `${head}; ${pending} por registar.` : `${head}; todos já registados.`;
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
