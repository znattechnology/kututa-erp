from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        # O browser esconde ao professor (sem outro papel) os canais e as reuniões das Mensagens.
        info = super().session_info()
        user = self.env.user
        info['edu_teacher_only'] = bool(user) and user._is_internal() and user._edu_teacher_only()
        return info
