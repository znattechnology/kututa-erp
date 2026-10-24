import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const pad = (n) => `${n}`.padStart(2, "0");
const hhmm = (minutes) => `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;

/**
 * «Vigilâncias», como as «Provas» do professor no secPed: uma frase diz quantas provas tem a vigiar e qual é a
 * próxima; depois, uma tabela por época (o I e o II trimestre não se misturam) com o dia, a hora, a disciplina, a
 * turma e a sala, e «Imprimir» dá a escala de vigilância da época. No telemóvel, uma lista por dia.
 */
export class TeacherSupervisionsPage extends Component {
    static template = "edu_roles.TeacherSupervisionsPage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.hhmm = hhmm;
        this.state = proxy({ data: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("edu.teacher.home", "supervisions_data", []);
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get rows() {
        return this.state.data.periods.flatMap((p) => p.rows);
    }

    /** Hoje no relógio do aparelho (não em UTC) e os minutos desde a meia-noite. */
    get now() {
        const d = new Date();
        return {
            date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
            minutes: d.getHours() * 60 + d.getMinutes(),
        };
    }

    isPast(row) {
        const now = this.now;
        return row.date < now.date || (row.date === now.date && row.end <= now.minutes);
    }

    get summary() {
        const rows = this.rows;
        const days = new Set(rows.map((r) => r.date)).size;
        let text = `${rows.length} ${rows.length === 1 ? "prova" : "provas"} em ${days} ${days === 1 ? "dia" : "dias"} a vigiar.`;
        const next = rows.find((r) => !this.isPast(r));
        if (!next) {
            return `${text} Já não há provas por vigiar.`;
        }
        const when = next.date === this.now.date ? "hoje" : next.day.replace(/^./, (c) => c.toLowerCase());
        text += ` A próxima: ${when}, às ${hhmm(next.start)}, ${next.subject}`;
        if (next.classes) {
            text += ` na ${next.classes}`;
        }
        return `${text}${next.rooms ? `, ${next.rooms}` : ""}.`;
    }

    /** A primeira prova de cada dia leva o dia (as seguintes ficam por baixo, sem o repetir). */
    firstOfDay(period, index) {
        return index === 0 || period.rows[index - 1].date !== period.rows[index].date;
    }

    hasPartners(period) {
        return period.rows.some((r) => r.partners);
    }

    /** Os dias da época, para a lista do telemóvel. */
    days(period) {
        const days = [];
        for (const row of period.rows) {
            if (!days.length || days[days.length - 1].date !== row.date) {
                days.push({ date: row.date, day: row.day, rows: [] });
            }
            days[days.length - 1].rows.push(row);
        }
        return days;
    }

    async print(period) {
        const action = await this.orm.call("edu.teacher.home", "supervisions_report", [period.id]);
        return this.action.doAction(action);
    }
}

registry.category("actions").add("edu_roles.teacher_supervisions", TeacherSupervisionsPage);
