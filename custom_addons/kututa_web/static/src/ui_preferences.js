import { browser } from "@web/core/browser/browser";

/**
 * Preferências de interface guardadas no navegador (por utilizador e por máquina). Lidas com
 * try/catch: em modo privado o localStorage pode falhar, e aí vale o valor por omissão.
 */
const PREFIX = "kututa_web.";

export function getPreference(key, fallback) {
    try {
        const value = browser.localStorage.getItem(PREFIX + key);
        return value === null ? fallback : JSON.parse(value);
    } catch {
        return fallback;
    }
}

export function setPreference(key, value) {
    try {
        browser.localStorage.setItem(PREFIX + key, JSON.stringify(value));
    } catch {
        // Sem armazenamento: a preferência vale só até recarregar a página.
    }
}
