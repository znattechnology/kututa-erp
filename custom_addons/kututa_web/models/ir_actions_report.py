from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def preview_action(self, docids):
        """Mostra o documento numa janela por cima da página, em HTML: «Imprimir» gera o PDF e «Fechar» deixa a
        página como estava. Sem mudar de ecrã nem abrir separadores (static/src/report_preview)."""
        self.ensure_one()
        action = self.report_action(docids, config=False)
        action['report_type'] = 'qweb-html'
        action['context'] = {**(action.get('context') or {}), 'kututa_preview': True}
        return action
