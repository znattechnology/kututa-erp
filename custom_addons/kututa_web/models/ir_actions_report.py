from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def preview_action(self, docids):
        """Mostra o documento na própria aplicação, em HTML, no lugar da página: «Imprimir» gera o PDF e «Voltar»
        regressa a onde se estava. Sem separadores novos."""
        self.ensure_one()
        action = self.report_action(docids, config=False)
        action['report_type'] = 'qweb-html'
        return action
