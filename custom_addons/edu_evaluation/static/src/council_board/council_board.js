import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const LAST_CLASS_KEY = "edu_evaluation.council_board.class";

function remember(value) {
    try {
        window.localStorage.setItem(LAST_CLASS_KEY, String(value));
    } catch {
        // Sem armazenamento: abre sem turma.
    }
}

function remembered() {
    try {
        return parseInt(window.localStorage.getItem(LAST_CLASS_KEY), 10) || false;
    } catch {
        return false;
    }
}

function fmt(value) {
    return value === undefined || value === null ? "—" : String(Math.round(value));
}

/**
 * Conselho de turma, como no secPed-Express: a grelha da turma (alunos × disciplinas) com a nota final a cores — verde
 * aprova, vermelho negativa, âmbar caso limite que se vota —, os cartões das votações abertas (a favor, contra,
 * apurar, quórum no técnico) e o encerramento. Até o director iniciar o conselho, os professores esperam. O servidor
 * verifica cada acção (quem pode abrir, votar, apurar, subir pontos).
 */
export class CouncilBoard extends Component {
    static template = "edu_evaluation.CouncilBoard";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = proxy({ classes: [], classId: false, data: null, busy: false, selected: null });
        onWillStart(async () => {
            this.state.classes = await this.orm.call("edu.council.session", "board_classes", []);
            const context = this.props.action.context || {};
            const wanted = context.default_class_id || remembered();
            const pick =
                this.state.classes.find((c) => c.id === wanted) || this.state.classes.find((c) => c.directs);
            if (pick) {
                await this.openClass(pick.id);
            }
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async openClass(classId) {
        this.state.classId = classId;
        this.state.selected = null;
        remember(classId);
        this.state.data = await this.orm.call("edu.council.session", "board_for_class", [classId]);
    }

    async onClassChange(ev) {
        const classId = parseInt(ev.target.value, 10) || false;
        if (classId) {
            await this.openClass(classId);
        } else {
            this.state.classId = false;
            this.state.data = null;
        }
    }

    get session() {
        return this.state.data?.session;
    }

    async call(method, args = []) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await this.orm.call("edu.council.session", method, [[this.session.id], ...args]);
            if (result && result.data) {
                this.state.data = result.data;
                if (result.message) {
                    this.notification.add(result.message, { type: "info" });
                }
            } else if (result) {
                this.state.data = result;
            }
        } finally {
            this.state.busy = false;
        }
    }

    // Grelha

    cellClass(cell) {
        if (!cell.result_id || !cell.complete) {
            return "text-muted";
        }
        if (cell.borderline) {
            return "text-warning fw-bold o_edu_cb_votable";
        }
        return cell.passed ? "text-success" : "text-danger fw-bold";
    }

    cellText(cell) {
        if (!cell.result_id || !cell.complete) {
            return "—";
        }
        return fmt(cell.final);
    }

    subjectName(subjectId) {
        return this.state.data.subjects.find((s) => s.id === subjectId)?.name || "";
    }

    /** Um caso limite escolhido na grelha: o painel por cima da grelha mostra o que se pode fazer com ele. */
    onCell(student, cell) {
        if (!cell.borderline || this.session.state !== "open") {
            return;
        }
        this.state.selected = { student, cell, subject: this.subjectName(cell.subject_id) };
    }

    get selectedActions() {
        const selected = this.state.selected;
        if (!selected) {
            return [];
        }
        const actions = [];
        if (selected.cell.can_teach) {
            actions.push({ key: "grant", label: "Subir +2 (professor da disciplina)", primary: !this.state.data.is_director });
        }
        if (this.state.data.is_director && !selected.cell.vote_id) {
            actions.push({ key: "vote", label: "Abrir votação do conselho", primary: true });
        }
        return actions;
    }

    async runSelected(key) {
        const cell = this.state.selected.cell;
        this.state.selected = null;
        await this.call(key === "grant" ? "board_grant" : "board_open_vote", [cell.result_id]);
    }

    fmt(value) {
        return fmt(value);
    }

    removePoints(student, cell) {
        this.dialog.add(ConfirmationDialog, {
            title: "Retirar a bonificação?",
            body: `${student.name} · ${this.subjectName(cell.subject_id)}: a nota volta a ${fmt(cell.base)}.`,
            confirmLabel: "Retirar",
            confirm: () => this.call("board_remove_points", [cell.result_id]),
            cancel: () => {},
        });
    }

    // Votações

    vote(vote, inFavor) {
        return this.call("board_cast", [vote.id, inFavor]);
    }

    closeVote(vote) {
        return this.call("board_close_vote", [vote.id]);
    }

    start() {
        return this.call("board_start");
    }

    realize() {
        this.dialog.add(ConfirmationDialog, {
            title: "Encerrar o conselho?",
            body: "Encerrado o conselho, a pauta fecha e calculam-se as decisões de transição. Depois só a direcção o reabre.",
            confirmLabel: "Encerrar o conselho",
            confirm: () => this.call("board_realize"),
            cancel: () => {},
        });
    }

    async print(method) {
        const action = await this.orm.call("edu.council.session", method, [[this.session.id]]);
        await this.action.doAction(action);
    }

    get counts() {
        const counts = { positives: 0, negatives: 0, borderline: 0 };
        for (const student of this.state.data?.students || []) {
            for (const cell of student.cells) {
                if (!cell.result_id || !cell.complete) {
                    continue;
                }
                if (cell.borderline) {
                    counts.borderline++;
                } else if (cell.passed) {
                    counts.positives++;
                } else {
                    counts.negatives++;
                }
            }
        }
        return counts;
    }
}

registry.category("actions").add("edu_evaluation.council_board", CouncilBoard);
