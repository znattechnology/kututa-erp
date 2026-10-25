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

    /** O cargo e o departamento, numa linha («Professor, Departamento de Ciências»). */
    get roleLine() {
        const d = this.state.data;
        return [d.job || "Professor", d.department].filter(Boolean).join(", ");
    }

    /** O que falta na ficha (para o aviso). */
    get missing() {
        const d = this.state.data;
        return [
            !d.email && "o email",
            !d.phone && "o telefone",
            !d.id_number && "o n.º do BI",
            !d.inss && "o n.º da Segurança Social",
        ].filter(Boolean);
    }

    /** Os dados da ficha em grelha, com o ícone de cada um. */
    get fields() {
        const d = this.state.data;
        return [
            { key: "email", label: "Email", icon: "mail", value: d.email },
            { key: "phone", label: "Telefone", icon: "phone", value: d.phone },
            { key: "id_number", label: "Bilhete de identidade", icon: "credit_card", value: d.id_number },
            { key: "inss", label: "N.º da Segurança Social", icon: "badge", value: d.inss },
            { key: "department", label: "Departamento", icon: "groups", value: d.department },
            { key: "job", label: "Cargo", icon: "work", value: d.job },
        ];
    }

    get loadWidth() {
        const load = this.state.data.load;
        return load.limit ? Math.min(100, (100 * load.count) / load.limit) : 0;
    }

    initials(name) {
        const parts = (name || "").split(" ").filter(Boolean);
        return (parts[0] ? parts[0][0] : "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
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

    /** O líquido dos últimos 12 recibos normais (sem as contas finais), do mais antigo ao mais recente. */
    get netCols() {
        const MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
        const slips = this.state.data.payslips.filter((slip) => !slip.final).slice(0, 12).reverse();
        const max = Math.max(...slips.map((slip) => slip.net_value), 0);
        return slips.map((slip) => ({
            id: slip.id,
            label: slip.month ? MONTHS[slip.month - 1] : "",
            title: `${slip.period}: ${slip.net}`,
            height: max ? Math.max(2, (100 * slip.net_value) / max) : 0,
        }));
    }

    deductionShare(slip) {
        return slip.gross_value ? Math.round((100 * slip.deductions_value) / slip.gross_value) : 0;
    }

    /** Os dias aprovados este ano e os pedidos por aprovar. */
    get leaveTotals() {
        const leaves = this.state.data.time_off || [];
        return {
            days: leaves.filter((l) => l.state === "validate").reduce((sum, l) => sum + l.days, 0).toLocaleString("pt-PT"),
            pending: leaves.filter((l) => ["confirm", "validate1"].includes(l.state)).length,
        };
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
