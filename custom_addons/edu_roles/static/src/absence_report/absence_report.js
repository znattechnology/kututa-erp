import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const plural = (n, one, many) => (n === 1 ? `1 ${one}` : `${n} ${many}`);
const STATUS = {
    ok: "Dentro do limite",
    at_risk: "A uma falta do limite",
    failed: "Atingiu o limite",
};

/**
 * «Relatório de faltas», como no secPed: em cima, os alunos a uma falta do limite ou que já o atingiram nas
 * disciplinas do professor (agrupados por aluno); em baixo, para o director de turma, o mapa da turma inteira, com
 * as faltas injustificadas por disciplina, as justificadas entre parênteses e a regra do limite.
 */
export class AbsenceReportPage extends Component {
    static template = "edu_roles.AbsenceReportPage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.status = STATUS;
        this.state = proxy({ data: null, trimesterId: false, classId: false, loading: false });
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("edu.attendance.page", "absence_report", [
                this.state.trimesterId,
                this.state.classId,
            ]);
            Object.assign(this.state, {
                data,
                trimesterId: data.trimester_id,
                classId: data.board ? data.board.class_id : false,
            });
        } finally {
            this.state.loading = false;
        }
    }

    onTrimester(ev) {
        this.state.trimesterId = parseInt(ev.target.value, 10) || false;
        return this.load();
    }

    onClass(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        return this.load();
    }

    // Nas minhas disciplinas

    get mineSentence() {
        const mine = this.state.data.mine;
        if (!mine.length) {
            return "Nenhum aluno está perto do limite de faltas nas suas disciplinas.";
        }
        const failed = mine.filter((g) => g.worst === "failed").length;
        const risk = mine.length - failed;
        const parts = [
            failed ? `${plural(failed, "aluno já atingiu", "alunos já atingiram")} o limite de faltas` : "",
            risk ? `${plural(risk, "aluno está", "alunos estão")} a uma falta dele` : "",
        ].filter((part) => part);
        let text = `${parts.join(" e ")}.`;
        if (failed) {
            text += " Quem o atinge reprova à disciplina por faltas: avise o encarregado.";
        }
        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    itemText(item) {
        const limit = item.limit ? ` de ${item.limit}` : "";
        const annual = item.annual ? " no ano" : "";
        const excused = item.excused ? ` (e ${plural(item.excused, "justificada", "justificadas")})` : "";
        return `${item.subject}: ${item.counted}${limit}${annual}${excused}`;
    }

    writeToGuardian() {
        return this.action.doAction("mail.action_discuss");
    }

    // A turma que dirijo

    get boardSentence() {
        const board = this.state.data.board;
        const parts = [
            board.failed ? `${plural(board.failed, "aluno atingiu", "alunos atingiram")} o limite` : "",
            board.at_risk ? `${plural(board.at_risk, "aluno está", "alunos estão")} a uma falta dele` : "",
        ].filter((part) => part);
        return parts.length ? `${parts.join("; ")}.` : "Nenhum aluno da turma está perto do limite de faltas.";
    }

    get ruleSentence() {
        return this.state.data.board.regime === "technical"
            ? "No técnico o limite é anual, o triplo dos tempos semanais da disciplina, e passá-lo numa disciplina retém o aluno no ano (Despacho 60/08)."
            : "O limite é por disciplina e por trimestre: 3 faltas com 1 tempo por semana, 4 com 2 tempos, 5 com mais (Decreto Executivo 424/25).";
    }

    cell(student, subject) {
        return student.cells[subject.id] || null;
    }
}

registry.category("actions").add("edu_roles.absence_report", AbsenceReportPage);
