from odoo import api, fields, models
from odoo.tools import formatLang


class L10nAoStampDutyItem(models.Model):
    """Verbas da Tabela do Imposto de Selo (Tabela 3 do Decreto Executivo n.º 683/25)."""

    _name = 'l10n_ao.stamp.duty.item'
    _description = 'Verba do Imposto de Selo'
    _order = 'sequence, id'
    _rec_names_search = ['code', 'name']

    sequence = fields.Integer(default=10)
    code = fields.Char(string='N.º verba', required=True)
    name = fields.Text(string='Acto / documento / contrato', required=True)
    rate_type = fields.Selection(
        selection=[('percent', 'Percentagem'), ('fixed', 'Valor fixo (Kz)'), ('none', 'Agrupamento')],
        string='Tipo de taxa',
        required=True,
        default='percent',
    )
    rate = fields.Float(string='Taxa', digits=(16, 4))
    rate_display = fields.Char(string='Taxa ', compute='_compute_rate_display')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'A verba tem de ser única.')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.code} - {(record.name or "")[:80]}'

    @api.depends('rate_type', 'rate')
    def _compute_rate_display(self):
        for record in self:
            if record.rate_type == 'percent':
                record.rate_display = f'{formatLang(self.env, record.rate, digits=2)} %'
            elif record.rate_type == 'fixed':
                record.rate_display = f'{formatLang(self.env, record.rate, digits=2)} Kz'
            else:
                record.rate_display = ''
