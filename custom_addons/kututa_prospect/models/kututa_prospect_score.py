from odoo import fields, models

from .kututa_prospect_profile import FONTES


class KututaProspectScore(models.Model):
    _name = 'kututa.prospect.score'
    _description = 'Pontuação de um lead para um produto'
    _order = 'pontuacao desc, id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='lead_id.company_id', store=True, index=True)
    profile_id = fields.Many2one('kututa.prospect.profile', 'Produto', required=True, ondelete='cascade')
    pontuacao = fields.Integer('Pontuação')
    criterios_cumpridos = fields.Text('Critérios cumpridos')
    justificacao = fields.Text('Justificação')


class KututaProspectSource(models.Model):
    _name = 'kututa.prospect.source'
    _description = 'Fonte de um dado de um lead de prospecção'
    _order = 'data_recolha desc, id'

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='lead_id.company_id', store=True, index=True)
    campo = fields.Char('Dado', required=True)
    url = fields.Char('Endereço')
    fonte = fields.Selection(FONTES, required=True)
    data_recolha = fields.Datetime('Recolhido em', default=fields.Datetime.now, required=True)
