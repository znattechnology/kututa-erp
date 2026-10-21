import { translatedTerms, translatedTermsGlobal, translationIsReady } from "@web/core/l10n/translation";
import { user } from "@web/core/user";

/**
 * Correcções de tradução do núcleo do Odoo para português de Angola e Portugal: textos sem tradução no pt.po
 * (aparecem em inglês) ou traduzidos em português do Brasil. Por módulo de origem, como o Odoo os procura.
 */
const GROUP_COUNT = {
    "%s record": "%s registo",
    "%s records": "%s registos",
};
const TERMS = {
    web: GROUP_COUNT,
    kututa_web: GROUP_COUNT,
    mail: {
        Unread: "Não lidas",
        "Search Conversation": "Procurar conversa",
        "Turn on notifications": "Activar notificações",
        Enable: "Activar",
        "Stay tuned! Enable push notifications to never miss a message.":
            "Active as notificações para não perder nenhuma mensagem.",
    },
};

export function applyTerms() {
    if (!(user.lang || "").startsWith("pt")) {
        return;
    }
    for (const [module, terms] of Object.entries(TERMS)) {
        translatedTerms[module] = Object.assign(translatedTerms[module] || {}, terms);
        Object.assign(translatedTermsGlobal, terms);
    }
}

translationIsReady.then(applyTerms);
