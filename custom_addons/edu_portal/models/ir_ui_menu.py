from odoo import api, models
from odoo.addons.edu_roles.models.ir_ui_menu import OTHER_ROLES, TEACHER_HIDDEN_APPS

STUDENT_TRAINING_MENU = 'edu_portal.menu_student_training'


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _load_menus_blacklist(self):
        """O aluno (sem outro papel na escola) só tem a sua área, como o professor: sem Discussões nem Calendário, e
        sem a formação técnica se não for do ensino técnico."""
        hidden = super()._load_menus_blacklist()
        user = self.env.user
        roles = [
            self.env.ref(xmlid, raise_if_not_found=False) for xmlid in (*OTHER_ROLES, 'edu_core.group_edu_teacher')
        ]
        if user.has_group('edu_portal.group_edu_student') and not any(g in user.all_group_ids for g in roles if g):
            hidden_xmlids = list(TEACHER_HIDDEN_APPS)
            # A formação técnica (o estágio e a PAP) é do ensino técnico, como no secPed.
            Portal = self.env['edu.student.portal']
            if not Portal._is_technical(Portal._student(user)):
                hidden_xmlids.append(STUDENT_TRAINING_MENU)
            for xmlid in hidden_xmlids:
                menu = self.env.ref(xmlid, raise_if_not_found=False)
                if menu and menu.id not in hidden:
                    hidden.append(menu.id)
        return hidden
