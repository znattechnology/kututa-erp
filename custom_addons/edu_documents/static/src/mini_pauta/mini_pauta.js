import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

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
 * Escolhe-se o ano lectivo (os anos fechados também se imprimem, para o arquivo), a turma e o trimestre.
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
    }

    get year() {
        return this.state.years.find((y) => y.id === this.state.yearId);
    }

    get selectedClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    get trimester() {
        return this.state.trimesters.find((t) => t.id === this.state.trimesterId);
    }

    get ready() {
        return Boolean(this.selectedClass && this.trimester);
    }

    async onYearChange(ev) {
        await this.load(parseInt(ev.target.value, 10) || false);
    }

    onClassChange(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        if (this.state.classId) {
            remember(this.state.classId);
        }
    }

    selectTrimester(trimester) {
        this.state.trimesterId = trimester.id;
    }

    async open(preview) {
        if (!this.ready || this.state.busy) {
            return;
        }
        this.state.busy = preview ? "open" : "print";
        try {
            const action = await this.orm.call("edu.mini.pauta", "page_open", [
                this.state.classId,
                this.state.trimesterId,
                preview,
            ]);
            await this.action.doAction(action);
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("edu_documents.mini_pauta", MiniPauta);
