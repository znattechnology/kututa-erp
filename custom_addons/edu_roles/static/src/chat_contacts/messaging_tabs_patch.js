import { MessagingMenuTab } from "@mail/core/public_web/messaging_menu/messaging_menu_tab_model";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

// O professor, o aluno e o encarregado (sem outro papel na escola) conversam com as pessoas: os canais e as reuniões
// ficam para a secretaria e a direcção, por isso as Mensagens deles ficam só com as conversas (e as notificações).
patch(MessagingMenuTab.prototype, {
    get canBeShown() {
        const restricted = session.edu_teacher_only || session.edu_student_only || session.edu_guardian_only;
        if (restricted && ["channel", "meeting"].includes(this.id)) {
            return false;
        }
        return super.canBeShown;
    },
});
