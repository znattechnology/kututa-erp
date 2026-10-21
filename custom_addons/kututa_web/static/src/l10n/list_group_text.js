import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// O Odoo 20 escreve «12 records» nos grupos das listas sem passar pela tradução.
patch(ListRenderer.prototype, {
    getGroupText(group) {
        return group.count <= 1 ? _t("%s record", group.count) : _t("%s records", group.count);
    },
});
