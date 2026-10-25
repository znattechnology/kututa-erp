import { Component, onWillStart, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

function remembered(key) {
    try {
        return parseInt(window.localStorage.getItem(key), 10) || false;
    } catch {
        return false;
    }
}

function remember(key, classId) {
    try {
        window.localStorage.setItem(key, String(classId || ""));
    } catch {
        // Sem armazenamento: fica só nesta visita.
    }
}

/**
 * O painel à esquerda das páginas de um aluno (Histórico, Declarações), como o da mini-pauta: o ano lectivo, as
 * turmas por curso (lembra-se a última) e os alunos da turma pelo número, ou a pesquisa pelo nome ou n.º de
 * processo. Quem já saiu da escola encontra-se no último ano em que esteve matriculado.
 */
export class StudentPanel extends Component {
    static template = "edu_documents.StudentPanel";

    props = useProps({
        onPick: t.function(),
        // O aluno à vista (para o destacar na lista).
        studentId: t.or([t.number(), t.literal(false)]).optional(false),
        // A chave do localStorage onde a página lembra a última turma.
        storageKey: t.string(),
    });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            yearId: false,
            years: [],
            classes: [],
            classId: false,
            students: [],
            filter: "",
            query: "",
            results: [],
            searching: false,
        });
        this.searchTimer = null;
        onWillUnmount(() => clearTimeout(this.searchTimer));
        onWillStart(() => this.loadYear(false, remembered(this.props.storageKey)));
    }

    async loadYear(yearId, classId = false) {
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
        if (classId && options.classes.some((c) => c.id === classId)) {
            await this.selectClass(classId);
        }
    }

    async onYearChange(ev) {
        await this.loadYear(parseInt(ev.target.value, 10) || false);
    }

    get selectedClass() {
        return this.state.classes.find((c) => c.id === this.state.classId);
    }

    /** As turmas por curso, filtradas pela pesquisa da turma. */
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

    async selectClass(classId) {
        this.state.classId = classId;
        this.state.filter = "";
        remember(this.props.storageKey, classId);
        this.state.students = [];
        // A resposta de uma turma escolhida antes não se sobrepõe à da turma actual.
        const request = (this.classRequest = (this.classRequest || 0) + 1);
        const students = await this.orm.call("edu.student.picker", "class_students", [classId]);
        if (request === this.classRequest) {
            this.state.students = students;
        }
    }

    backToClasses() {
        this.state.classId = false;
        this.state.students = [];
        remember(this.props.storageKey, false);
    }

    get searchMode() {
        return this.state.query.trim().length >= 2;
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
