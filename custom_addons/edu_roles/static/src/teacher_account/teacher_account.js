import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const list = (items) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} e ${items[items.length - 1]}` : items[0] || "");

/**
 * «Meu perfil», como no secPed: numa frase, o que o professor faz este ano; o trabalho (disciplinas, turmas,
 * direcção de turma, carga, departamento e cargo); os dados da ficha, que se corrigem na secretaria; e a mudança da
 * palavra-passe.
 */
export class TeacherProfilePage extends Component {
    static template = "edu_roles.TeacherProfilePage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("edu.teacher.home", "profile_data", []);
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    get sentence() {
        const d = this.state.data;
        if (!d.subjects.length) {
            return `${d.name}, ainda não tem disciplinas atribuídas${d.year ? ` no ano lectivo ${d.year}` : ""}.`;
        }
        const classes = d.classes.length === 1 ? "uma turma" : `${d.classes.length} turmas`;
        return `${d.name}, dá ${list(d.subjects)} em ${classes} no ano lectivo ${d.year}.`;
    }

    get loadText() {
        const load = this.state.data.load;
        const notes = load.notes.length ? ` (${load.notes.join(", ")})` : "";
        return `${load.count} de ${load.limit} tempos${notes}`;
    }

    get overLoad() {
        const load = this.state.data.load;
        return load.count > load.limit;
    }

    list(items) {
        return list(items);
    }

    async changePassword() {
        const action = await this.orm.call("edu.teacher.home", "change_password", []);
        return this.action.doAction(action);
    }
}

/**
 * «Recibos e férias», como no secPed: os recibos de vencimento fechados (o líquido, o bruto e os descontos, com a
 * folha A4 para ver ou descarregar) e, para quem tem acesso às ausências, as férias e as faltas pedidas este ano.
 */
export class TeacherPayslipsPage extends Component {
    static template = "edu_roles.TeacherPayslipsPage";
    static components = { Layout };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null });
        onWillStart(() => this.load());
    }

    get display() {
        return { controlPanel: {} };
    }

    async load() {
        this.state.data = await this.orm.call("edu.teacher.home", "payslips_data", []);
    }

    async openPayslip(slip, preview) {
        const action = await this.orm.call("edu.teacher.home", "payslip_report", [slip.id, preview]);
        return this.action.doAction(action);
    }

    async requestTimeOff() {
        const action = await this.orm.call("edu.teacher.home", "action_my_time_off", []);
        return this.action.doAction(action, { onClose: () => this.load() });
    }

    leaveClass(leave) {
        return (
            { validate: "text-bg-success", confirm: "text-bg-warning", validate1: "text-bg-warning", refuse: "text-bg-danger" }[
                leave.state
            ] || "text-bg-light"
        );
    }

    days(leave) {
        return leave.days === 1 ? "1 dia" : `${leave.days.toLocaleString("pt-PT")} dias`;
    }
}

registry.category("actions").add("edu_roles.teacher_profile", TeacherProfilePage);
registry.category("actions").add("edu_roles.teacher_payslips", TeacherPayslipsPage);
