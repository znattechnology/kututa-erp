import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/** Um número à portuguesa: 12,5; «—» quando não há. */
function fmt(value, digits = 0) {
    if (value === null || value === undefined) {
        return "—";
    }
    return value.toLocaleString("pt-PT", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function pct(value) {
    return value === null || value === undefined ? "—" : `${fmt(value, 1)}%`;
}

// O gráfico dos trimestres (SVG): margens e tamanho do desenho.
const CHART = { width: 560, height: 220, left: 36, right: 120, top: 16, bottom: 30 };

/**
 * «Análise de dados»: os números da escola de vários anos lectivos lado a lado, para a direcção e a secretaria. Por
 * cima, os filtros (anos, curso, classe e turno), que valem para os três separadores: o resumo de cada ano, o percurso
 * dos alunos que entraram num ano e o aproveitamento. Cada barra abre a lista dos alunos que conta.
 */
export class AnalyticsDashboard extends Component {
    static template = "edu_analytics.Dashboard";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.fmt = fmt;
        this.pct = pct;
        this.chart = CHART;
        this.state = proxy({
            options: null,
            filters: {
                year_ids: [],
                course_id: false,
                class_number: "",
                shift_id: false,
                cohort_year_id: false,
                class_year_id: false,
                detail_year_id: false,
                capacity_year_id: false,
            },
            tab: "summary",
            data: null,
            loading: false,
        });
        onWillStart(async () => {
            const options = await this.orm.call("edu.analytics", "options", []);
            this.state.options = options;
            this.state.filters.year_ids = options.years.map((y) => y.id);
            await this.load();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        // Uma resposta antiga (filtros mudados entretanto) não se sobrepõe à mais recente.
        const request = (this.request = (this.request || 0) + 1);
        this.state.loading = true;
        try {
            const data = await this.orm.call("edu.analytics", "dashboard", [this.filters]);
            if (request === this.request) {
                this.state.data = data;
            }
        } finally {
            if (request === this.request) {
                this.state.loading = false;
            }
        }
    }

    /** Os filtros como o servidor os quer (a classe vazia é «todas»). */
    get filters() {
        const f = this.state.filters;
        return { ...f, year_ids: [...f.year_ids], class_number: f.class_number === "" ? false : f.class_number };
    }

    // Filtros

    toggleYear(yearId) {
        const ids = this.state.filters.year_ids;
        if (ids.includes(yearId)) {
            if (ids.length === 1) {
                return;
            }
            this.state.filters.year_ids = ids.filter((id) => id !== yearId);
        } else {
            const order = this.state.options.years.map((y) => y.id);
            this.state.filters.year_ids = order.filter((id) => id === yearId || ids.includes(id));
        }
        this.load();
    }

    allYears() {
        this.state.filters.year_ids = this.state.options.years.map((y) => y.id);
        this.load();
    }

    onFilter(key, ev) {
        const value = ev.target.value;
        this.state.filters[key] = value === "" ? (key === "class_number" ? "" : false) : parseInt(value, 10);
        this.load();
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    get hasFilters() {
        const f = this.state.filters;
        return Boolean(f.course_id || f.class_number !== "" || f.shift_id);
    }

    clearFilters() {
        Object.assign(this.state.filters, { course_id: false, class_number: "", shift_id: false });
        this.load();
    }

    // Os alunos de cada número

    async students(kind, params) {
        const action = await this.orm.call("edu.analytics", "students", [this.filters, kind, params]);
        return this.action.doAction(action);
    }

    // Resumo

    get summary() {
        return this.state.data ? this.state.data.summary : [];
    }

    /** O último ano escolhido e o anterior; o último com resultados e o anterior (para a transição e a média). */
    get kpis() {
        const all = this.summary;
        const closed = all.filter((s) => s.decided);
        const last = all[all.length - 1];
        const prev = all[all.length - 2];
        const lastClosed = closed[closed.length - 1];
        const prevClosed = closed[closed.length - 2];
        const delta = (a, b, key, digits = 1) => {
            if (!a || !b || a[key] === null || b[key] === null) {
                return null;
            }
            const d = a[key] - b[key];
            const same = Math.abs(d) < (digits ? 0.05 : 0.5);
            return { value: same ? 0 : d, same, text: `${d > 0 ? "+" : ""}${fmt(d, digits)}`, year: b.year };
        };
        return [
            {
                key: "enrolled",
                label: "Matrículas",
                value: last ? fmt(last.enrolled) : "—",
                year: last && last.year,
                detail: last ? `${fmt(last.types.new)} novas, ${fmt(last.classes)} turmas` : "",
                delta: delta(last, prev, "enrolled", 0),
                worseUp: null,
            },
            {
                key: "transition",
                label: "Taxa de transição",
                value: lastClosed ? pct(lastClosed.transition) : "—",
                year: lastClosed && lastClosed.year,
                detail: lastClosed ? `${fmt(lastClosed.outcomes.conditional)} com disciplinas em atraso` : "Ainda sem resultados",
                delta: delta(lastClosed, prevClosed, "transition"),
                worseUp: false,
                unit: " pp",
            },
            {
                key: "retention",
                label: "Taxa de reprovação",
                value: lastClosed ? pct(lastClosed.retention) : "—",
                year: lastClosed && lastClosed.year,
                detail: lastClosed ? `${fmt(lastClosed.outcomes.retained)} de ${fmt(lastClosed.decided)} avaliados` : "",
                delta: delta(lastClosed, prevClosed, "retention"),
                worseUp: true,
                unit: " pp",
            },
            {
                key: "average",
                label: "Média final",
                value: lastClosed ? fmt(lastClosed.average, 1) : "—",
                year: lastClosed && lastClosed.year,
                detail: "Escala de 0 a 20",
                delta: delta(lastClosed, prevClosed, "average"),
                worseUp: false,
                unit: "",
            },
        ];
    }

    deltaClass(k) {
        if (!k.delta || k.worseUp === null || Math.abs(k.delta.value) < 0.05) {
            return "text-muted";
        }
        return k.delta.value > 0 === k.worseUp ? "text-danger" : "text-success";
    }

    /** As matrículas de cada ano em colunas empilhadas pelo tipo (a coluna mais alta vai ao topo). */
    get enrollColumns() {
        const max = Math.max(1, ...this.summary.map((s) => s.enrolled));
        const types = this.state.options.types;
        return this.summary.map((s) => ({
            ...s,
            height: (100 * s.enrolled) / max,
            parts: types
                .filter((t) => s.types[t.key])
                .map((t) => ({ ...t, count: s.types[t.key], share: (100 * s.types[t.key]) / Math.max(1, s.enrolled) })),
        }));
    }

    /** O resultado de cada ano: uma barra (100% das matrículas) com um segmento por resultado. */
    get outcomeRows() {
        const outcomes = this.state.options.outcomes;
        return this.summary.map((s) => ({
            ...s,
            parts: outcomes
                .filter((o) => s.outcomes[o.key])
                .map((o) => ({ ...o, count: s.outcomes[o.key], width: (100 * s.outcomes[o.key]) / Math.max(1, s.enrolled) })),
        }));
    }

    get usedOutcomes() {
        return this.state.options.outcomes.filter((o) => this.summary.some((s) => s.outcomes[o.key]));
    }

    // Percurso dos alunos

    get cohort() {
        return this.state.data && this.state.data.cohort;
    }

    onCohortYear(ev) {
        this.state.filters.cohort_year_id = parseInt(ev.target.value, 10) || false;
        this.load();
    }

    get cohortRows() {
        const c = this.cohort;
        if (!c) {
            return [];
        }
        const keys = this.state.options.cohort_keys;
        return c.steps.map((s) => ({
            ...s,
            parts: keys
                .filter((k) => s.segments[k.key])
                .map((k) => ({ ...k, count: s.segments[k.key], width: (100 * s.segments[k.key]) / Math.max(1, c.size) })),
            present: ["promoted", "conditional", "retained", "ongoing", "dropped", "transferred"].reduce(
                (n, key) => n + (s.segments[key] || 0),
                0
            ),
        }));
    }

    get usedCohortKeys() {
        const c = this.cohort;
        return c ? this.state.options.cohort_keys.filter((k) => c.steps.some((s) => s.segments[k.key])) : [];
    }

    share(count, total) {
        return total ? `${fmt((100 * count) / total, 0)}%` : "—";
    }

    // Aproveitamento

    get performance() {
        return this.state.data ? this.state.data.performance : null;
    }

    /** A cor de cada ano (paleta categórica pela ordem dos anos lectivos: a cor segue o ano, não a posição). */
    yearColor(yearId) {
        const index = this.state.options.years.findIndex((y) => y.id === yearId);
        return `o_edu_subj_${Math.min(8, index + 1)}`;
    }

    /** O percurso T1 → T2 → T3 de cada ano: as linhas, os pontos e a escala do eixo (à volta dos valores). */
    get trimesterChart() {
        const lines = this.performance ? this.performance.trimesters : [];
        const values = lines.flatMap((l) => l.values.filter((v) => v !== null));
        if (!values.length) {
            return null;
        }
        const low = Math.max(0, Math.floor(Math.min(...values, 10) - 1));
        const high = Math.min(20, Math.ceil(Math.max(...values) + 1));
        const { width, height, left, right, top, bottom } = CHART;
        const plotW = width - left - right;
        const plotH = height - top - bottom;
        const x = (i) => left + (plotW * i) / 2;
        const y = (v) => top + plotH - (plotH * (v - low)) / Math.max(1, high - low);
        const ticks = [];
        const step = high - low > 8 ? 2 : 1;
        for (let v = low; v <= high; v += step) {
            ticks.push({ value: v, y: y(v) });
        }
        return {
            ticks,
            pass: 10 >= low && 10 <= high ? y(10) : null,
            xs: ["1.º trimestre", "2.º trimestre", "3.º trimestre"].map((label, i) => ({ label, x: x(i) })),
            lines: lines.map((l) => {
                const points = l.values
                    .map((v, i) => (v === null ? null : { x: x(i), y: y(v), v, i }))
                    .filter(Boolean);
                const end = points[points.length - 1];
                return {
                    ...l,
                    color: this.yearColor(l.year_id),
                    path: points.map((p) => `${p.x},${p.y}`).join(" "),
                    points,
                    end,
                };
            }),
            labelYs: this.spreadLabels(lines.map((l) => {
                const last = [...l.values].reverse().find((v) => v !== null);
                return y(last);
            })),
        };
    }

    /** As etiquetas no fim das linhas sem se sobreporem (pelo menos 14px entre elas). */
    spreadLabels(ys) {
        const order = ys.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
        for (let k = 1; k < order.length; k++) {
            order[k].v = Math.max(order[k].v, order[k - 1].v + 14);
        }
        const out = [];
        for (const o of order) {
            out[o.i] = o.v;
        }
        return out;
    }

    /** As médias finais por faixas: uma barra por ano (100% dos avaliados). */
    get bandRows() {
        const bands = this.state.options.bands;
        return (this.performance ? this.performance.bands : []).map((b) => ({
            ...b,
            parts: bands
                .filter((band) => b.counts[band.index])
                .map((band) => ({ ...band, count: b.counts[band.index], width: (100 * b.counts[band.index]) / b.total })),
        }));
    }

    /** A cor de cada célula do mapa das disciplinas: mais escura com mais negativas (50% ou mais, a cor toda). */
    heatStyle(rate) {
        if (rate === null || rate === undefined) {
            return "";
        }
        const strength = Math.round(8 + Math.min(1, rate / 50) * 92);
        return `--edu-heat: ${strength}%`;
    }

    heatClass(rate) {
        if (rate === null || rate === undefined) {
            return "o_edu_an_heat_none";
        }
        return rate >= 30 ? "o_edu_an_heat_strong" : "";
    }

    onClassYear(ev) {
        this.state.filters.class_year_id = parseInt(ev.target.value, 10) || false;
        this.load();
    }

    /** As turmas do ano: a média de 0 a 20 numa barra com o traço da positiva (10). */
    get classRows() {
        const classes = this.performance && this.performance.classes;
        return classes
            ? classes.rows.map((r) => ({ ...r, width: r.average === null ? 0 : (100 * r.average) / 20 }))
            : [];
    }

    /** Escolhe o ano de um quadro (as disciplinas em atraso, as turmas) e volta a carregar. */
    onYearOf(key, ev) {
        this.state.filters[key] = parseInt(ev.target.value, 10) || false;
        this.load();
    }

    // Decisões e disciplinas em atraso

    get decisions() {
        return this.state.data && this.state.data.decisions;
    }

    /** As negativas da decisão: uma barra por ano (100% dos avaliados). */
    get negativeRows() {
        const d = this.decisions;
        const labels = this.state.options.negatives;
        return d
            ? d.years.map((y) => ({
                  ...y,
                  parts: labels
                      .filter((l) => y.negatives[l.index])
                      .map((l) => ({ ...l, count: y.negatives[l.index], width: (100 * y.negatives[l.index]) / y.decided })),
              }))
            : [];
    }

    get arrearsBars() {
        const d = this.decisions;
        const max = d ? Math.max(1, ...d.arrears.map((a) => a.count)) : 1;
        return d ? d.arrears.map((a) => ({ ...a, width: (100 * a.count) / max })) : [];
    }

    get lastDecisions() {
        const d = this.decisions;
        return d ? d.years[d.years.length - 1] : null;
    }

    get pendingExams() {
        const d = this.decisions;
        return d ? d.exams.reduce((n, e) => n + e.pending, 0) : 0;
    }

    // Saídas

    get exits() {
        return this.state.data && this.state.data.exits;
    }

    /** As saídas de cada ano: uma barra com a parte de cada tipo de saída nas matrículas do ano, à escala do ano com
     * mais saídas (para se verem as diferenças). */
    get exitRows() {
        const e = this.exits;
        if (!e) {
            return [];
        }
        const max = Math.max(1, ...e.years.map((y) => y.rate || 0));
        return e.years.map((y) => ({
            ...y,
            parts: this.state.options.exits
                .filter((k) => y.counts[k.key])
                .map((k) => ({
                    ...k,
                    count: y.counts[k.key],
                    width: (100 * ((100 * y.counts[k.key]) / Math.max(1, y.enrolled))) / max,
                })),
        }));
    }

    get lastExits() {
        const e = this.exits;
        const closed = e ? e.years.filter((y) => y.counts.not_renewed !== null) : [];
        return closed[closed.length - 1] || null;
    }

    get reasonBars() {
        const e = this.exits;
        const max = e ? Math.max(1, ...e.reasons.map((r) => r.count)) : 1;
        return e ? e.reasons.map((r) => ({ ...r, width: (100 * r.count) / max })) : [];
    }

    get monthColumns() {
        const e = this.exits;
        if (!e) {
            return [];
        }
        const max = Math.max(1, ...e.months.map((m) => m.count));
        const names = Object.fromEntries(this.state.options.months.map((m) => [m.id, m.name]));
        return e.months.map((m) => ({ ...m, name: names[m.month], height: (100 * m.count) / max }));
    }

    get hasMonths() {
        return this.monthColumns.some((m) => m.count);
    }

    // Turmas e capacidade

    get capacity() {
        return this.state.data && this.state.data.capacity;
    }

    get lastCapacity() {
        const c = this.capacity;
        return c ? c.years.find((y) => y.year_id === c.year_id) : null;
    }

    meterClass(occupancy) {
        if (occupancy === null || occupancy === undefined) {
            return "";
        }
        if (occupancy > 100) {
            return "o_edu_meter_bad";
        }
        return occupancy < 50 ? "o_edu_meter_warn" : "";
    }

    meterWidth(occupancy) {
        return `width: ${Math.min(100, occupancy || 0)}%`;
    }

    sizeLabel(index) {
        return this.state.options.sizes[index].label;
    }
}

registry.category("actions").add("edu_analytics.dashboard", AnalyticsDashboard);
