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

    def _edu_guardian_only(self):
        """Encarregado sem outro papel na escola (nem aluno, nem professor, nem secretaria, nem administração): só tem
        a sua área. Um professor que também é encarregado continua com o seu painel e ganha a área do encarregado."""
        self.ensure_one()
        if not self.has_group('edu_portal.group_edu_guardian'):
            return False
        roles = [
            self.env.ref(xmlid, raise_if_not_found=False)
            for xmlid in (*OTHER_ROLES, 'edu_core.group_edu_teacher', 'edu_portal.group_edu_student')
        ]
        return not any(group in self.all_group_ids for group in roles if group)

    # Para as regras de acesso (o safe_eval não chama métodos começados por «_»): só restringem quem tem apenas a
    # área do aluno ou do encarregado, não um funcionário que também o seja.
    @api.private
    def edu_student_only(self):
        return self._edu_student_only()

    @api.private
    def edu_guardian_only(self):
        return self._edu_guardian_only()

    def _on_webclient_bootstrap(self):
        # O aluno e o encarregado usam as Discussões só para falar com a escola: o OdooBot não lhes abre uma conversa.
        if (
            'odoobot_state' in self._fields
            and self.odoobot_state != 'disabled'
            and (self._edu_student_only() or self._edu_guardian_only())
        ):
            self.sudo().odoobot_state = 'disabled'
        return super()._on_webclient_bootstrap()

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        self.env['discuss.channel']._edu_remove_family(users)
        return users

    def write(self, vals):
        result = super().write(vals)
        if 'group_ids' in vals:
            self.env['discuss.channel']._edu_remove_family(self)
        return result
