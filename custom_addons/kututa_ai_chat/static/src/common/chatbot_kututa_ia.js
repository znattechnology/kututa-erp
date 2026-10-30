import { ChatbotScriptStep } from "@im_livechat/core/common/chatbot_script_step_model";
import { Chatbot } from "@im_livechat/core/common/chatbot_model";
import { patch } from "@web/core/utils/patch";

// Passo «Conversa com IA»: o bot espera sempre pela próxima mensagem do visitante.
patch(ChatbotScriptStep.prototype, {
    get expectAnswer() {
        return this.step_type === "kututa_ia" || super.expectAnswer;
    },
});

// Enquanto o servidor pede a resposta à IA (alguns segundos), mostra «a escrever…».
patch(Chatbot.prototype, {
    async _goToNextStep() {
        const comIa = this.currentStep?.step_type === "kututa_ia";
        if (comIa) {
            this.isTyping = true;
        }
        try {
            return await super._goToNextStep(...arguments);
        } finally {
            if (comIa) {
                this.isTyping = false;
            }
        }
    },
});
