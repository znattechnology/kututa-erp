from odoo import api, fields, models


class L10nAoCae(models.Model):
    """Códigos de Actividade Económica (Tabela 1 do Decreto Executivo n.º 683/25, lista do INE)."""

    _name = 'l10n_ao.cae'
    _description = 'Código de Actividade Económica (CAE)'
    _order = 'code'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='Código', required=True, size=5)
    name = fields.Char(string='Descrição', required=True)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'O código CAE tem de ser único.')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.code} - {record.name}'
