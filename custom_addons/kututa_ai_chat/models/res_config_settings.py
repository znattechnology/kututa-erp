from odoo import fields, models

from .kututa_ia_agente import MODELO, MODELOS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kututa_ia_activo = fields.Boolean('Assistente de IA activo', config_parameter='kututa_ia.activo')
    kututa_ia_modelo = fields.Selection(
        [(m, d['nome']) for m, d in MODELOS.items()],
        'Modelo de IA',
        config_parameter='kututa_ia.modelo',
        default=MODELO,
    )
    kututa_ia_esforco = fields.Selection(
        [('low', 'Baixo'), ('medium', 'Médio'), ('high', 'Alto')],
        'Esforço',
        config_parameter='kututa_ia.esforco',
        default='low',
    )
    kututa_ia_max_respostas = fields.Integer(
        'Máximo de respostas por conversa', config_parameter='kututa_ia.max_respostas', default=30
    )
