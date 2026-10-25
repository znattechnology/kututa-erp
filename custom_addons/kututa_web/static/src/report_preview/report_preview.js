import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { getReportUrl } from "@web/webclient/actions/reports/utils";

/**
 * «Visualizar» numa janela por cima da página: o documento em HTML, com «Imprimir» (o PDF) e «Fechar». A página de
 * onde se veio fica onde estava, sem mudar de ecrã nem de separador.
 */
export class ReportPreviewDialog extends Component {
    static template = "kututa_web.ReportPreviewDialog";
    static components = { Dialog };

    props = useProps({
        close: t.function(),
        action: t.object(),
        print: t.function(),
    });

    get title() {
        return this.props.action.display_name || this.props.action.name || "Documento";
    }

    get url() {
        return getReportUrl(this.props.action, "html", user.context);
    }

    onLoad(ev) {
        const body = ev.currentTarget.contentDocument?.body;
        if (body) {
            body.classList.add("o_in_iframe", "container-fluid");
            body.classList.remove("container");
        }
    }

    async print() {
        await this.props.print();
    }
}

registry.category("ir.actions.report handlers").add("kututa_report_preview", async (action, options, env) => {
    if (action.report_type !== "qweb-html" || !action.context?.kututa_preview) {
        return false;
    }
    const { kututa_preview: _flag, ...context } = action.context;
    const pdf = { ...action, context, report_type: "qweb-pdf" };
    env.services.dialog.add(ReportPreviewDialog, {
        action: { ...action, context },
        print: () => env.services.action.doAction(pdf),
    });
    return true;
});
