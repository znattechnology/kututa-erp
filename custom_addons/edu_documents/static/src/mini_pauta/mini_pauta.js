import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { getReportUrl } from "@web/webclient/actions/reports/utils";

const LAST_CLASS_KEY = "edu_documents.mini_pauta.class";

function remembered() {
    try {
        return parseInt(window.localStorage.getItem(LAST_CLASS_KEY), 10) || false;
    } catch {
        return false;
    }
}

function remember(classId) {
    try {
        window.localStorage.setItem(LAST_CLASS_KEY, String(classId));
    } catch {
        // Sem armazenamento: fica só nesta visita.
    }
}

/**
 * «Mini-pauta», como a do secPed-Express: o mapa de aproveitamento da turma num trimestre (uma letra por
 * disciplina, a CT/MT de cada aluno, ou a CF no fim do ano, e as faltas), numa folha A4 para imprimir e assinar.
 * As turmas à esquerda (por curso), o ano e o trimestre no topo, e a mini-pauta na própria página: escolhida a turma,
 * aparece logo; «Imprimir» gera o PDF. Os anos fechados também se abrem, para o arquivo.
 */
export class MiniPauta extends Component {
    static template = "edu_documents.MiniPauta";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            yearId: false,
            years: [],
            classes: [],
            classId: false,
            trimesters: [],
            trimesterId: false,
            filter: "",
            // O documento à vista: o URL da mini-pauta em HTML e a acção para o PDF.
            url: false,
            report: null,
            error: false,
            busy: false,
        });
        onWillStart(() => {
            const context = this.props.action.context || {};
            return this.load(context.default_academic_year_id || false, context.default_class_id);
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async load(yearId, classId = false) {
        const options = await this.orm.call("edu.mini.pauta", "page_options", [yearId]);
        this.state.yearId = options.year_id;
        this.state.years = options.years;
        this.state.classes = options.classes;
        this.state.trimesters = options.trimesters;
        const wanted = classId || remembered();
        this.state.classId = (this.state.classes.find((c) => c.id === wanted) || {}).id || false;
        const current = options.trimesters.find((t) => t.is_current) || options.trimesters[0];
        this.state.trimesterId = current ? current.id : false;
        await this.refresh();
    }

    get selectedClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    /** As turmas por curso, filtradas pela pesquisa. */
    get classGroups() {
        const filter = this.state.filter.trim().toLowerCase();
        const groups = [];
        for (const c of this.state.classes) {
            if (filter && !`${c.name} ${c.course || ""}`.toLowerCase().includes(filter)) {
                continue;
            }
            const course = c.course || "Sem curso";
            let group = groups.find((g) => g.course === course);
            if (!group) {
                group = { course, classes: [] };
                groups.push(group);
            }
            group.classes.push(c);
        }
        return groups;
    }

    /** Prepara a mini-pauta da turma e do trimestre escolhidos e mostra-a na página. */
    async refresh() {
        this.state.url = false;
        this.state.report = null;
        this.state.error = false;
        if (!this.selectedClass || !this.state.trimesterId) {
            return;
        }
        // A resposta de uma turma ou trimestre escolhido antes não se sobrepõe à da escolha actual.
        const request = (this.refreshRequest = (this.refreshRequest || 0) + 1);
        try {
            const action = await this.orm.call("edu.mini.pauta", "page_open", [
                this.state.classId,
                this.state.trimesterId,
                true,
            ]);
            if (request !== this.refreshRequest) {
                return;
            }
            const { kututa_preview: _flag, ...context } = action.context || {};
            this.state.report = { ...action, context };
            this.state.url = getReportUrl(this.state.report, "html", user.context);
        } catch (error) {
            if (request === this.refreshRequest) {
                this.state.error = error.data?.message || error.message;
            }
        }
    }

    async onYearChange(ev) {
        await this.load(parseInt(ev.target.value, 10) || false);
    }

    async selectClass(classId) {
        this.state.classId = classId;
        remember(classId);
        await this.refresh();
    }

    async selectTrimester(trimester) {
        this.state.trimesterId = trimester.id;
        await this.refresh();
    }

    onFrameLoad(ev) {
        const body = ev.currentTarget.contentDocument?.body;
        if (body) {
            body.classList.add("o_in_iframe", "container-fluid");
            body.classList.remove("container");
        }
    }

    async print() {
        if (!this.state.report || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            // De novo no servidor: o registo temporário da mini-pauta à vista pode já ter sido limpo pelo Odoo.
            const action = await this.orm.call("edu.mini.pauta", "page_open", [
                this.state.classId,
                this.state.trimesterId,
                false,
            ]);
            await this.action.doAction(action);
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("edu_documents.mini_pauta", MiniPauta);
