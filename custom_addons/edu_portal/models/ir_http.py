from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        # O browser esconde ao aluno as Preferências (os seus dados vêm da secretaria) e as Discussões.
        info = super().session_info()
        user = self.env.user
        info['edu_student_only'] = bool(user) and user._is_internal() and user._edu_student_only()
        # Ao encarregado esconde só as Preferências: as Discussões são as suas mensagens com a escola.
        info['edu_guardian_only'] = bool(user) and user._is_internal() and user._edu_guardian_only()
        return info
