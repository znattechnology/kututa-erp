from odoo import api, fields, models

# USD por milhão de tokens (entrada, saída, leitura da cache, escrita da cache), lidos a 30/10/2026.
PRECOS = {
    'claude-opus-5-5': (4.0, 20.0, 0.20, 5.0),
    'claude-sonnet-5-5': (2.0, 10.0, 0.20, 2.5),
    'claude-haiku-5-5': (0.10, 0.50, 0.01, 0.125),
}


class KututaIaUso(models.Model):
    _name = 'kututa.ia.uso'
    _description = 'Pedido à API de IA do chat do site'
    _order = 'id desc'

    channel_id = fields.Many2one('discuss.channel', 'Conversa', index=True, ondelete='cascade')
    modelo = fields.Char()
    pedido = fields.Char('ID do pedido')
    motivo_paragem = fields.Char()
    tokens_entrada = fields.Integer()
    tokens_saida = fields.Integer()
    tokens_cache_lidos = fields.Integer()
    tokens_cache_escritos = fields.Integer()
    custo_usd = fields.Float('Custo (USD)', digits=(10, 5), compute='_compute_custo_usd', store=True)
    erro = fields.Text()

    @api.depends('modelo', 'tokens_entrada', 'tokens_saida', 'tokens_cache_lidos', 'tokens_cache_escritos')
    def _compute_custo_usd(self):
        for uso in self:
            entrada, saida, lidos, escritos = PRECOS.get(uso.modelo, PRECOS['claude-opus-5-5'])
            uso.custo_usd = (
                uso.tokens_entrada * entrada
                + uso.tokens_saida * saida
                + uso.tokens_cache_lidos * lidos
                + uso.tokens_cache_escritos * escritos
            ) / 1_000_000
