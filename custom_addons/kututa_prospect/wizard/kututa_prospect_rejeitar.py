from odoo import fields, models


class KututaProspectRejeitar(models.TransientModel):
    _name = 'kututa.prospect.rejeitar'
    _description = 'Rejeitar leads de prospecção'

    lead_ids = fields.Many2many('crm.lead', string='Leads', required=True)
    motivo = fields.Char(required=True)
    excluir = fields.Boolean(
        'Excluir de todas as campanhas',
        help='A organização recusou o contacto: entra na lista de exclusão global e nenhum perfil a volta a contactar.',
    )

    def action_rejeitar(self):
        self.lead_ids._kp_rejeitar(self.motivo, excluir=self.excluir)
        return {'type': 'ir.actions.act_window_close'}
