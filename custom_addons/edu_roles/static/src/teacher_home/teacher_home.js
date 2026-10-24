import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * O Painel do Professor, como o do secPed-Express: primeiro o dia (as aulas de hoje pelo horário, ou as do próximo
 * dia de aulas, com a chamada a um toque), depois as turmas deste ano com a direcção de turma assinalada, e ao lado
 * as próximas vigilâncias e os atalhos.
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
