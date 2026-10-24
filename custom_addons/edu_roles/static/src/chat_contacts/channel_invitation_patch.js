import { ChannelInvitation } from "@mail/discuss/core/common/channel_invitation";
import { onWillStart, proxy } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";

/**
 * «Nova conversa» das Mensagens, como no secPed: numa conversa nova e sem nada escrito na procura, o «Conversar»
 * mostra primeiro os contactos por grupos (o director de turma, os professores das minhas turmas, a secretaria e a
 * direcção). Escolher um abre logo a conversa; a procura do Odoo continua por baixo, para qualquer outro colega.
 */
patch(ChannelInvitation.prototype, {
    setup() {
        super.setup(...arguments);
        this.eduChat = proxy({ groups: [] });
        onWillStart(async () => {
            if (!this.props.channel && this.store.self_user?.share === false) {
                this.eduChat.groups = await this.orm.call("edu.teacher.home", "chat_contacts", []);
            }
        });
    },

    get eduChatGroups() {
        return !this.props.channel && !this.searchStr ? this.eduChat.groups : [];
    },

    async eduOpenChat(contact) {
        await this.store.openChat({ partnerId: contact.partner_id });
        this.props.close?.();
    },
});
