from odoo import api, fields, models


class L10nAoIecRate(models.Model):
    """Taxas do Imposto Especial de Consumo por classificação pautal (Tabela 2 do DE n.º 683/25)."""

    _name = 'l10n_ao.iec.rate'
    _description = 'Taxa do Imposto Especial de Consumo'
    _order = 'code'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='Classificação pautal', required=True)
    name = fields.Char(string='Designação', required=True)
    uom = fields.Char(string='Unidade de medida')
    rate = fields.Float(string='Taxa (%)', digits=(16, 2))
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'A classificação pautal tem de ser única.')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.code} - {record.name}'
