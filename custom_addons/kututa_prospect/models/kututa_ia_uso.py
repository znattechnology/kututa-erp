from odoo import fields, models


class KututaIaUso(models.Model):
    _inherit = 'kututa.ia.uso'

    kp_lead_id = fields.Many2one('crm.lead', 'Lead de prospecção', index=True, ondelete='cascade')
