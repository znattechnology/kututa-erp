import { registry } from "@web/core/registry";
import { session } from "@web/session";

// O aluno (sem outro papel na escola) não muda os seus dados nas Preferências (são da secretaria; a palavra-passe muda-se
// em «Meu perfil») e não usa as Discussões nem as actividades do pessoal.
if (session.edu_student_only) {
    registry.category("user_menuitems").remove("preferences");
    for (const item of ["mail.messaging_menu", "mail.activity_menu"]) {
        registry.category("systray").remove(item);
    }
}
