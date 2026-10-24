from odoo import api, models
from odoo.addons.edu_roles.models.ir_ui_menu import OTHER_ROLES


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _edu_student_only(self):
        """Aluno sem outro papel na escola (nem professor, nem secretaria, nem administração): só tem a sua área."""
        self.ensure_one()
        if not self.has_group('edu_portal.group_edu_student'):
            return False
        roles = [
            self.env.ref(xmlid, raise_if_not_found=False) for xmlid in (*OTHER_ROLES, 'edu_core.group_edu_teacher')
        ]
        return not any(group in self.all_group_ids for group in roles if group)

    def _on_webclient_bootstrap(self):
        # O aluno não usa as Discussões: o OdooBot não lhe abre uma conversa.
        if 'odoobot_state' in self._fields and self.odoobot_state != 'disabled' and self._edu_student_only():
            self.sudo().odoobot_state = 'disabled'
        return super()._on_webclient_bootstrap()

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        self.env['discuss.channel']._edu_remove_students(users)
        return users

    def write(self, vals):
        result = super().write(vals)
        if 'group_ids' in vals:
            self.env['discuss.channel']._edu_remove_students(self)
        return result
