from odoo import fields, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    # Histórico da conversa no formato da API da Anthropic (JSON), só acrescentado, nunca editado:
    # os blocos de raciocínio do modelo têm de voltar exactamente como vieram.
    kututa_ia_historico = fields.Text(copy=False)
    kututa_ia_respostas = fields.Integer(copy=False)
    kututa_ia_lead_id = fields.Many2one('crm.lead', copy=False, index='btree_not_null', ondelete='set null')
    kututa_ia_uso_ids = fields.One2many('kututa.ia.uso', 'channel_id')
