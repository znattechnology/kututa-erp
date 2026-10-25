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

    /**
     * O que pede atenção, antes de tudo (como nos painéis do aluno e do encarregado): as aulas por registar, os alunos
     * no limite de faltas, as notas em falta com os dias até ao fim do trimestre e a vigilância de hoje ou amanhã.
     */
    get warnings() {
        const d = this.state.data;
        const db = d.dashboard;
        const plural = (n, one, many) => (n === 1 ? one : `${n} ${many}`);
        const items = [];
        if (db.pending_lessons) {
            items.push({
                key: "lessons",
                icon: "fact_check",
                text: `${plural(db.pending_lessons, "Uma aula", "aulas")} sem chamada ou sumário`,
                action: "edu_roles.action_teacher_attendance",
                bad: db.pending_lessons > 3,
            });
        }
        if (db.failed || db.at_risk) {
            const parts = [];
            if (db.failed) {
                parts.push(`${plural(db.failed, "um aluno passou", "alunos passaram")} o limite de faltas`);
            }
            if (db.at_risk) {
                parts.push(`${plural(db.at_risk, "um está", "estão")} a uma falta dele`);
            }
            const text = parts.join(" e ");
            items.push({
                key: "absences",
                icon: "person_off",
                text: text[0].toUpperCase() + text.slice(1),
                action: "edu_roles.action_teacher_absence_report",
                bad: Boolean(db.failed),
            });
        }
        const missing = db.expected - db.graded;
        if (db.expected && missing > 0 && db.trimester_days !== null && db.trimester_days <= 21) {
            const left = db.trimester_days <= 0 ? "o trimestre acaba hoje" : `faltam ${plural(db.trimester_days, "um dia", "dias")} para o fim do ${db.trimester}`;
            items.push({
                key: "grades",
                icon: "edit_document",
                text: `${plural(missing, "Uma classificação", "classificações")} por lançar: ${left}`,
                action: "edu_evaluation.action_edu_grade_grid",
                bad: db.trimester_days <= 7,
            });
        }
        const soon = d.supervisions.find((s) => s.days <= 1);
        if (soon) {
            items.push({
                key: "supervision",
                icon: "visibility",
                text: [`Vigilância ${soon.days <= 0 ? "hoje" : "amanhã"}: ${soon.subject}`, soon.hours, soon.rooms]
                    .filter(Boolean)
                    .join(", "),
                action: "edu_roles.action_teacher_supervisions",
            });
        }
        return items;
    }

    get shortcuts() {
        return [
            { action: "edu_roles.action_teacher_schedule", icon: "calendar_today", label: "Meu horário" },
            { action: "edu_roles.action_teacher_attendance", icon: "fact_check", label: "Presenças" },
            { action: "edu_roles.action_teacher_absence_report", icon: "check_circle", label: "Relatório de faltas" },
            { action: "edu_evaluation.action_edu_grade_grid", icon: "edit_document", label: "Lançar notas" },
            { action: "mail.action_discuss", icon: "forum", label: "Mensagens" },
            { action: "edu_roles.action_teacher_profile_page", icon: "person", label: "Meu perfil" },
        ];
    }

    /** Quanto falta para uma vigilância. */
    whenLabel(days) {
        return days <= 0 ? "Hoje" : days === 1 ? "Amanhã" : `Daqui a ${days} dias`;
    }

    /** «Agora» na aula a decorrer e «A seguir» na próxima de hoje (pela hora do browser). */
    get lessonTags() {
        const d = this.state.data;
        const tags = {};
        if (d.lessons_day) {
            return tags;
        }
        const now = new Date();
        const minutes = now.getHours() * 60 + now.getMinutes();
        const toMin = (text) => {
            const [h, m] = text.split(":").map(Number);
            return h * 60 + m;
        };
        let next = null;
        for (const l of d.lessons) {
            const [from, to] = l.hours.split("–").map(toMin);
            const key = l.schedule_id + "-" + l.date;
            if (minutes >= from && minutes < to) {
                tags[key] = "now";
            } else if (from > minutes && !next) {
                next = key;
            }
        }
        if (next) {
            tags[next] = "next";
        }
        return tags;
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

    get rdecPercent() {
        const db = this.state.data.dashboard;
        return db.rdec_total ? Math.round((100 * db.rdec_done) / db.rdec_total) : 0;
    }

    async openRdec(classId) {
        const action = await this.orm.call("edu.grade.grid", "class_link_action", [classId, "rdec"]);
        return this.action.doAction(action);
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
