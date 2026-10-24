import { registry } from "@web/core/registry";
import {
    BadgesSelectionField,
    badgesSelectionField,
} from "@web/views/fields/badges_selection/badges_selection_field";

// Cor de cada nível do RDEC, como no secPed: não satisfatório, satisfatório, bom, muito bom.
const TONES = {
    not_satisfactory: "danger",
    satisfactory: "warning",
    good: "info",
    very_good: "success",
};

/**
 * Nível de uma área do RDEC: os quatro níveis em botões, sempre à vista, e um clique escolhe (outro clique no mesmo
 * tira), sem ter de entrar primeiro na linha. Só leitura quando o relatório não é do(a) educador(a) da turma.
 */
export class RdecLevelField extends BadgesSelectionField {
    static template = "edu_evaluation.RdecLevelField";

    get editable() {
        const root = this.props.record.model.root;
        return Boolean(root.data.can_edit) && !root.isReadonly;
    }

    tone(value) {
        return TONES[value] || "secondary";
    }

    select(value) {
        this.props.record.update({ [this.props.name]: this.value === value ? false : value });
    }
}

registry.category("fields").add("edu_rdec_level", {
    ...badgesSelectionField,
    component: RdecLevelField,
});
