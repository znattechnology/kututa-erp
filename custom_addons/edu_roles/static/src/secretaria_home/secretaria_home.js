import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const LIMIT = 10;

/**
 * O Painel da secretaria, como o dos Serviços Académicos do secPed, num quadro: o que está à espera de tratamento
 * (cada linha abre a lista onde se resolve), os números do ano, os alunos por classe, as turmas (as que têm alguma
 * coisa por resolver primeiro, com a ocupação e as notas lançadas) e os eventos das próximas duas semanas.
 */
export class SecretariaHome extends Component {
    static template = "edu_roles.SecretariaHome";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, all: false });
        onWillStart(async () => {
            this.state.data = await this.orm.call("edu.secretaria.home", "home_data", []);
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async open(key, resId = false) {
        const action = await this.orm.call("edu.secretaria.home", "open", [key, resId]);
        return this.action.doAction(action);
    }

    openAction(xmlid) {
        return this.action.doAction(xmlid);
    }

    get occupancy() {
        const k = this.state.data.kpis;
        return k.capacity ? Math.round((100 * k.students) / k.capacity) : null;
    }

    get occupancyWidth() {
        return Math.min(100, this.occupancy || 0);
    }

    /** Os alunos por classe, em barras do maior número para 100%. */
    get perClass() {
        const rows = this.state.data.per_class;
        const max = Math.max(1, ...rows.map((r) => r.count));
        return rows.map((r) => ({ ...r, width: r.count ? Math.max(2, (100 * r.count) / max) : 0 }));
    }

    get classes() {
        const rows = this.state.data.classes;
        return this.state.all ? rows : rows.slice(0, LIMIT);
    }

    get hiddenClasses() {
        return Math.max(0, this.state.data.classes.length - LIMIT);
    }

    toggleAll() {
        this.state.all = !this.state.all;
    }

    occupancyClass(row) {
        return row.over ? "o_edu_meter_bad" : row.occupancy >= 90 ? "o_edu_meter_warn" : "";
    }
}

registry.category("actions").add("edu_roles.secretaria_home", SecretariaHome);
