from odoo import models

from .ir_ui_menu import OTHER_ROLES


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _edu_teacher_only(self):
        """Professor sem outro papel na escola (nem secretaria, nem RH, nem administração): tem só o seu painel."""
        self.ensure_one()
        if not self.has_group('edu_core.group_edu_teacher'):
            return False
        roles = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in OTHER_ROLES]
        return not any(group in self.all_group_ids for group in roles if group)
