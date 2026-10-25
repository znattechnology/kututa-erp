import { DiscussContent } from "@mail/core/public_web/discuss_content";
import { onWillStart, proxy } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

// As Mensagens sem conversa aberta (o professor, o aluno e o encarregado): em vez do «Nenhuma conversa seleccionada»,
// os contactos da «Nova conversa» (os directores de turma, os professores, a secretaria e a direcção), cada um com o
// seu «Escrever». Quem não tem contactos (um utilizador sem papel na escola) fica com a frase do Odoo.
patch(DiscussContent.prototype, {
    setup() {
        super.setup(...arguments);
        this.eduIntro = proxy({ groups: [] });
        if (user.isInternalUser) {
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

    /** As conversas por ler (as de pessoa a pessoa e os grupos), para as abrir logo à entrada. */
    get eduUnread() {
        const channels = this.store["discuss.channel"]?.records;
        if (!channels) {
            return [];
        }
        return [...channels.values()]
            .filter((c) => c.isChatChannel && c.isUnread && c.self_member_id?.is_pinned)
            .slice(0, 5);
    },

    eduOpenChannel(channel) {
        channel.thread.setAsDiscussThread();
    },

    eduInitials(name) {
        const words = (name || "").split(/\s+/).filter(Boolean);
        return words.length > 1 ? words[0][0] + words.at(-1)[0] : (words[0] || "?").slice(0, 2);
    },

    async eduOpenChat(contact) {
        await this.store.openChat({ partnerId: contact.partner_id });
    },
});
