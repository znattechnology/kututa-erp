from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def webclient_rendering_context(self):
        # Ícone do separador: o favicon do site da escola (ou o do Kututa ERP), não o do Odoo.
        # Vai pelo contexto e não por uma vista herdada: uma vista criada por este módulo numa base com o
        # website falha na actualização (o campo obrigatório «visibility» ainda não está carregado).
        return {**super().webclient_rendering_context(), 'x_icon': '/kututa_web/favicon'}
