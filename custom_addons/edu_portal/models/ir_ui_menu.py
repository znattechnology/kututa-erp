from odoo import api, models
from odoo.addons.edu_roles.models.ir_ui_menu import TEACHER_HIDDEN_APPS

STUDENT_TRAINING_MENU = 'edu_portal.menu_student_training'
GUARDIAN_RDEC_MENU = 'edu_portal.menu_guardian_rdec'
# As Ausências são dos funcionários: o aluno não tem ficha de funcionário.
STUDENT_HIDDEN_APPS = (*TEACHER_HIDDEN_APPS, 'hr_holidays.menu_hr_holidays_root')


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _load_menus_blacklist(self):
        """O aluno e o encarregado (sem outro papel na escola) só têm a sua área, como o professor: sem Discussões,
        Calendário nem Ausências. O aluno sem a formação técnica se não for do ensino técnico; o encarregado sem o RDEC
        se nenhum educando estiver na Iniciação."""
        hidden = super()._load_menus_blacklist()
        user = self.env.user
        hidden_xmlids = []
        if user._edu_student_only():
            hidden_xmlids = list(STUDENT_HIDDEN_APPS)
            # A formação técnica (o estágio e a PAP) é do ensino técnico, como no secPed.
            Portal = self.env['edu.student.portal']
            if not Portal._is_technical(Portal._student(user)):
                hidden_xmlids.append(STUDENT_TRAINING_MENU)
        elif user._edu_guardian_only():
            hidden_xmlids = list(STUDENT_HIDDEN_APPS)
        # O RDEC só a quem tem um educando na Iniciação, como no secPed (também ao professor que é encarregado).
        if user.has_group('edu_portal.group_edu_guardian') and not self.env['edu.guardian.portal']._has_preschool():
            hidden_xmlids.append(GUARDIAN_RDEC_MENU)
        for xmlid in hidden_xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.id not in hidden:
                hidden.append(menu.id)
        return hidden
