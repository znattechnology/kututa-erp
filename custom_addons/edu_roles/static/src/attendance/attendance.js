import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/** Os botões da chamada, pela ordem do secPed. */
const STATES = [
    { key: "present", label: "Presente" },
    { key: "late", label: "Atraso" },
    { key: "absent", label: "Falta" },
    { key: "excused", label: "Justificada" },
];

const pad = (n) => `${n}`.padStart(2, "0");
const todayKey = () => {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const toTime = (hours) => {
    const minutes = Math.round(hours * 60);
    return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
};
const fromTime = (text) => {
    const [h, m] = (text || "").split(":").map((part) => parseInt(part, 10));
    return Number.isFinite(h) ? h + (m || 0) / 60 : 0;
};

/**
 * «Presenças», como a página do secPed: «Hoje» (as aulas do dia pelo horário, com a chamada a um toque), «Outra
 * aula» (turma e disciplina; o director de turma marca qualquer disciplina da sua turma), as aulas do ano e a
 * chamada. A chamada começa com todos presentes mas só fica registada quando se guarda; com o sumário escrito, a
 * aula fica dada. Mudar de aula com marcações por guardar pede confirmação.
 */
export class AttendancePage extends Component {
    static template = "edu_roles.AttendancePage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.states = STATES;
        this.state = proxy({
            data: null,
            classId: false,
            subjectId: false,
            lessons: null,
            roll: null,
            marks: {},
            initial: {},
            summary: "",
            initialSummary: "",
            query: "",
            busy: false,
            form: null,
        });
        onWillStart(async () => {
            await this.loadOptions();
            const lessonId = (this.props.action.context || {}).attendance_lesson_id;
            if (lessonId) {
                await this.openLesson(lessonId);
            }
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async loadOptions() {
        this.state.data = await this.orm.call("edu.attendance.page", "options", []);
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

    // Marcações por guardar: mudar de aula pergunta antes de fazer o que quer que seja.

    get dirty() {
        const s = this.state;
        if (!s.roll) {
            return false;
        }
        if (s.summary.trim() !== s.initialSummary.trim()) {
            return true;
        }
        return s.roll.rows.some((row) => {
            const now = s.marks[row.enrollment_id];
            const was = s.initial[row.enrollment_id];
            return now.state !== was.state || (now.state === "excused" && now.justification !== was.justification);
        });
    }

    guard(callback) {
        if (!this.dirty) {
            return callback();
        }
        this.dialog.add(ConfirmationDialog, {
            title: "Sair sem guardar a chamada?",
            body: "Tem marcações por guardar nesta aula. Se mudar agora, perde-as.",
            confirmLabel: "Sair sem guardar",
            cancelLabel: "Continuar a chamada",
            confirm: () => callback(),
            cancel: () => {},
        });
    }

    // Hoje

    openToday(row) {
        if (row.lesson_id && this.state.roll && this.state.roll.lesson.id === row.lesson_id) {
            return;
        }
        this.guard(() =>
            this.run(async () => {
                const lesson = await this.orm.call("edu.attendance.page", "open_today", [row.schedule_id]);
                await this.showLesson(lesson.id, lesson.class_id, lesson.subject_id);
            })
        );
    }

    // Por registar: as aulas dos dias anteriores que ainda não estão dadas (falta a chamada ou o sumário).

    openPending(lesson) {
        if (this.state.roll && this.state.roll.lesson.id === lesson.id) {
            return;
        }
        this.guard(() => this.run(() => this.showLesson(lesson.id, lesson.class_id, lesson.subject_id)));
    }

    // Outra aula

    /** As turmas e as disciplinas do professor num só cartão cada uma («Matemática, 10ª A»), para um toque só. */
    get assignments() {
        return this.classes.flatMap((c) =>
            c.subjects.map((s) => ({ key: `${c.id}-${s.id}`, classId: c.id, subjectId: s.id, subject: s.name, class: c.name, asDirector: s.as_director }))
        );
    }

    pickAssignment(item) {
        if (this.state.classId === item.classId && this.state.subjectId === item.subjectId) {
            return;
        }
        this.guard(() =>
            this.run(async () => {
                Object.assign(this.state, { classId: item.classId, subjectId: item.subjectId, roll: null, form: null });
                await this.loadLessons();
            })
        );
    }

    get classes() {
        return this.state.data.classes;
    }

    get currentClass() {
        return this.classes.find((c) => c.id === this.state.classId);
    }

    get subjects() {
        return this.currentClass ? this.currentClass.subjects : [];
    }

    get asDirector() {
        const subject = this.subjects.find((s) => s.id === this.state.subjectId);
        return Boolean(subject && subject.as_director);
    }

    async loadLessons() {
        const s = this.state;
        s.lessons = s.classId && s.subjectId ? await this.orm.call("edu.attendance.page", "lessons", [s.classId, s.subjectId]) : null;
    }

    chooseLesson(lesson) {
        if (this.state.roll && this.state.roll.lesson.id === lesson.id) {
            return;
        }
        this.guard(() => this.run(() => this.showLesson(lesson.id, lesson.class_id, lesson.subject_id)));
    }

    async openLesson(lessonId) {
        const roll = await this.orm.call("edu.attendance.page", "roll", [lessonId]);
        Object.assign(this.state, { classId: roll.lesson.class_id, subjectId: roll.lesson.subject_id });
        await this.loadLessons();
        this.setRoll(roll);
    }

    async showLesson(lessonId, classId, subjectId) {
        const sameList = this.state.classId === classId && this.state.subjectId === subjectId;
        Object.assign(this.state, { classId, subjectId, form: null });
        const roll = await this.orm.call("edu.attendance.page", "roll", [lessonId]);
        if (!sameList || !this.state.lessons || !this.state.lessons.some((l) => l.id === lessonId)) {
            await this.loadLessons();
        }
        this.setRoll(roll);
        // A chamada abre mais abaixo: leva o professor até ela.
        setTimeout(() => document.querySelector(".o_edu_att_roll")?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    }

    setRoll(roll) {
        const marks = {};
        const initial = {};
        for (const row of roll.rows) {
            marks[row.enrollment_id] = { state: row.state, justification: row.justification };
            initial[row.enrollment_id] = { state: row.state, justification: row.justification };
        }
        Object.assign(this.state, {
            roll,
            marks,
            initial,
            summary: roll.lesson.summary,
            initialSummary: roll.lesson.summary,
            query: "",
        });
    }

    // Registar outra aula

    openForm() {
        this.guard(() => {
            this.state.roll = null;
            // O dia do servidor (o fuso do utilizador), o mesmo com que ele valida a aula.
            const today = this.state.data.today_iso || todayKey();
            this.state.form = { date: today, slotId: "", from: "07:00", to: "07:45", summary: "", slots: [] };
            return this.loadSlots();
        });
    }

    async loadSlots() {
        const form = this.state.form;
        form.slots = await this.orm.call("edu.attendance.page", "slots", [this.state.classId, this.state.subjectId, form.date]);
        const first = form.slots[0];
        form.slotId = first ? first.id : "";
        if (first) {
            form.from = toTime(first.hour_from);
            form.to = toTime(first.hour_to);
        }
    }

    onFormDate(ev) {
        this.state.form.date = ev.target.value;
        return this.loadSlots();
    }

    onFormSlot(ev) {
        const form = this.state.form;
        form.slotId = parseInt(ev.target.value, 10) || "";
        const slot = form.slots.find((s) => s.id === form.slotId);
        if (slot) {
            form.from = toTime(slot.hour_from);
            form.to = toTime(slot.hour_to);
        }
    }

    createLesson() {
        const s = this.state;
        const form = s.form;
        return this.run(async () => {
            const lesson = await this.orm.call("edu.attendance.page", "new_lesson", [
                s.classId,
                s.subjectId,
                {
                    date: form.date,
                    schedule_id: form.slotId || false,
                    hour_from: fromTime(form.from),
                    hour_to: fromTime(form.to),
                    summary: form.summary,
                },
            ]);
            if (lesson.existed) {
                this.notification.add("Já havia uma aula desta disciplina nesse dia e hora: abrimos essa.", { type: "info" });
            }
            s.form = null;
            await this.loadLessons();
            await this.showLesson(lesson.id, lesson.class_id, lesson.subject_id);
        });
    }

    // A chamada

    get counts() {
        const counts = { present: 0, late: 0, absent: 0, excused: 0 };
        for (const row of this.state.roll.rows) {
            counts[this.state.marks[row.enrollment_id].state]++;
        }
        return counts;
    }

    /** As partes da barra da chamada (presentes, atrasos, justificadas e faltas), pela ordem da marcação. */
    get countBar() {
        const c = this.counts;
        return ["present", "late", "excused", "absent"].filter((key) => c[key]).map((key) => ({ key, count: c[key] }));
    }

    get countSentence() {
        const total = this.state.roll.rows.length;
        const c = this.counts;
        if (c.present === total) {
            return `Os ${total} alunos estão presentes.`;
        }
        const parts = [
            c.absent ? `${c.absent} ${c.absent === 1 ? "falta" : "faltas"}` : "",
            c.late ? `${c.late} ${c.late === 1 ? "atraso" : "atrasos"}` : "",
            c.excused ? `${c.excused} ${c.excused === 1 ? "justificada" : "justificadas"}` : "",
        ].filter((part) => part);
        return `${c.present} de ${total} presentes` + (parts.length ? `; ${parts.join(", ")}` : "") + ".";
    }

    get visibleRows() {
        const term = this.state.query.trim().toLowerCase();
        const rows = this.state.roll.rows;
        return term ? rows.filter((row) => row.name.toLowerCase().includes(term)) : rows;
    }

    get readonly() {
        const roll = this.state.roll;
        return roll.closed || roll.future || roll.lesson.state === "cancelled";
    }

    mark(row, key) {
        if (this.readonly || (key === "excused" && !row.can_justify)) {
            return;
        }
        this.state.marks[row.enrollment_id].state = key;
    }

    stateTitle(row, key) {
        if (key === "excused" && !row.can_justify) {
            return "Só o director de turma e a secretaria justificam faltas: marque «Falta».";
        }
        return "";
    }

    allPresent() {
        for (const row of this.state.roll.rows) {
            const mark = this.state.marks[row.enrollment_id];
            // Uma falta justificada pelo director não se desfaz por engano.
            if (mark.state !== "excused" || row.can_justify) {
                mark.state = "present";
            }
        }
    }

    get footer() {
        const roll = this.state.roll;
        if (this.readonly) {
            if (roll.closed) {
                return { text: roll.reason, warn: false };
            }
            if (roll.future) {
                return { text: "A aula ainda não aconteceu: a chamada faz-se no próprio dia.", warn: false };
            }
            return { text: "A aula não se realizou.", warn: false };
        }
        if (!roll.saved) {
            return { text: "A chamada desta aula ainda não foi guardada.", warn: true };
        }
        if (this.dirty) {
            return { text: "Tem alterações por guardar.", warn: true };
        }
        if (roll.lesson.state !== "done") {
            return { text: "Chamada guardada. Escreva o sumário para a aula contar como dada.", warn: false };
        }
        return { text: `Chamada guardada. Aula n.º ${roll.lesson.number}, dada.`, warn: false };
    }

    get canSave() {
        return !this.readonly && (!this.state.roll.saved || this.dirty) && !this.state.busy;
    }

    save() {
        const s = this.state;
        return this.run(async () => {
            const rows = s.roll.rows.map((row) => ({ enrollment_id: row.enrollment_id, ...s.marks[row.enrollment_id] }));
            const result = await this.orm.call("edu.attendance.page", "save", [s.roll.lesson.id, rows, s.summary]);
            this.setRoll(result);
            let message = "Chamada guardada.";
            if (result.done) {
                message += ` A aula ficou dada (n.º ${result.lesson.number}).`;
            }
            this.notification.add(message, { type: "success" });
            await Promise.all([this.loadLessons(), this.loadOptions()]);
        });
    }
}

registry.category("actions").add("edu_roles.attendance", AttendancePage);
