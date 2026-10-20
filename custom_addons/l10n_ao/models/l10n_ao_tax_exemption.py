from odoo import api, fields, models


class L10nAoTaxExemption(models.Model):
    """Motivos de isenção/não sujeição (Tabelas 4 a 6 do Decreto Executivo n.º 683/25)."""

    _name = 'l10n_ao.tax.exemption'
    _description = 'Motivo de isenção (AGT)'
    _order = 'tax_type, code'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='Código', required=True, size=3)
    tax_type = fields.Selection(
        selection=[('IVA', 'IVA'), ('IS', 'Imposto de Selo'), ('IEC', 'Imposto Especial de Consumo')],
        string='Imposto',
        required=True,
    )
    name = fields.Char(string='Menção no documento', required=True, translate=False)
    description = fields.Text(string='Descrição')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'O código de isenção tem de ser único.')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.code} - {record.name}'
