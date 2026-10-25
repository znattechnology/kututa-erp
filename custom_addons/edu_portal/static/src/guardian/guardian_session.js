import { registry } from "@web/core/registry";
import { session } from "@web/session";

// O encarregado (sem outro papel na escola) não muda os seus dados nas Preferências: são da secretaria (o NIF vai nas
// facturas). A palavra-passe muda-se em «Meu perfil»; as Discussões ficam, são as suas mensagens com a escola.
if (session.edu_guardian_only) {
    registry.category("user_menuitems").remove("preferences");
    registry.category("systray").remove("mail.activity_menu");
}
