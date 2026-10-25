import { registry } from "@web/core/registry";
import { session } from "@web/session";

// O aluno (sem outro papel na escola) não muda os seus dados nas Preferências (são da secretaria; a palavra-passe muda-se
// em «Meu perfil») e não usa as actividades do pessoal. As Discussões ficam: são as suas mensagens com a escola.
if (session.edu_student_only) {
    registry.category("user_menuitems").remove("preferences");
    registry.category("systray").remove("mail.activity_menu");
}
