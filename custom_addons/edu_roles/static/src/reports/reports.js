import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const fmt = (value) => (value === null || value === undefined ? "—" : value.toLocaleString("pt-PT"));
const plural = (n, one, many) => (n === 1 ? one : `${fmt(n)} ${many}`);

/**
 * «Relatórios», como no secPed: os números da escola num ano lectivo, por subsistema, nível, curso ou turma. Cada
 * quadro diz primeiro, numa frase, o que conta, e depois uma barra por grupo. Durante o ano contam as matrículas, as
 * notas do trimestre e as chamadas; o resultado final e as classificações por disciplina, quando os conselhos fecham.
 */
export class ReportsPage extends Component {
    static template = "edu_roles.ReportsPage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.fmt = fmt;
        this.plural = plural;
        this.state = proxy({
            years: [],
            groups: [],
            yearId: false,
            groupBy: "subsystem",
            trimesterId: false,
            classId: false,
            data: null,
            loading: false,
            exporting: "",
        });
        onWillStart(async () => {
            const options = await this.orm.call("edu.report.page", "options", []);
            Object.assign(this.state, { years: options.years, groups: options.groups, yearId: options.year_id });
            await this.load();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get args() {
        const s = this.state;
        return [s.yearId, s.groupBy, s.trimesterId || false, s.classId || false];
    }

    async load() {
        if (!this.state.yearId) {
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call("edu.report.page", "report", this.args);
            this.state.data = data;
            this.state.trimesterId = data.grades.trimester_id;
        } finally {
            this.state.loading = false;
        }
    }

    async onYear(ev) {
        this.state.yearId = parseInt(ev.target.value, 10) || false;
        this.state.trimesterId = false;
        this.state.classId = false;
        await this.load();
    }

    async setGroup(value) {
        this.state.groupBy = value;
        await this.load();
    }

    async onTrimester(ev) {
        this.state.trimesterId = parseInt(ev.target.value, 10) || false;
        await this.load();
    }

    async onClass(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        await this.load();
    }

    width(pct) {
        return `width: ${Math.max(0, Math.min(100, pct || 0))}%`;
    }

    shareWidth(value, rows, field) {
        const max = Math.max(1, ...rows.map((r) => r[field]));
        return `width: ${(100 * value) / max}%`;
    }

    // Frases

    get gradesSentence() {
        const g = this.state.data.grades;
        return `No ${g.trimester}, ${g.pct}% das ${fmt(g.grades)} notas lançadas são positivas.`;
    }

    gradeDetail(row) {
        const average = row.average !== null ? `média ${fmt(row.average)}` : "";
        if (row.with_negative) {
            return [`${plural(row.with_negative, "um aluno", "alunos")} com negativa`, average].filter(Boolean).join(", ");
        }
        return average || "sem negativas";
    }

    finalDetail(row) {
        const parts = [`${fmt(row.approved)} de ${fmt(row.evaluated)}`];
        if (row.exam) {
            parts.push(`${fmt(row.exam)} em recurso`);
        }
        if (row.average !== null) {
            parts.push(`média ${fmt(row.average)}`);
        }
        return parts.join(", ");
    }

    // Gráficos (SVG desenhado aqui: barras finas com a ponta arredondada, grelha discreta, dica ao passar o rato)

    get kpis() {
        const d = this.state.data;
        return [
            { key: "enrolled", label: "alunos matriculados", value: fmt(d.enrollments.total) },
            {
                key: "grades",
                label: d.grades.grades ? `positivas no ${d.grades.trimester}` : "positivas (ainda sem notas)",
                value: d.grades.grades ? `${d.grades.pct}%` : "—",
            },
            {
                key: "attendance",
                label: d.attendance.calls ? "presenças nas aulas" : "presenças (ainda sem chamadas)",
                value: d.attendance.calls ? `${d.attendance.pct}%` : "—",
            },
            {
                key: "final",
                label: d.final.evaluated ? "transitaram ou concluíram" : "transitaram (ano por fechar)",
                value: d.final.evaluated ? `${d.final.pct}%` : "—",
            },
        ];
    }

    /** Distribuição das notas de 0 a 20: uma coluna por valor e a linha da nota mínima. */
    get histogram() {
        const counts = this.state.data.grades.histogram;
        if (!counts.length) {
            return null;
        }
        const W = 440, H = 150, left = 8, bottom = 22, top = 16;
        const step = (W - left * 2) / counts.length;
        const max = Math.max(...counts);
        const bars = counts.map((count, value) => {
            const h = max ? ((H - bottom - top) * count) / max : 0;
            return {
                key: value,
                x: left + value * step + 1,
                y: H - bottom - h,
                w: step - 2,
                h,
                negative: value < 10,
                title: `${value} valores: ${fmt(count)} ${count === 1 ? "nota" : "notas"}`,
                label: value % 5 === 0 ? `${value}` : "",
                lx: left + value * step + step / 2,
            };
        });
        return { W, H, bars, base: H - bottom, passX: left + 10 * step - 0.5, top };
    }

    /** Percentagem de positivas em cada trimestre do ano. */
    get trimesterColumns() {
        const items = this.state.data.grades.by_trimester.filter((t) => t.grades);
        if (items.length < 2) {
            return null;
        }
        const W = 240, H = 150, bottom = 22, top = 20;
        const slot = W / items.length;
        const w = Math.min(36, slot * 0.5);
        return {
            W,
            H,
            base: H - bottom,
            columns: items.map((t, i) => {
                const h = ((H - bottom - top) * (t.pct || 0)) / 100;
                const cx = slot * i + slot / 2;
                return { key: t.name, x: cx - w / 2, y: H - bottom - h, w, h, cx, pct: t.pct, name: t.name,
                    title: `${t.name}: ${t.pct}% positivas em ${fmt(t.grades)} notas` };
            }),
        };
    }

    /** Taxa de transição de ano para ano (os anos com resultado final). */
    get yearsLine() {
        const items = this.state.data.years_trend;
        if (items.length < 2) {
            return null;
        }
        const W = 440, H = 160, left = 34, right = 40, bottom = 22, top = 24;
        // Os pontos começam afastados do eixo, para o valor do primeiro ano não tapar o «100%».
        const inset = left + 28;
        const x = (i) => inset + ((W - inset - right) * i) / (items.length - 1);
        const y = (pct) => top + ((H - top - bottom) * (100 - pct)) / 100;
        const points = items.map((t, i) => ({
            key: t.id,
            x: x(i),
            y: y(t.pct),
            pct: t.pct,
            name: t.name,
            current: t.id === this.state.yearId,
            title: `${t.name}: ${t.pct}% transitaram (${fmt(t.approved)} de ${fmt(t.evaluated)})`,
        }));
        return {
            W,
            H,
            points,
            path: points.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "),
            grid: [0, 50, 100].map((v) => ({ v, y: y(v) })),
            last: points[points.length - 1],
            // Poucos anos: o valor vai em todos os pontos; muitos, só no ano escolhido e no último.
            labelAll: points.length <= 5,
            left,
        };
    }

    /** Resultado final de cada grupo, em partes: transitou, recurso, retido. */
    finalParts(row) {
        const total = row.evaluated || 1;
        return [
            { key: "approved", cls: "o_edu_rp_s1", n: row.approved, label: "transitaram" },
            { key: "exam", cls: "o_edu_rp_s3", n: row.exam, label: "em exame de recurso" },
            { key: "retained", cls: "o_edu_rp_s2", n: row.retained, label: "retidos" },
        ]
            .filter((part) => part.n)
            .map((part) => ({ ...part, style: `flex-grow: ${part.n / total}`, title: `${fmt(part.n)} ${part.label}` }));
    }

    // Exportar e análise detalhada

    async exportXlsx() {
        this.state.exporting = "xlsx";
        try {
            const file = await this.orm.call("edu.report.page", "export_xlsx", this.args);
            const link = document.createElement("a");
            link.href = `data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${file.datas}`;
            link.download = file.name;
            link.click();
        } finally {
            this.state.exporting = "";
        }
    }

    async printPdf() {
        this.state.exporting = "pdf";
        try {
            const action = await this.orm.call("edu.report.page", "print_pdf", this.args);
            await this.action.doAction(action);
        } finally {
            this.state.exporting = "";
        }
    }

    openAnalysis(xmlid) {
        return this.action.doAction(xmlid);
    }
}

registry.category("actions").add("edu_roles.reports", ReportsPage);
