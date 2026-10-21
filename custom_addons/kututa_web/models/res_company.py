from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies.filtered(lambda c: not c.external_report_layout_id)._kututa_set_default_layout()
        return companies

    def _kututa_set_default_layout(self):
        # Sem layout definido, a primeira impressão do administrador abre o assistente do Odoo (com uma factura de
        # exemplo) em vez do documento pedido. O Kututa parte do layout padrão; muda-se nas Definições.
        layout = self.env.ref('web.external_layout_standard', raise_if_not_found=False)
        if layout:
            self.write({'external_report_layout_id': layout.id})
