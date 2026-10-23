import { Component, onWillStart, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Escolher um aluno, como o «EscolherAluno» do secPed-Express: no ano lectivo, pela turma (a lista dos alunos, pelo
 * número) ou pelo nome. Quem já saiu da escola encontra-se no último ano em que esteve matriculado.
 */
export class StudentPicker extends Component {
    static template = "edu_documents.StudentPicker";

    props = useProps({
        onPick: t.function(),
    });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            yearId: false,
            years: [],
            classes: [],
            classId: false,
            students: [],
            query: "",
            results: [],
            searching: false,
        });
        this.searchTimer = null;
        onWillUnmount(() => clearTimeout(this.searchTimer));
        onWillStart(() => this.loadYear(false));
    }

    async loadYear(yearId) {
        const options = await this.orm.call("edu.student.picker", "picker_options", [yearId]);
        Object.assign(this.state, {
            yearId: options.year_id,
            years: options.years,
            classes: options.classes,
            classId: false,
            students: [],
            results: [],
            query: "",
        });
    }

    async onYearChange(ev) {
        await this.loadYear(parseInt(ev.target.value, 10) || false);
    }

    async onClassChange(ev) {
        this.state.classId = parseInt(ev.target.value, 10) || false;
        this.state.students = this.state.classId
            ? await this.orm.call("edu.student.picker", "class_students", [this.state.classId])
            : [];
    }

    get selectedClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.search(), 300);
    }

    async search() {
        const query = this.state.query.trim();
        if (query.length < 2) {
            this.state.results = [];
            return;
        }
        // Uma resposta antiga (lenta) não se sobrepõe à da pesquisa mais recente.
        const request = (this.searchRequest = (this.searchRequest || 0) + 1);
        this.state.searching = true;
        try {
            const results = await this.orm.call("edu.student.picker", "search_students", [this.state.yearId, query]);
            if (request === this.searchRequest) {
                this.state.results = results;
            }
        } finally {
            if (request === this.searchRequest) {
                this.state.searching = false;
            }
        }
    }

    pick(row) {
        this.props.onPick(row);
    }
}
