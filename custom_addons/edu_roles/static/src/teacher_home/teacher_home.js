import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * O Painel do Professor, como um quadro: em cima os números principais (a carga semanal, as aulas por registar, as
 * notas lançadas no trimestre e os alunos em risco por faltas); depois o dia (com a chamada a um toque), as notas do
 * trimestre em cada turma e disciplina (positivas, negativas e sem nota) e as turmas; ao lado, as presenças nas suas
 * aulas, as vigilâncias e os atalhos.
 */
export class TeacherHome extends Component {
    static template = "edu_roles.TeacherHome";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, busy: false });
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        this.state.data = await this.orm.call("edu.teacher.home", "home_data", []);
    }

    get greeting() {
        const hour = new Date().getHours();
        const word = hour < 12 ? "Bom dia" : hour < 19 ? "Boa tarde" : "Boa noite";
        return `${word}, ${(this.state.data.name || "").split(" ")[0]}`;
    }

    get headline() {
        const d = this.state.data;
        const lessons = d.lessons.length;
        const classes = d.classes.length;
        const directs = d.classes.filter((c) => c.directs).length;
        const parts = [];
        if (!d.lessons_day) {
            parts.push(lessons ? `${lessons} ${lessons === 1 ? "aula" : "aulas"} hoje` : "sem aulas hoje");
        }
        parts.push(`${classes} ${classes === 1 ? "turma" : "turmas"} este ano`);
        if (directs) {
            parts.push(`director(a) de ${directs === 1 ? "uma turma" : `${directs} turmas`}`);
        }
        return parts.join(", ") + ".";
    }

    get overLoad() {
        const load = this.state.data.dashboard.load;
        return load.limit && load.count > load.limit;
    }

    get loadWidth() {
        const load = this.state.data.dashboard.load;
        return load.limit ? Math.min(100, (load.count / load.limit) * 100) : 0;
    }

    get gradedPercent() {
        const db = this.state.data.dashboard;
        return db.expected ? Math.round((100 * db.graded) / db.expected) : 0;
    }

    stateLabel(lesson) {
        return { scheduled: "Por dar", done: "Dada", cancelled: "Não se realizou" }[lesson.state] || lesson.state;
    }

    stateClass(lesson) {
        return { done: "text-bg-success", cancelled: "text-bg-secondary" }[lesson.state] || "text-bg-light";
    }

    async openLesson(lesson) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const action = await this.orm.call("edu.teacher.home", "open_lesson", [lesson.schedule_id, lesson.date]);
            await this.action.doAction(action, { onClose: () => this.load() });
        } finally {
            this.state.busy = false;
        }
    }

    openGrades(edu_class) {
        return this.action.doAction("edu_evaluation.action_edu_grade_grid", {
            additionalContext: { default_class_id: edu_class.id },
        });
    }

    openCouncil(edu_class) {
        return this.action.doAction("edu_evaluation.action_edu_council_board", {
            additionalContext: { default_class_id: edu_class.id },
        });
    }

    openAction(xmlid) {
        return this.action.doAction(xmlid);
    }

}

registry.category("actions").add("edu_roles.teacher_home", TeacherHome);
