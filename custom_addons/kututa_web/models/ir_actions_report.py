from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def preview_action(self, docids):
        """Abre o PDF num separador novo: o mesmo ficheiro que a impressão gera, para ver antes de imprimir."""
        self.ensure_one()
        ids = docids.ids if isinstance(docids, models.BaseModel) else docids
        return {
            'type': 'ir.actions.act_url',
            'url': f'/report/pdf/{self.report_name}/{",".join(map(str, ids))}',
            'target': 'new',
        }
