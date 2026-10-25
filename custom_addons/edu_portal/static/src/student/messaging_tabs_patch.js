import { MessagingMenuTab } from "@mail/core/public_web/messaging_menu/messaging_menu_tab_model";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

// O aluno e o encarregado só conversam com os contactos da lista: os canais e as reuniões da escola não são para eles,
// por isso as Mensagens ficam só com as conversas (e as notificações).
patch(MessagingMenuTab.prototype, {
    get canBeShown() {
        if ((session.edu_student_only || session.edu_guardian_only) && ["channel", "meeting"].includes(this.id)) {
            return false;
        }
        return super.canBeShown;
    },
});
