import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

// Os separadores de cada página: o estado ou os estados que mostram.
const TABS = {
    internship: [
        { id: "all", label: "Todos", states: [] },
        { id: "planned", label: "Por começar", states: ["planned"] },
        { id: "ongoing", label: "A decorrer", states: ["ongoing"] },
        { id: "passed", label: "Aprovados", states: ["passed"] },
        { id: "failed", label: "Não aprovados", states: ["failed"] },
        { id: "cancelled", label: "Anulados", states: ["cancelled"] },
    ],
    project: [
        { id: "all", label: "Todos", states: [] },
        { id: "course", label: "Em curso", states: ["proposed", "ongoing"] },
        { id: "delivered", label: "Entregues", states: ["submitted", "defended"] },
        { id: "passed", label: "Aprovados", states: ["passed"] },
        { id: "failed", label: "Reprovados", states: ["failed"] },
    ],
};

/**
 * «Estágios» e «Trabalho de fim de curso» (PAP), como no secPed: a lista com o resumo, os separadores e a pesquisa; o
 * «Novo» pela turma da classe final (o estágio a vários alunos de uma vez, na mesma entidade); a ficha de
 * acompanhamento, com os relatórios entregues (estágio) e a defesa (PAP). O professor vê só os seus orientandos.
 */
export class TrainingPage extends Component {
    static template = "edu_records.TrainingPage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const context = this.props.action.context || {};
        // «Orientações» (o menu do professor, como no secPed): os estágios de que é tutor e as PAP que orienta numa só
        // página, com a escolha entre os dois.
        this.switchable = Boolean(context.training_switch);
        this.state = proxy({
            kind: context.training_kind === "project" ? "project" : "internship",
            mode: "list",
            rows: [],
            years: [],
            yearId: "",
            tab: "all",
            query: "",
            isStaff: false,
            isManager: false,
            busy: false,
            // Novo
            options: null,
            classId: false,
            students: [],
            chosen: {},
            form: {},
            // Ficha
            detail: null,
            edit: {},
            grade: "",
            submitted: "",
            report: { name: "", date: "", file: null },
            confirmRemove: false,
            // «Orientações»: as linhas dos estágios e das PAP.
            both: null,
        });
        onWillStart(async () => {
            await this.load();
            // «Novo estágio» no menu abre a página já no formulário.
            if (context.training_new && this.state.isStaff) {
                await this.openNew();
            }
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get kind() {
        return this.state.kind;
    }


    get isProject() {
        return this.kind === "project";
    }

    get title() {
        if (this.switchable) {
            return "Orientações";
        }
        return this.isProject ? "Trabalho de fim de curso" : "Estágios";
    }

    get backLabel() {
        if (this.switchable) {
            return "Voltar às orientações";
        }
        return this.isProject ? "Voltar aos trabalhos" : "Voltar aos estágios";
    }

    get noun() {
        return this.isProject ? "trabalho" : "estágio";
    }

    async load() {
        if (this.switchable) {
            // «Orientações»: as duas listas, uma por baixo da outra, como no secPed.
            const [internships, projects] = await Promise.all([
                this.orm.call("edu.training.page", "listing", ["internship"]),
                this.orm.call("edu.training.page", "listing", ["project"]),
            ]);
            this.state.both = { internship: internships.rows, project: projects.rows };
        }
        const data = await this.orm.call("edu.training.page", "listing", [this.kind]);
        Object.assign(this.state, {
            rows: data.rows,
            years: data.years,
            yearId: data.year_id || "",
            isStaff: data.is_staff,
            isManager: data.is_manager,
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

    // Lista

    get tabs() {
        const rows = this.yearRows;
        return TABS[this.kind]
            .map((tab) => ({
                ...tab,
                count: tab.states.length ? rows.filter((r) => tab.states.includes(r.state)).length : rows.length,
            }))
            .filter((tab) => tab.id !== "cancelled" || tab.count);
    }

    get yearRows() {
        const yearId = this.state.yearId;
        return yearId ? this.state.rows.filter((r) => r.year_id === yearId) : this.state.rows;
    }

    get visibleRows() {
        const tab = TABS[this.kind].find((t) => t.id === this.state.tab);
        const term = this.state.query.trim().toLowerCase();
        return this.yearRows.filter(
            (r) =>
                (!tab.states.length || tab.states.includes(r.state)) &&
                (!term ||
                    [r.student, r.entity, r.supervisor, r.tutor, r.title, r.advisor, r.course, r.class]
                        .filter(Boolean)
                        .some((s) => s.toLowerCase().includes(term)))
        );
    }

    count(...states) {
        return this.yearRows.filter((r) => states.includes(r.state)).length;
    }

    get summary() {
        const rows = this.yearRows;
        if (!rows.length) {
            return "";
        }
        const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
        if (this.isProject) {
            const open = rows.filter((r) => !["passed", "failed"].includes(r.state));
            const noAdvisor = open.filter((r) => !r.advisor).length;
            return {
                text:
                    `${plural(rows.length, "trabalho", "trabalhos")}: ${this.count("proposed", "ongoing")} em curso, ` +
                    `${this.count("submitted", "defended")} entregues ou defendidos e ` +
                    `${plural(this.count("passed"), "aprovado", "aprovados")}.`,
                alert: noAdvisor ? `${plural(noAdvisor, "ainda não tem", "ainda não têm")} orientador.` : "",
            };
        }
        const entities = new Set(rows.map((r) => r.entity.trim().toLowerCase()).filter(Boolean)).size;
        const noTutor = rows.filter((r) => ["planned", "ongoing"].includes(r.state) && !r.tutor).length;
        return {
            text:
                `${plural(rows.length, "estágio", "estágios")} em ${plural(entities, "entidade", "entidades")}: ` +
                `${this.count("ongoing")} a decorrer, ${this.count("planned")} por começar e ` +
                `${plural(this.count("passed"), "aprovado", "aprovados")}.`,
            alert: noTutor ? `${plural(noTutor, "ainda não tem", "ainda não têm")} tutor da escola.` : "",
        };
    }

    get emptyText() {
        if (!this.state.rows.length) {
            if (!this.state.isStaff) {
                return this.isProject
                    ? "Não orienta nenhum trabalho de fim de curso, nem é júri de nenhum."
                    : "Não é tutor de nenhum estágio.";
            }
            return this.isProject
                ? "Ainda não há trabalhos de fim de curso. «Novo trabalho» regista o tema e o orientador de um finalista."
                : "Ainda não há estágios. «Novo estágio» atribui o estágio aos alunos de uma turma da classe final, de uma vez.";
        }
        if (this.state.query.trim()) {
            return `Nenhum ${this.noun} corresponde a «${this.state.query.trim()}».`;
        }
        return `Nenhum ${this.noun} neste separador.`;
    }

    selectTab(tab) {
        this.state.tab = tab;
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
    }

    onYear(ev) {
        this.state.yearId = parseInt(ev.target.value, 10) || "";
    }

    stateClass(state) {
        return (
            {
                passed: "text-bg-success",
                failed: "text-bg-danger",
                cancelled: "text-bg-secondary",
                ongoing: "text-bg-info",
                submitted: "text-bg-primary",
                defended: "text-bg-primary",
            }[state] || "text-bg-light"
        );
    }

    fmtGrade(grade) {
        if (grade === null || grade === undefined) {
            return "—";
        }
        const value = Math.round(grade * 10) / 10;
        return value.toLocaleString("pt-PT", { maximumFractionDigits: 1 });
    }

    async backToList() {
        this.state.mode = "list";
        this.state.detail = null;
        await this.load();
    }

    // Novo

    async openNew() {
        const options = await this.orm.call("edu.training.page", "new_options", [this.kind]);
        Object.assign(this.state, {
            mode: "new",
            options,
            classId: false,
            students: [],
            chosen: {},
            form: this.isProject
                ? { name: "", description: "", advisor_id: "" }
                : { entity: "", supervisor: "", supervisor_contact: "", tutor_id: "", date_start: "", date_end: "" },
        });
    }

    async onClass(ev) {
        const classId = parseInt(ev.target.value, 10) || false;
        this.state.classId = classId;
        this.state.chosen = {};
        this.state.students = classId
            ? await this.orm.call("edu.training.page", "class_students", [this.kind, classId])
            : [];
    }

    get freeStudents() {
        return this.state.students.filter((s) => !s.taken);
    }

    get chosenIds() {
        return Object.keys(this.state.chosen)
            .filter((id) => this.state.chosen[id])
            .map((id) => parseInt(id, 10));
    }

    get allChosen() {
        const free = this.freeStudents;
        return free.length > 0 && free.every((s) => this.state.chosen[s.enrollment_id]);
    }

    toggleStudent(student) {
        if (student.taken) {
            return;
        }
        if (this.isProject) {
            // A PAP é de um aluno.
            this.state.chosen = { [student.enrollment_id]: true };
            return;
        }
        this.state.chosen[student.enrollment_id] = !this.state.chosen[student.enrollment_id];
    }

    toggleAll() {
        const all = this.allChosen;
        const chosen = {};
        for (const s of this.freeStudents) {
            chosen[s.enrollment_id] = !all;
        }
        this.state.chosen = chosen;
    }

    onNew(field, ev) {
        this.state.form[field] = ev.target.value;
    }

    get dateError() {
        const f = this.state.mode === "new" ? this.state.form : this.state.edit;
        return Boolean(f.date_start && f.date_end && f.date_end < f.date_start);
    }

    get canCreate() {
        const f = this.state.form;
        const filled = this.isProject ? f.name.trim().length >= 3 : f.entity.trim().length >= 2;
        return Boolean(this.chosenIds.length && filled && !this.dateError && !this.state.busy);
    }

    get createLabel() {
        const n = this.chosenIds.length;
        if (this.isProject) {
            return "Criar trabalho";
        }
        return n > 1 ? `Criar ${n} estágios` : "Criar estágio";
    }

    async create() {
        if (!this.canCreate) {
            return;
        }
        await this.run(async () => {
            const f = this.state.form;
            const vals = { ...f, enrollment_ids: this.chosenIds };
            for (const key of ["tutor_id", "advisor_id"]) {
                if (key in vals) {
                    vals[key] = parseInt(vals[key], 10) || false;
                }
            }
            const ids = await this.orm.call("edu.training.page", "create_records", [this.kind, vals]);
            this.notification.add(
                this.isProject ? "Trabalho criado." : ids.length === 1 ? "Estágio criado." : `${ids.length} estágios criados.`,
                { type: "success" }
            );
            if (ids.length === 1) {
                await this.open({ id: ids[0] });
            } else {
                await this.backToList();
            }
        });
    }

    // Ficha

    showDetail(detail, keepEdits = false) {
        this.state.detail = detail;
        this.state.mode = "detail";
        this.state.confirmRemove = false;
        this.state.report = { name: "", date: "", file: null };
        if (keepEdits) {
            // Os relatórios gravam-se à parte: o que se escreveu na ficha e ainda não se guardou fica.
            return;
        }
        // A nota de um estágio reaberto fica à vista, mesmo que seja 0.
        this.state.grade = detail.grade !== null ? `${detail.grade_value}` : "";
        this.state.submitted = "";
        this.state.edit = this.isProject
            ? {
                  name: detail.title,
                  description: detail.description,
                  advisor_id: detail.advisor_id || "",
                  jury_ids: [...detail.jury_ids],
                  defense_date: detail.defense_date,
                  note: detail.note,
              }
            : {
                  entity: detail.entity,
                  supervisor: detail.supervisor,
                  supervisor_contact: detail.supervisor_contact,
                  tutor_id: detail.tutor_id || "",
                  date_start: detail.date_start,
                  date_end: detail.date_end,
                  hours: `${detail.hours}`,
                  appraisal: detail.appraisal,
                  note: detail.note,
              };
    }

    async open(row, kind = false) {
        if (kind) {
            this.state.kind = kind;
        }
        this.showDetail(await this.orm.call("edu.training.page", "detail", [this.kind, row.id]));
    }

    get closed() {
        return ["passed", "failed", "cancelled"].includes(this.state.detail.state);
    }

    get editable() {
        return this.state.detail.is_staff && !this.closed;
    }

    onEdit(field, ev) {
        this.state.edit[field] = ev.target.value;
    }

    onJury(ev) {
        this.state.edit.jury_ids = [...ev.target.selectedOptions].map((o) => parseInt(o.value, 10));
    }

    onGrade(ev) {
        this.state.grade = ev.target.value;
    }

    onSubmitted(ev) {
        this.state.submitted = ev.target.value;
    }

    get gradeError() {
        const g = this.state.grade;
        if (g === "") {
            return "";
        }
        const value = parseFloat(g);
        return Number.isNaN(value) || value < 0 || value > 20 ? "A nota vai de 0 a 20." : "";
    }

    editValues() {
        const vals = { ...this.state.edit };
        if (!this.state.detail.is_staff) {
            delete vals.jury_ids;
        }
        for (const key of ["tutor_id", "advisor_id"]) {
            if (key in vals) {
                vals[key] = parseInt(vals[key], 10) || false;
            }
        }
        if ("hours" in vals) {
            vals.hours = parseInt(vals.hours, 10) || 0;
        }
        return vals;
    }

    async save() {
        if (this.dateError) {
            return;
        }
        await this.run(async () => {
            const d = this.state.detail;
            this.showDetail(await this.orm.call("edu.training.page", "save", [this.kind, d.id, this.editValues()]));
            this.notification.add(this.isProject ? "Trabalho guardado." : "Estágio guardado.", { type: "success" });
        });
    }

    async act(action, value, message) {
        await this.run(async () => {
            const d = this.state.detail;
            // O que se escreveu na ficha grava-se antes (a data da defesa, as horas).
            if (this.editable) {
                await this.orm.call("edu.training.page", "save", [this.kind, d.id, this.editValues()]);
            }
            this.showDetail(
                await this.orm.call("edu.training.page", "run_action", [this.kind, d.id, action, value ?? null])
            );
            this.notification.add(message, { type: "success" });
        });
    }

    evaluate() {
        if (this.state.grade === "" || this.gradeError) {
            return;
        }
        const pass = parseFloat(this.state.grade) >= 10;
        const message = this.isProject
            ? pass ? "PAP aprovada." : "PAP reprovada."
            : pass ? "Estágio aprovado." : "Estágio não aprovado.";
        return this.act("evaluate", this.state.grade, message);
    }

    askRemove() {
        this.state.confirmRemove = true;
    }

    cancelRemove() {
        this.state.confirmRemove = false;
    }

    async remove() {
        await this.run(async () => {
            await this.orm.call("edu.training.page", "remove", [this.kind, this.state.detail.id]);
            this.notification.add(this.isProject ? "Trabalho removido." : "Estágio removido.", { type: "success" });
            await this.backToList();
        });
    }

    // Relatórios entregues

    onReport(field, ev) {
        this.state.report[field] = ev.target.value;
    }

    async onReportFile(ev) {
        const file = ev.target.files[0];
        if (!file) {
            this.state.report.file = null;
            return;
        }
        const datas = await new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.readAsDataURL(file);
        });
        this.state.report.file = { name: file.name, datas };
        if (!this.state.report.name.trim()) {
            this.state.report.name = file.name.replace(/\.[^.]+$/, "");
        }
    }

    async addReport() {
        const r = this.state.report;
        if (!r.name.trim()) {
            return;
        }
        await this.run(async () => {
            this.showDetail(
                await this.orm.call("edu.training.page", "add_report", [
                    this.state.detail.id,
                    r.name,
                    r.date || false,
                    r.file,
                ]),
                true
            );
            this.notification.add("Relatório registado.", { type: "success" });
        });
    }

    async removeReport(report) {
        await this.run(async () => {
            this.showDetail(await this.orm.call("edu.training.page", "remove_report", [report.id]), true);
        });
    }

    reportUrl(report) {
        return `/web/content/?model=edu.internship.report&id=${report.id}&field=file&filename_field=file_name&download=true`;
    }
}

registry.category("actions").add("edu_records.training", TrainingPage);
