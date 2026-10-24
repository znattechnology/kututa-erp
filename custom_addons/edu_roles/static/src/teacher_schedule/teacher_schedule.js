import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const DAYS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"];
/** Uma linha da grelha por quarto de hora: um tempo de 45 minutos ocupa três. */
const SLOT = 15;

const pad = (n) => `${n}`.padStart(2, "0");
const hhmm = (minutes) => `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;

/** O agora no relógio do professor, com a semana a começar à segunda (0), como os dias do horário. */
function clock() {
    const d = new Date();
    return {
        day: (d.getDay() + 6) % 7,
        minutes: d.getHours() * 60 + d.getMinutes(),
        date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    };
}

/**
 * «O meu horário», como a página do secPed: «A seguir» responde à pergunta com que o professor abre a página (a
 * aula a decorrer ou a próxima, com a chamada a um toque no próprio dia), o resumo diz a carga em linguagem simples
 * e a grelha mostra a semana toda (no telemóvel, uma lista por dia). «Visualizar» e «Exportar» dão a folha A4.
 */
export class TeacherSchedulePage extends Component {
    static template = "edu_roles.TeacherSchedulePage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.days = DAYS;
        this.hhmm = hhmm;
        this.state = proxy({ data: null, now: clock(), busy: false });
        onWillStart(async () => {
            this.state.data = await this.orm.call("edu.teacher.home", "schedule_data", []);
        });
        const timer = setInterval(() => (this.state.now = clock()), 60000);
        onWillUnmount(() => clearInterval(timer));
    }

    get display() {
        return { controlPanel: {} };
    }

    get lessons() {
        return this.state.data.lessons;
    }

    // A seguir

    /** A aula a decorrer ou a próxima da semana, dando a volta (sábado à tarde → segunda). */
    get next() {
        const now = this.state.now;
        const current = this.lessons.find((l) => l.weekday === now.day && l.start <= now.minutes && now.minutes < l.end);
        if (current) {
            return { now: true, lesson: current, left: current.end - now.minutes, today: true };
        }
        // Até ao mesmo dia da semana seguinte (quem só tem aulas num dia vê a da próxima semana).
        for (let ahead = 0; ahead <= 7; ahead++) {
            const day = (now.day + ahead) % 7;
            const lesson = this.lessons
                .filter((l) => l.weekday === day && (ahead > 0 || l.start > now.minutes))
                .sort((a, b) => a.start - b.start)[0];
            if (lesson) {
                return { now: false, lesson, ahead, minutes: ahead * 1440 + lesson.start - now.minutes, today: ahead === 0 };
            }
        }
        return null;
    }

    get nextWhen() {
        const next = this.next;
        const lesson = next.lesson;
        if (next.now) {
            return `A decorrer: termina às ${hhmm(lesson.end)} (faltam ${next.left} min)`;
        }
        if (next.ahead === 0) {
            return next.minutes < 60 ? `Hoje, daqui a ${next.minutes} min` : `Hoje às ${hhmm(lesson.start)}`;
        }
        if (next.ahead === 1) {
            return `Amanhã às ${hhmm(lesson.start)}`;
        }
        return `${DAYS[lesson.weekday]} às ${hhmm(lesson.start)}`;
    }

    lessonDetail(lesson) {
        return [lesson.class, lesson.room].filter((part) => part).join(", ");
    }

    async takeRollCall(lesson) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            // O dia do servidor (o fuso do utilizador), o mesmo com que ele valida a aula.
            const action = await this.orm.call("edu.teacher.home", "open_lesson", [lesson.id, this.state.data.today]);
            await this.action.doAction(action);
        } finally {
            this.state.busy = false;
        }
    }

    openClass(lesson) {
        return this.action.doAction("edu_evaluation.action_edu_grade_grid", {
            additionalContext: { default_class_id: lesson.class_id, default_subject_id: lesson.subject_id },
        });
    }

    // A semana

    get summary() {
        const count = this.lessons.length;
        const days = new Set(this.lessons.map((l) => l.weekday)).size;
        const lessons = count === 1 ? "1 aula" : `${count} aulas`;
        return `${lessons} por semana, em ${days} ${days === 1 ? "dia" : "dias"}.`;
    }

    get load() {
        const load = this.state.data.load;
        if (!load) {
            return null;
        }
        return {
            text: `${load.count} de ${load.limit} tempos`,
            over: load.count > load.limit,
            notes: load.notes.join(", "),
        };
    }

    /** Segunda a sexta; o sábado só se houver aulas nele. */
    get weekDays() {
        const last = this.lessons.some((l) => l.weekday === 5) ? 6 : 5;
        return Array.from({ length: last }, (_, i) => i);
    }

    lessonsOn(day) {
        return this.lessons.filter((l) => l.weekday === day);
    }

    /** Da hora certa antes da primeira aula à hora certa depois da última; sem aulas, a manhã. */
    get grid() {
        const start = this.lessons.length ? Math.floor(Math.min(...this.lessons.map((l) => l.start)) / 60) * 60 : 7 * 60;
        const end = this.lessons.length ? Math.ceil(Math.max(...this.lessons.map((l) => l.end)) / 60) * 60 : 12 * 60;
        const rows = Math.max(1, (end - start) / SLOT);
        return {
            start,
            rows: Array.from({ length: rows }, (_, i) => {
                const minutes = start + i * SLOT;
                return { index: i, minutes, label: minutes % 60 === 0 ? hhmm(minutes) : "", hour: minutes % 60 === 0 };
            }),
            style: `grid-template-columns: 4.5rem repeat(${this.weekDays.length}, minmax(0, 1fr)); grid-template-rows: auto repeat(${rows}, 1.15rem);`,
        };
    }

    cellStyle(column, row) {
        return `grid-column: ${column}; grid-row: ${row + 2};`;
    }

    blockStyle(lesson) {
        const start = this.grid.start;
        const row = Math.round((lesson.start - start) / SLOT) + 2;
        const span = Math.max(1, Math.round((lesson.end - lesson.start) / SLOT));
        return `grid-column: ${lesson.weekday + 2}; grid-row: ${row} / span ${span};`;
    }

    blockTitle(lesson) {
        const detail = this.lessonDetail(lesson);
        return `${lesson.subject}, ${hhmm(lesson.start)}–${hhmm(lesson.end)}${detail ? `, ${detail}` : ""}`;
    }

    // Visualizar e exportar

    async openReport(preview) {
        const action = await this.orm.call("edu.teacher.home", "schedule_report", [preview]);
        return this.action.doAction(action);
    }
}

registry.category("actions").add("edu_roles.teacher_schedule", TeacherSchedulePage);
