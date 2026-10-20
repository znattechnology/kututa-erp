from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ao_vat_regime = fields.Selection(
        selection=[
            ('general', 'Regime Geral'),
            ('simplified', 'Regime Simplificado'),
            ('exclusion', 'Regime de Exclusão'),
        ],
        string='Regime de IVA',
        default='general',
        help='Enquadramento em IVA (Código do IVA). Os Regimes Geral e Simplificado estão obrigados à '
        'facturação electrónica (art. 16.º do DP n.º 71/25).',
    )
    l10n_ao_cae_id = fields.Many2one('l10n_ao.cae', string='CAE principal')
