import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const LAST_CLASS_KEY = "edu_timetable.schedule_editor.class";

function remember(value) {
    try {
        window.localStorage.setItem(LAST_CLASS_KEY, String(value));
    } catch {
        // Sem armazenamento (janela privada): o editor abre sem turma.
    }
}

function remembered() {
    try {
        return parseInt(window.localStorage.getItem(LAST_CLASS_KEY), 10) || false;
    } catch {
        return false;
    }
}

function overlaps(a, b) {
    return a.day === b.day && a.from < b.to && b.from < a.to;
}

/**
 * Editor de horários, como o do secPed-Express: as disciplinas da turma à esquerda («2/3» tempos colocados face
 * ao plano, e o professor) e a grelha da semana à direita. Escolhe-se a disciplina (clique) ou arrasta-se para uma
 * célula livre; as aulas arrastam-se para outra célula. Com uma disciplina na mão, as células onde o professor ou a
 * sala já estão noutra turma ficam bloqueadas e dizem porquê. O servidor volta a verificar tudo ao gravar.
 */
export class ScheduleEditor extends Component {
    static template = "edu_timetable.ScheduleEditor";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            mode: "class",
            options: { classes: [], teachers: [], trimesters: [], year: false },
            classId: false,
            teacherId: false,
            trimesterId: false,
            saturday: false,
            data: null,
            selectedSubjectId: false,
            // O que se está a arrastar: {subjectId} da lista ou {lessonId} da grelha.
            drag: null,
            dropTarget: null,
            busy: false,
        });
        onWillStart(async () => {
            this.state.options = await this.orm.call("edu.schedule", "editor_options", []);
            const context = this.props.action.context || {};
            const wanted = context.default_class_id || remembered();
            if (wanted && this.state.options.classes.some((c) => c.id === wanted)) {
                this.state.classId = wanted;
                await this.load();
            }
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    // Dados

    async load() {
        const { mode, classId, teacherId, trimesterId } = this.state;
        if (mode === "class" && classId) {
            this.state.data = await this.orm.call("edu.schedule", "editor_class_data", [classId, trimesterId]);
        } else if (mode === "teacher" && teacherId) {
            this.state.data = await this.orm.call("edu.schedule", "editor_teacher_data", [teacherId, trimesterId]);
        } else {
            this.state.data = null;
        }
        if (this.state.data && !this.state.data.subjects?.some((s) => s.id === this.state.selectedSubjectId)) {
            this.state.selectedSubjectId = false;
        }
    }

    async setMode(mode) {
        this.state.mode = mode;
        this.state.selectedSubjectId = false;
        await this.load();
    }

    async onClassChange(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        this.state.selectedSubjectId = false;
        if (this.state.classId) {
            remember(this.state.classId);
        }
        await this.load();
    }

    async onTeacherChange(ev) {
        this.state.teacherId = parseInt(ev.target.value, 10) || false;
        await this.load();
    }

    async onTrimesterChange(ev) {
        this.state.trimesterId = parseInt(ev.target.value, 10) || false;
        await this.load();
    }

    async openClass(classId) {
        this.state.mode = "class";
        this.state.classId = classId;
        remember(classId);
        await this.load();
    }

    async print() {
        const action = await this.orm.call("edu.class", "action_print_schedule", [[this.state.classId]]);
        await this.action.doAction(action);
    }

    // Grelha

    get days() {
        const days = this.state.data?.days || [];
        if (this.state.mode === "class" && this.state.saturday && !days.some((d) => d.code === 5)) {
            return [...days, { code: 5, name: "Sábado" }];
        }
        return days;
    }

    get rows() {
        const data = this.state.data;
        return (data?.periods || []).map((period) => ({
            ...period,
            cells: this.days.map((day) => {
                const slot = { day: day.code, from: period.from, to: period.to };
                const lesson = data.lessons.find((l) => overlaps(l, slot));
                return {
                    key: `${day.code}-${period.from}-${period.to}`,
                    slot,
                    lesson,
                    // A aula ocupa a célula onde começa; nas seguintes não se repete.
                    first: lesson && lesson.from === period.from,
                    clash: lesson ? false : this.clashAt(slot),
                };
            }),
        }));
    }

    get subjects() {
        return this.state.data?.subjects || [];
    }

    get selectedSubject() {
        return this.subjects.find((s) => s.id === this.state.selectedSubjectId);
    }

    /** O que está «na mão»: a disciplina arrastada ou escolhida, ou a aula arrastada. */
    get holding() {
        const drag = this.state.drag;
        if (drag?.lessonId) {
            const lesson = this.state.data.lessons.find((l) => l.id === drag.lessonId);
            return lesson && { teacherId: lesson.teacher_id, lessonId: lesson.id };
        }
        const subject = this.subjects.find((s) => s.id === (drag?.subjectId || this.state.selectedSubjectId));
        return subject && { teacherId: subject.teacher_id };
    }

    /** Porque não se pode pôr aqui o que está na mão (o professor ou a sala noutra turma), ou false. */
    clashAt(slot) {
        const holding = this.holding;
        const data = this.state.data;
        if (!holding || this.state.mode !== "class") {
            return false;
        }
        const teacherBusy = (data.teacher_busy[holding.teacherId] || []).find((b) => overlaps(b, slot));
        if (teacherBusy) {
            return `Professor(a) ocupado(a): ${teacherBusy.label}`;
        }
        const roomBusy = data.room_busy.find((b) => overlaps(b, slot));
        if (roomBusy) {
            return `Sala ocupada: ${roomBusy.label}`;
        }
        return false;
    }

    get summary() {
        const subjects = this.subjects;
        const planned = subjects.reduce((n, s) => n + s.planned, 0);
        const placed = subjects.reduce((n, s) => n + Math.min(s.placed, s.planned), 0);
        const missing = subjects.filter((s) => s.planned > s.placed).map((s) => `${s.name} ${s.planned - s.placed}`);
        const extra = subjects.filter((s) => s.placed > s.planned).map((s) => `${s.name} +${s.placed - s.planned}`);
        const withoutTeacher = subjects.filter((s) => !s.teacher_id).length;
        return { planned, placed, missing, extra, withoutTeacher };
    }

    /** Por baixo da disciplina: o professor e a sala na turma; a turma e a sala no horário do professor. */
    lessonDetail(lesson) {
        const who = this.state.mode === "class" ? lesson.teacher || "Sem professor" : lesson.class;
        return [who, lesson.room].filter(Boolean).join(", ");
    }

    subjectState(subject) {
        if (!subject.planned) {
            return "text-muted";
        }
        if (subject.placed === subject.planned) {
            return "text-success";
        }
        return subject.placed > subject.planned ? "text-warning" : "text-muted";
    }

    toggleSubject(subject) {
        this.state.selectedSubjectId = this.state.selectedSubjectId === subject.id ? false : subject.id;
    }

    // Arrastar e largar

    onDragSubject(ev, subject) {
        this.state.drag = { subjectId: subject.id };
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", subject.name);
    }

    onDragLesson(ev, lesson) {
        this.state.drag = { lessonId: lesson.id };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", lesson.subject);
    }

    onDragEnd() {
        this.state.drag = null;
        this.state.dropTarget = null;
    }

    onDragOver(ev, cell) {
        if (!this.state.drag || cell.lesson || cell.clash) {
            return;
        }
        ev.preventDefault();
        this.state.dropTarget = cell.key;
    }

    async onDrop(ev, cell) {
        ev.preventDefault();
        const drag = this.state.drag;
        this.onDragEnd();
        if (!drag || cell.lesson || cell.clash) {
            return;
        }
        if (drag.lessonId) {
            await this.save(() =>
                this.orm.call("edu.schedule", "editor_move", [[drag.lessonId], cell.slot.day, cell.slot.from, cell.slot.to])
            );
        } else {
            await this.place(drag.subjectId, cell);
        }
    }

    async onClickCell(cell) {
        if (cell.lesson || this.state.mode !== "class") {
            return;
        }
        if (!this.state.selectedSubjectId) {
            this.notification.add("Escolha primeiro uma disciplina na lista à esquerda, ou arraste-a para a grelha.", {
                type: "info",
            });
            return;
        }
        if (cell.clash) {
            this.notification.add(cell.clash, { type: "warning" });
            return;
        }
        await this.place(this.state.selectedSubjectId, cell);
    }

    async place(subjectId, cell) {
        await this.save(() =>
            this.orm.call(
                "edu.schedule",
                "editor_place",
                [this.state.classId, subjectId, cell.slot.day, cell.slot.from, cell.slot.to],
                { trimester_id: this.state.trimesterId }
            )
        );
    }

    async remove(lesson) {
        await this.save(() => this.orm.unlink("edu.schedule", [lesson.id]));
    }

    async save(write) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await write();
            if (result?.warning) {
                this.notification.add(result.warning, { type: "warning", title: "Carga horária excedida" });
            }
        } catch (error) {
            // Choque que o servidor encontrou (por exemplo, outra pessoa colocou a aula entretanto).
            this.notification.add(error.data?.message || error.message, { type: "danger" });
        } finally {
            this.state.busy = false;
            await this.load();
        }
    }
}

registry.category("actions").add("edu_timetable.schedule_editor", ScheduleEditor);
