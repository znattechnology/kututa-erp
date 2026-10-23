import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { StudentPicker } from "../student_picker/student_picker";

/**
 * «Histórico do aluno», como a página do secPed-Express: escolhe-se o aluno (pela turma ou pelo nome) e vê-se o
 * percurso na escola, um ano lectivo por linha, do primeiro ao último: a turma, a média final, a assiduidade e o
 * resultado do conselho; o ano em curso e as saídas também. Daqui imprime-se o termo de cada ano e o do curso.
 */
export class StudentHistory extends Component {
    static template = "edu_documents.StudentHistory";
    static components = { Layout, StudentPicker };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
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

    async load(studentId) {
        this.state.studentId = studentId;
        this.state.data = await this.orm.call("edu.history.page", "student_history", [studentId]);
    }

    choose(row) {
        return this.load(row.student_id);
    }

    otherStudent() {
        this.state.studentId = false;
        this.state.data = null;
        this.state.editing = null;
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

    async resetDecision(row) {
        if (this.state.busy || !window.confirm("Voltar à decisão automática (a das regras, com as notas do ano)?")) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.data = await this.orm.call("edu.history.page", "reset_decision", [row.year_result_id]);
            this.notification.add("Decisão automática reposta.", { type: "success" });
        } finally {
            this.state.busy = false;
        }
    }

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
        return value >= 10 ? "text-primary" : "text-danger";
    }

    toneClass(tone) {
        return {
            pos: "text-primary",
            neg: "text-danger",
            warn: "text-warning",
            current: "fw-semibold",
            muted: "text-muted",
        }[tone];
    }

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
