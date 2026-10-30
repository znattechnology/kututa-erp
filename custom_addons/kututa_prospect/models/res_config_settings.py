from odoo import api, fields, models
from odoo.exceptions import UserError

from .kututa_prospect_ia import MODELO

TEXTO_AGT = 'Facturação electrónica preparada para o modelo da AGT (DP 71/25 e DE 683/25), em processo de certificação.'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kututa_prospect_ia_activa = fields.Boolean('Classificação com IA', config_parameter='kututa_prospect.ia_activa')
    kututa_prospect_modelo = fields.Selection(
        [
            ('claude-haiku-5-5', 'Haiku 5.5 (o mais barato)'),
            ('claude-sonnet-5-5', 'Sonnet 5.5 (equilibrado)'),
            ('claude-opus-5-5', 'Opus 5.5 (o mais capaz)'),
        ],
        'Modelo da prospecção',
        default=MODELO,
        config_parameter='kututa_prospect.modelo',
    )
    kututa_prospect_agt_estado = fields.Selection(
        [('em_homologacao', 'Em homologação'), ('certificado', 'Certificado pela AGT')],
        'Estado na AGT',
        default='em_homologacao',
        config_parameter='kututa_prospect.agt_estado',
    )
    kututa_prospect_agt_texto = fields.Char(
        'Frase sobre a AGT', default=TEXTO_AGT, config_parameter='kututa_prospect.agt_texto'
    )
    kututa_prospect_max_entradas_dia = fields.Integer(
        'Máximo de entradas do n8n por dia', default=2000, config_parameter='kututa_prospect.max_entradas_dia'
    )

    @api.constrains('kututa_prospect_agt_estado', 'kututa_prospect_agt_texto')
    def _check_kututa_prospect_agt(self):
        for settings in self:
            if settings.kututa_prospect_agt_texto:
                self.env['crm.lead']._kp_validar_afirmacao_agt(
                    settings.kututa_prospect_agt_texto, estado=settings.kututa_prospect_agt_estado
                )

    def set_values(self):
        if not self.env.user.has_group('kututa_prospect.group_prospect_manager') and (
            self.kututa_prospect_agt_estado
            != self.env['ir.config_parameter'].sudo().get_str('kututa_prospect.agt_estado', 'em_homologacao')
        ):
            raise UserError(self.env._('Só o Gestor da prospecção muda o estado na AGT.'))
        return super().set_values()
