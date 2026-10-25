import { DiscussContent } from "@mail/core/public_web/discuss_content";
import { onWillStart, proxy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

// As Mensagens do aluno e do encarregado sem conversa aberta: em vez do «Nenhuma conversa seleccionada», os contactos
// da «Nova conversa» (o director de turma, os professores, a secretaria e a direcção), cada um com o seu «Escrever».
patch(DiscussContent.prototype, {
    setup() {
        super.setup(...arguments);
        this.eduIntro = proxy({ groups: [] });
        if (session.edu_student_only || session.edu_guardian_only) {
            const orm = useService("orm");
            onWillStart(async () => {
                // Sem os contactos fica a frase do Odoo; o «Conversar» continua a abrir a lista.
                try {
                    this.eduIntro.groups = await orm.silent.call("edu.teacher.home", "chat_contacts", []);
                } catch {
                    this.eduIntro.groups = [];
                }
            });
        }
    },

    eduInitials(name) {
        const words = (name || "").split(/\s+/).filter(Boolean);
        return words.length > 1 ? words[0][0] + words.at(-1)[0] : (words[0] || "?").slice(0, 2);
    },

    async eduOpenChat(contact) {
        await this.store.openChat({ partnerId: contact.partner_id });
    },
});
