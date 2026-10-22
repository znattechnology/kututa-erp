import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const LAST_PERIOD_KEY = "edu_exam.exam_planner.period";

function remember(value) {
    try {
        window.localStorage.setItem(LAST_PERIOD_KEY, String(value));
    } catch {
        // Sem armazenamento (janela privada): abre na primeira época.
    }
}

function remembered() {
    try {
        return parseInt(window.localStorage.getItem(LAST_PERIOD_KEY), 10) || false;
    } catch {
        return false;
    }
}

export function fmtHour(value) {
    const minutes = Math.round((value || 0) * 60);
    return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

function parseHour(text) {
    const [h, m] = (text || "").split(":").map(Number);
    return (h || 0) + (m || 0) / 60;
}

/** «quarta-feira, 9 de dezembro» → «Quarta-feira, 9 de Dezembro». */
export function fmtDay(day) {
    const text = new Date(`${day}T00:00:00`).toLocaleDateString("pt-PT", {
        weekday: "long",
        day: "numeric",
        month: "long",
    });
    return text
        .replace(/^./, (c) => c.toUpperCase())
        .replace(/ de ([a-zç]+)$/, (_, month) => ` de ${month[0].toUpperCase()}${month.slice(1)}`);
}

function fmtShort(day) {
    return new Date(`${day}T00:00:00`).toLocaleDateString("pt-PT", { day: "numeric", month: "short" });
}

function overlaps(a, b) {
    return a.date === b.date && a.from < b.to && b.from < a.to;
}

/**
 * Calendário de provas, como o do secPed-Express. Uma época (as datas) e, dentro dela, as provas de cada turma com a
 * sala e o vigilante, vistas de três maneiras:
 *  - por sessão: as turmas que fazem prova à mesma hora; o vigilante escolhe-se na linha (quem já vigia outra turma
 *    a essa hora aparece, mas não se escolhe) e «Distribuir vigilantes» preenche as que faltam;
 *  - por turma: o calendário de provas da turma, para imprimir e afixar;
 *  - vigilâncias por professor: quem vigia quanto e a escala de cada um.
 * «Marcar prova em várias turmas» cria a mesma prova (disciplina, dia e horas) em todas as turmas escolhidas, cada uma
 * na sua sala. O servidor volta a verificar os choques de sala, vigilante e aluno ao gravar.
 */
export class ExamPlanner extends Component {
    static template = "edu_exam.ExamPlanner";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = proxy({
            options: { periods: [], proposals: [], year: false, can_print: false },
            periodId: false,
            mode: "session",
            data: null,
            showProposals: false,
            marking: null,
            classId: false,
            teacherId: false,
            open: {},
            busy: false,
        });
        onWillStart(async () => {
            await this.loadOptions();
            const wanted = remembered();
            const periods = this.state.options.periods;
            const period = periods.find((p) => p.id === wanted) || periods[periods.length - 1];
            if (period) {
                await this.selectPeriod(period.id);
            }
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    // Dados

    async loadOptions() {
        this.state.options = await this.orm.call("edu.exam.period", "planner_options", []);
    }

    async load() {
        this.state.data = this.state.periodId
            ? await this.orm.call("edu.exam.period", "planner_data", [[this.state.periodId]])
            : null;
    }

    async selectPeriod(periodId) {
        this.state.periodId = periodId;
        this.state.marking = null;
        this.state.classId = false;
        this.state.teacherId = false;
        this.state.open = {};
        remember(periodId);
        await this.load();
    }

    async run(fn) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            return await fn();
        } finally {
            this.state.busy = false;
        }
    }

    // Épocas

    get period() {
        return this.state.data?.period;
    }

    get proposalsCount() {
        return this.state.options.proposals.length;
    }

    fmtShort(day) {
        return fmtShort(day);
    }

    async createFromEvent(eventId) {
        await this.run(async () => {
            const periodId = await this.orm.call("edu.exam.period", "planner_create_from_event", [eventId]);
            this.state.showProposals = false;
            await this.loadOptions();
            await this.selectPeriod(periodId);
        });
    }

    async openPeriodForm(periodId = false) {
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "edu.exam.period",
                res_id: periodId || undefined,
                views: [[false, "form"]],
                target: "new",
                context: { form_view_initial_mode: "edit" },
            },
            {
                onClose: async () => {
                    await this.loadOptions();
                    const periods = this.state.options.periods;
                    const keep = periods.find((p) => p.id === this.state.periodId);
                    const last = periods[periods.length - 1];
                    if (keep || last) {
                        await this.selectPeriod(keep ? keep.id : last.id);
                    }
                },
            }
        );
    }

    async setMode(mode) {
        this.state.mode = mode;
        this.state.marking = null;
    }

    // Provas

    get sessions() {
        return this.state.data?.sessions || [];
    }

    get classById() {
        return new Map((this.state.data?.classes || []).map((c) => [c.id, c]));
    }

    /** Vigilâncias de cada professor na época. */
    get supervisionCounts() {
        const counts = new Map();
        for (const session of this.sessions) {
            for (const teacher of session.supervisors) {
                counts.set(teacher.id, (counts.get(teacher.id) || 0) + 1);
            }
        }
        return counts;
    }

    incomplete(session) {
        return !session.room_id || session.supervisors.length === 0;
    }

    /** As sessões: as provas com o mesmo dia e as mesmas horas. */
    get groups() {
        const groups = new Map();
        for (const session of this.sessions) {
            const key = `${session.date}|${session.from}|${session.to}`;
            if (!groups.has(key)) {
                groups.set(key, { key, date: session.date, from: session.from, to: session.to, sessions: [] });
            }
            groups.get(key).sessions.push(session);
        }
        const list = [...groups.values()];
        for (const group of list) {
            group.sessions.sort((a, b) => a.class.localeCompare(b.class, "pt", { numeric: true }));
            group.missing = group.sessions.filter((s) => s.supervisors.length === 0).length;
            group.subjects = [...new Set(group.sessions.map((s) => s.subject))].join(", ");
        }
        return list.sort((a, b) => a.date.localeCompare(b.date) || a.from - b.from || a.to - b.to);
    }

    isOpen(group) {
        return this.state.open[group.key] ?? group.missing > 0;
    }

    toggle(group) {
        this.state.open[group.key] = !this.isOpen(group);
    }

    get allOpen() {
        const groups = this.groups;
        return groups.length > 0 && groups.every((g) => this.isOpen(g));
    }

    toggleAll() {
        const value = !this.allOpen;
        this.state.open = Object.fromEntries(this.groups.map((g) => [g.key, value]));
    }

    /** Onde o professor já vigia à hora da prova (outra turma desta época ou outra época), ou false. */
    occupiedAt(teacherId, session) {
        for (const other of this.sessions) {
            if (other.id !== session.id && overlaps(other, session) && other.supervisors.some((t) => t.id === teacherId)) {
                return other.class;
            }
        }
        const elsewhere = (this.state.data?.elsewhere || []).find(
            (e) => e.teacher_id === teacherId && overlaps(e, session)
        );
        return elsewhere ? elsewhere.label : false;
    }

    teacherOptions(session) {
        const load = this.supervisionCounts;
        const current = session.supervisors[0]?.id;
        return (this.state.data?.teachers || []).map((teacher) => {
            const where = teacher.id === current ? false : this.occupiedAt(teacher.id, session);
            const count = load.get(teacher.id);
            return {
                id: teacher.id,
                label: where ? `${teacher.name} — vigia ${where}` : count ? `${teacher.name} (${count})` : teacher.name,
                disabled: !!where,
            };
        });
    }

    replaceSession(updated) {
        const index = this.state.data.sessions.findIndex((s) => s.id === updated.id);
        if (index >= 0) {
            this.state.data.sessions[index] = updated;
        }
    }

    async onSupervisorChange(session, ev) {
        const teacherId = parseInt(ev.target.value, 10) || false;
        await this.run(async () => {
            try {
                const updated = await this.orm.call("edu.exam.period", "planner_set_supervisor", [
                    session.id,
                    teacherId,
                ]);
                this.replaceSession(updated);
            } catch (error) {
                await this.load();
                throw error;
            }
        });
    }

    async onRoomChange(session, ev) {
        const roomId = parseInt(ev.target.value, 10) || false;
        await this.run(async () => {
            try {
                const updated = await this.orm.call("edu.exam.period", "planner_set_room", [session.id, roomId]);
                this.replaceSession(updated);
            } catch (error) {
                await this.load();
                throw error;
            }
        });
    }

    removeSession(session) {
        this.dialog.add(ConfirmationDialog, {
            title: `Remover a prova de ${session.subject}?`,
            body: `${fmtDay(session.date)}, das ${fmtHour(session.from)} às ${fmtHour(session.to)}, ${session.class}. A sala e o vigilante desta prova saem com ela.`,
            confirmLabel: "Remover a prova",
            confirm: async () => {
                await this.orm.call("edu.exam.period", "planner_remove", [session.id]);
                await this.load();
            },
            cancel: () => {},
        });
    }

    async distribute(group) {
        await this.run(async () => {
            const result = await this.orm.call("edu.exam.period", "planner_distribute", [
                [this.state.periodId],
                group.date,
                group.from,
                group.to,
            ]);
            await this.load();
            const parts = [];
            if (result.assigned) {
                parts.push(`${result.assigned} ${result.assigned === 1 ? "vigilante atribuído" : "vigilantes atribuídos"}`);
            }
            if (result.without) {
                parts.push(`${result.without} sem professor livre`);
            }
            if (result.no_room) {
                parts.push(`${result.no_room} sem sala (escolha a sala primeiro)`);
            }
            this.notification.add(parts.join("; ") || "Não havia turmas sem vigilante.", {
                type: result.without || result.no_room ? "warning" : "success",
            });
        });
    }

    async summon(group) {
        await this.run(async () => {
            const added = await this.orm.call("edu.exam.period", "planner_summon", [
                [this.state.periodId],
                group.date,
                group.from,
                group.to,
            ]);
            await this.load();
            this.notification.add(
                added ? `${added} ${added === 1 ? "aluno convocado" : "alunos convocados"}.` : "Não havia alunos por convocar.",
                { type: "success" }
            );
        });
    }

    async openSession(session) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "edu.exam.session",
            res_id: session.id,
            views: [[false, "form"]],
        });
    }

    // Marcar prova em várias turmas

    startMarking(classId = false) {
        const period = this.period;
        const preset = classId ? this.classById.get(classId) : null;
        this.state.marking = {
            classNumber: preset ? preset.number : "",
            subjectId: false,
            date: period.date_start,
            from: "08:00",
            to: "10:00",
            selected: preset ? [preset.id] : [],
            fixedClass: classId,
        };
    }

    get classNumbers() {
        return [...new Set((this.state.data?.classes || []).map((c) => c.number))].sort((a, b) => a - b);
    }

    get markingClasses() {
        const marking = this.state.marking;
        if (!marking) {
            return [];
        }
        return (this.state.data?.classes || []).filter(
            (c) => marking.classNumber === "" || c.number === marking.classNumber
        );
    }

    hasExam(classId, subjectId) {
        return this.sessions.some((s) => s.class_ids.includes(classId) && s.subject_id === subjectId);
    }

    markingRow(edu_class) {
        const marking = this.state.marking;
        const inPlan = !marking.subjectId || edu_class.subject_ids.includes(marking.subjectId);
        const room = (this.state.data?.rooms || []).find((r) => r.id === edu_class.room_id);
        return {
            inPlan,
            already: marking.subjectId && this.hasExam(edu_class.id, marking.subjectId),
            room: room ? room.name : false,
            checked: marking.selected.includes(edu_class.id),
        };
    }

    onMarkingNumber(ev) {
        this.state.marking.classNumber = ev.target.value === "" ? "" : parseInt(ev.target.value, 10);
        this.preselect();
    }

    onMarkingSubject(ev) {
        this.state.marking.subjectId = parseInt(ev.target.value, 10) || false;
        this.preselect();
    }

    /** As turmas com a disciplina no plano e ainda sem prova dela ficam escolhidas por omissão. */
    preselect() {
        const marking = this.state.marking;
        if (marking.fixedClass || !marking.subjectId) {
            return;
        }
        marking.selected = this.markingClasses
            .filter((c) => c.subject_ids.includes(marking.subjectId) && !this.hasExam(c.id, marking.subjectId))
            .map((c) => c.id);
    }

    toggleMarkingClass(classId) {
        const selected = this.state.marking.selected;
        const index = selected.indexOf(classId);
        if (index >= 0) {
            selected.splice(index, 1);
        } else {
            selected.push(classId);
        }
    }

    get markingSubjects() {
        const marking = this.state.marking;
        const subjects = this.state.data?.subjects || [];
        if (marking?.fixedClass) {
            const edu_class = this.classById.get(marking.fixedClass);
            return subjects.filter((s) => edu_class.subject_ids.includes(s.id));
        }
        return subjects;
    }

    async submitMarking() {
        const marking = this.state.marking;
        const visible = new Set(this.markingClasses.map((c) => c.id));
        const classIds = marking.selected.filter((id) => visible.has(id));
        if (!marking.subjectId) {
            this.notification.add("Escolha a disciplina.", { type: "warning" });
            return;
        }
        if (!classIds.length) {
            this.notification.add("Escolha pelo menos uma turma.", { type: "warning" });
            return;
        }
        await this.run(async () => {
            const result = await this.orm.call("edu.exam.period", "planner_mark", [
                [this.state.periodId],
                marking.subjectId,
                marking.date,
                parseHour(marking.from),
                parseHour(marking.to),
                classIds,
            ]);
            await this.load();
            if (result.created) {
                this.notification.add(
                    `Prova marcada em ${result.created} ${result.created === 1 ? "turma" : "turmas"}.`,
                    { type: "success" }
                );
            }
            if (result.failures.length) {
                this.notification.add(result.failures.join(" · "), { type: "danger", sticky: true });
            } else {
                this.state.marking = null;
            }
        });
    }

    // Por turma

    get classSummary() {
        const summary = new Map();
        for (const session of this.sessions) {
            for (const classId of session.class_ids) {
                const item = summary.get(classId) || { exams: 0, incomplete: 0 };
                item.exams++;
                if (this.incomplete(session)) {
                    item.incomplete++;
                }
                summary.set(classId, item);
            }
        }
        return summary;
    }

    get classesWithExams() {
        return (this.state.data?.classes || []).filter((c) => this.classSummary.has(c.id)).length;
    }

    get incompleteCount() {
        return this.sessions.filter((s) => this.incomplete(s)).length;
    }

    onClassChange(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        this.state.marking = null;
    }

    openClass(classId) {
        this.state.classId = classId;
    }

    /** Linhas de uma lista de provas, com o dia só na primeira prova desse dia. */
    rows(sessions) {
        const sorted = [...sessions].sort((a, b) => a.date.localeCompare(b.date) || a.from - b.from);
        return sorted.map((session, index) => ({
            session,
            firstOfDay: index === 0 || sorted[index - 1].date !== session.date,
            newDay: index > 0 && sorted[index - 1].date !== session.date,
        }));
    }

    get classSessions() {
        return this.sessions.filter((s) => s.class_ids.includes(this.state.classId));
    }

    get selectedClass() {
        return this.classById.get(this.state.classId);
    }

    // Por professor

    get teacherLoads() {
        const byTeacher = new Map();
        for (const session of this.sessions) {
            for (const teacher of session.supervisors) {
                if (!byTeacher.has(teacher.id)) {
                    byTeacher.set(teacher.id, []);
                }
                byTeacher.get(teacher.id).push(session);
            }
        }
        return (this.state.data?.teachers || [])
            .map((teacher) => {
                const sessions = (byTeacher.get(teacher.id) || []).sort(
                    (a, b) => a.date.localeCompare(b.date) || a.from - b.from
                );
                return {
                    id: teacher.id,
                    name: teacher.name,
                    sessions,
                    days: new Set(sessions.map((s) => s.date)).size,
                    summary: sessions.map((s) => `${fmtShort(s.date)} ${fmtHour(s.from)} · ${s.class}`).join("; "),
                };
            })
            .sort((a, b) => b.sessions.length - a.sessions.length || a.name.localeCompare(b.name, "pt"));
    }

    get selectedTeacher() {
        return this.teacherLoads.find((t) => t.id === this.state.teacherId);
    }

    get supervisionsTotal() {
        return this.sessions.reduce((n, s) => n + s.supervisors.length, 0);
    }

    get teachersWithSupervision() {
        return this.teacherLoads.filter((t) => t.sessions.length).length;
    }

    get withoutSupervisor() {
        return this.sessions.filter((s) => s.supervisors.length === 0).length;
    }

    onTeacherChange(ev) {
        this.state.teacherId = parseInt(ev.target.value, 10) || false;
    }

    openTeacher(teacherId) {
        this.state.teacherId = teacherId;
    }

    // Impressão

    async print(kind) {
        const resId = kind === "class" ? this.state.classId : this.state.teacherId;
        const action = await this.orm.call("edu.exam.period", "planner_print", [[this.state.periodId], kind, resId]);
        await this.action.doAction(action);
    }

    // Formatação no modelo

    fmtHour(value) {
        return fmtHour(value);
    }

    fmtDay(day) {
        return fmtDay(day);
    }

    plural(count, one, many) {
        return `${count} ${count === 1 ? one : many}`;
    }
}

registry.category("actions").add("edu_exam.exam_planner", ExamPlanner);
