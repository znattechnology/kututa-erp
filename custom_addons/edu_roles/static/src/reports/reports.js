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
