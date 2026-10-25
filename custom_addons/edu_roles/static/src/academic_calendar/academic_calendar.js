import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MONTHS = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]; // prettier-ignore
const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
/** Os tipos pela ordem da legenda; a cor de cada um vem do SCSS (o_edu_ca_t_<tipo>). */
export const TYPES = [
    { key: "exam", label: "Provas e exames" },
    { key: "trimester_start", label: "Início de trimestre" },
    { key: "trimester_end", label: "Fim de trimestre" },
    { key: "holiday", label: "Feriado ou pausa" },
    { key: "meeting", label: "Reunião" },
    { key: "activity", label: "Actividade" },
    { key: "other", label: "Outro" },
];

const pad = (n) => `${n}`.padStart(2, "0");
const keyOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fromKey = (key) => {
    const [y, m, d] = key.split("-").map((part) => parseInt(part, 10));
    return new Date(y, m - 1, d);
};
const shortDay = (key) => {
    const d = fromKey(key);
    return `${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3).toLowerCase()}`;
};

/**
 * «Calendário académico», como no secPed: o mês (a semana começa à segunda; o domingo é o dia sem aulas), o dia
 * escolhido e os próximos eventos. As datas comemorativas do calendário nacional (há aulas) vão em texto simples,
 * sem a cor de um exame ou de um feriado, e podem esconder-se. Um evento de vários dias aparece em todos os dias e
 * conta como próximo enquanto não acabar.
 */
export class AcademicCalendarPage extends Component {
    static template = "edu_roles.AcademicCalendarPage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.weekdays = WEEKDAYS;
        this.types = TYPES;
        const today = new Date();
        this.today = keyOf(today);
        this.state = proxy({
            data: null,
            month: new Date(today.getFullYear(), today.getMonth(), 1),
            selected: this.today,
            commemorative: this.showCommemorative,
            filter: null,
        });
        onWillStart(async () => {
            this.state.data = await this.loadData();
        });
    }

    // O que muda de área para área (o encarregado junta as provas dos educandos): os dados, o título e os filtros.

    loadData() {
        return this.orm.call("edu.teacher.home", "calendar_data", []);
    }

    /** As datas comemorativas à vista por omissão. */
    get showCommemorative() {
        return true;
    }

    get subtitle() {
        return "Os eventos, as provas e os prazos da escola.";
    }

    /** Os botões por cima do mês ([{key, label}]), por exemplo os educandos; ``null`` sem filtros. */
    get filters() {
        return null;
    }

    /** Se um evento passa no filtro escolhido. */
    matchesFilter(event) {
        return true;
    }

    setFilter(key) {
        this.state.filter = key;
    }

    get display() {
        return { controlPanel: {} };
    }

    get monthTitle() {
        return `${MONTHS[this.state.month.getMonth()]} de ${this.state.month.getFullYear()}`;
    }

    get visible() {
        const events = this.state.data.events.filter((e) => this.matchesFilter(e));
        return this.state.commemorative ? events : events.filter((e) => !e.commemorative);
    }

    get hasCommemorative() {
        return this.state.data.events.some((e) => e.commemorative);
    }

    eventsOn(key) {
        return this.visible.filter((e) => e.start <= key && key <= e.end);
    }

    /** Seis semanas, de segunda a domingo, com os dias dos meses vizinhos a completar. */
    get cells() {
        const month = this.state.month;
        const first = new Date(month.getFullYear(), month.getMonth(), 1);
        const offset = (first.getDay() + 6) % 7;
        return Array.from({ length: 42 }, (_, i) => {
            const date = new Date(month.getFullYear(), month.getMonth(), 1 - offset + i);
            const key = keyOf(date);
            const inMonth = date.getMonth() === month.getMonth();
            const events = inMonth ? this.eventsOn(key) : [];
            return {
                key,
                day: date.getDate(),
                inMonth,
                sunday: date.getDay() === 0,
                today: key === this.today,
                selected: key === this.state.selected,
                events: events.slice(0, 3),
                more: Math.max(0, events.length - 3),
                label:
                    `${date.getDate()} de ${MONTHS[date.getMonth()]}${key === this.today ? ", hoje" : ""}` +
                    (events.length ? `, ${events.length} ${events.length === 1 ? "evento" : "eventos"}` : ""),
            };
        });
    }

    get selectedTitle() {
        const d = fromKey(this.state.selected);
        return `${d.getDate()} de ${MONTHS[d.getMonth()]}`;
    }

    get selectedEvents() {
        return this.eventsOn(this.state.selected);
    }

    /** Os que ainda não acabaram (um de vários dias já começado também conta). */
    get upcoming() {
        return this.visible.filter((e) => e.end >= this.today).slice(0, 8);
    }

    // Quanto falta

    /** Os dias de hoje até ``key`` (negativo se já passou). */
    daysUntil(key) {
        return Math.round((fromKey(key) - fromKey(this.today)) / 86400000);
    }

    /** Quanto falta para um evento: «A decorrer», «Hoje», «Amanhã», «Daqui a N dias» (ou semanas). */
    whenLabel(event) {
        if (event.start <= this.today && this.today <= event.end) {
            return event.start === event.end ? "Hoje" : `A decorrer até ${shortDay(event.end)}`;
        }
        const days = this.daysUntil(event.start);
        if (days === 1) {
            return "Amanhã";
        }
        return days < 21 ? `Daqui a ${days} dias` : `Daqui a ${Math.round(days / 7)} semanas`;
    }

    /** O trimestre em curso (do início e do fim no calendário): a semana, os dias que faltam e o tempo passado. */
    get trimester() {
        const events = this.state.data.events;
        const ends = Object.fromEntries(events.filter((e) => e.type === "trimester_end").map((e) => [e.id.replace("trimester_end", ""), e]));
        const terms = events
            .filter((e) => e.type === "trimester_start" && ends[e.id.replace("trimester_start", "")])
            .map((e) => ({ name: e.name.replace(/^Início do /, ""), start: e.start, end: ends[e.id.replace("trimester_start", "")].start }));
        const current = terms.find((t) => t.start <= this.today && this.today <= t.end);
        if (current) {
            const total = this.daysUntil(current.end) - this.daysUntil(current.start) + 1;
            const passed = -this.daysUntil(current.start) + 1;
            return {
                ...current,
                current: true,
                left: this.daysUntil(current.end),
                week: Math.floor((passed - 1) / 7) + 1,
                weeks: Math.ceil(total / 7),
                width: Math.min(100, (100 * passed) / total),
            };
        }
        const next = terms.find((t) => t.start > this.today);
        return next ? { ...next, current: false, until: this.daysUntil(next.start) } : null;
    }

    /** O próximo evento (ou o que está a decorrer) de um dos tipos, no filtro escolhido. */
    nextOf(types) {
        return (
            this.state.data.events.find(
                (e) => types.includes(e.type) && !e.commemorative && e.end >= this.today && this.matchesFilter(e)
            ) || null
        );
    }

    /** Os tipos que contam como provas no cartão de cima (o encarregado junta as provas dos educandos). */
    get examTypes() {
        return ["exam"];
    }

    /** Os números de cima: o trimestre, a próxima pausa ou feriado, as próximas provas e a próxima reunião. */
    get overview() {
        return [
            { key: "holiday", label: "Próxima pausa ou feriado", event: this.nextOf(["holiday"]), empty: "Nenhuma marcada" },
            { key: "exam", label: "Próximas provas", event: this.nextOf(this.examTypes), empty: "Nenhuma marcada" },
            { key: "meeting", label: "Próxima reunião", event: this.nextOf(["meeting"]), empty: "Nenhuma marcada" },
        ];
    }

    typeLabel(event) {
        if (event.commemorative) {
            return "Data comemorativa";
        }
        if (event.type_label) {
            return event.type_label;
        }
        return (TYPES.find((t) => t.key === event.type) || TYPES[TYPES.length - 1]).label;
    }

    /** O tipo a meio da frase: só a primeira letra em minúscula («prova de Ana», não «prova de ana»). */
    typeLabelInline(event) {
        const label = this.typeLabel(event);
        return label.charAt(0).toLowerCase() + label.slice(1);
    }

    span(event) {
        return event.end !== event.start ? `de ${shortDay(event.start)} a ${shortDay(event.end)}` : shortDay(event.start);
    }

    typeClass(event) {
        return event.commemorative ? "o_edu_ca_t_commemorative" : `o_edu_ca_t_${event.type}`;
    }

    // Navegação

    choose(key) {
        const d = fromKey(key);
        this.state.selected = key;
        this.state.month = new Date(d.getFullYear(), d.getMonth(), 1);
    }

    shift(months) {
        const month = this.state.month;
        this.state.month = new Date(month.getFullYear(), month.getMonth() + months, 1);
    }

    goToday() {
        this.choose(this.today);
    }

    toggleCommemorative(ev) {
        this.state.commemorative = ev.target.checked;
    }
}

registry.category("actions").add("edu_roles.academic_calendar", AcademicCalendarPage);
