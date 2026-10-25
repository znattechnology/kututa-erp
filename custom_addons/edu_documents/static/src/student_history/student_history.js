import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { StudentPanel } from "../student_panel/student_panel";

/**
 * «Histórico do aluno», como a página do secPed-Express, no formato da mini-pauta: à esquerda o ano lectivo, as
 * turmas (por curso) e os alunos da turma, ou a pesquisa pelo nome; à direita o percurso do aluno na escola, um ano
 * lectivo por linha, do primeiro ao último: a turma, a média final, a assiduidade e o resultado do conselho; o ano em
 * curso e as saídas também. Daqui imprime-se o termo de cada ano e o do curso (com pré-visualização).
 */
export class StudentHistory extends Component {
    static template = "edu_documents.StudentHistory";
    static components = { Layout, StudentPanel };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = proxy({ studentId: false, data: null, busy: false, editing: null, status: "", reason: "" });
        onWillStart(async () => {
            const studentId = (this.props.action.context || {}).default_student_id;
            if (studentId) {
                await this.load(studentId);
            }
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    // Aluno

    async load(studentId) {
        this.state.studentId = studentId;
        this.state.editing = null;
        const data = await this.orm.call("edu.history.page", "student_history", [studentId]);
        // Escolheu outro aluno entretanto: esta resposta já não serve.
        if (this.state.studentId === studentId) {
            this.state.data = data;
        }
    }

    choose(row) {
        return this.load(row.student_id);
    }

    /** Os números do percurso: anos na escola, média dos anos com média e os resultados. */
    get stats() {
        const rows = this.state.data ? this.state.data.rows : [];
        const averages = rows.map((r) => r.average).filter((a) => a !== null && a !== undefined);
        const count = (tones) => rows.filter((r) => r.year_result_id && tones.includes(r.tone)).length;
        return {
            years: new Set(rows.map((r) => r.year)).size,
            average: averages.length ? averages.reduce((a, b) => a + b, 0) / averages.length : null,
            passed: count(["pos"]),
            failed: count(["neg"]),
        };
    }

    // Decisão da direcção

    decisionOptions(row) {
        const options = row.terminal
            ? [{ key: "graduated", label: "Concluiu o curso" }]
            : [
                  { key: "promoted", label: "Transita" },
                  { key: "conditional", label: "Transita com disciplinas em atraso" },
              ];
        return [...options, { key: "retained", label: "Não transita" }];
    }

    startDecision(row) {
        this.state.editing = row.enrollment_id;
        this.state.status = row.status && this.decisionOptions(row).some((o) => o.key === row.status) ? row.status : "";
        this.state.reason = "";
    }

    cancelDecision() {
        this.state.editing = null;
    }

    onStatus(ev) {
        this.state.status = ev.target.value;
    }

    onReason(ev) {
        this.state.reason = ev.target.value;
    }

    async saveDecision(row) {
        if (!this.state.status || !this.state.reason.trim() || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.data = await this.orm.call("edu.history.page", "decide", [
                row.year_result_id,
                this.state.status,
                this.state.reason,
            ]);
            this.state.editing = null;
            this.notification.add("Decisão alterada.", { type: "success" });
        } finally {
            this.state.busy = false;
        }
    }

    resetDecision(row) {
        if (this.state.busy) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: "Voltar à decisão automática",
            body: `A decisão de ${row.year} volta a ser a das regras, com as notas do ano.`,
            confirmLabel: "Voltar à automática",
            cancelLabel: "Cancelar",
            confirm: async () => {
                this.state.busy = true;
                try {
                    this.state.data = await this.orm.call("edu.history.page", "reset_decision", [row.year_result_id]);
                    this.notification.add("Decisão automática reposta.", { type: "success" });
                } finally {
                    this.state.busy = false;
                }
            },
            cancel: () => {},
        });
    }

    // Apresentação

    fmtAverage(value) {
        return value === null || value === undefined ? "—" : String(Math.round(value * 10) / 10).replace(".", ",");
    }

    fmtRate(value) {
        return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
    }

    averageClass(value) {
        if (value === null || value === undefined) {
            return "text-muted";
        }
        return value >= 10 ? "text-success" : "text-danger";
    }

    badgeClass(tone) {
        return {
            pos: "text-bg-success",
            neg: "text-bg-danger",
            warn: "text-bg-warning",
            current: "text-bg-info",
            muted: "text-bg-light",
        }[tone];
    }

    // Impressão

    async run(method, args) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const action = await this.orm.call("edu.history.page", method, args);
            await this.action.doAction(action);
        } finally {
            this.state.busy = false;
        }
    }

    printYear(row) {
        return this.run("print_year_term", [row.year_result_id]);
    }

    printCourse() {
        return this.run("print_course_term", [this.state.studentId]);
    }

    subjects() {
        return this.run("subject_history", [this.state.studentId]);
    }
}

registry.category("actions").add("edu_documents.student_history", StudentHistory);
