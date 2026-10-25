import { ChannelInvitation } from "@mail/discuss/core/common/channel_invitation";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

// O aluno e o encarregado só escrevem aos contactos da lista (como no secPed): a procura não vai além dela, por isso
// sai a frase que convida a procurar outra pessoa da escola.
patch(ChannelInvitation.prototype, {
    setup() {
        super.setup(...arguments);
        this.eduChatRestricted = Boolean(session.edu_student_only || session.edu_guardian_only);
    },
});
