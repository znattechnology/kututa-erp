from odoo import api, fields, models


class L10nAoPayrollIrtBracket(models.Model):
    _name = 'l10n_ao_payroll.irt.bracket'
    _description = 'Escalão do IRT (grupo A)'
    _order = 'date_from desc, lower'

    date_from = fields.Date(string='Em vigor desde', required=True, default='2026-01-01')
    lower = fields.Monetary(string='Limite inferior (exclusivo)', required=True, currency_field='currency_id')
    upper = fields.Monetary(
        string='Limite superior (inclusivo)', currency_field='currency_id', help='Vazio no último escalão.'
    )
    fixed = fields.Monetary(string='Parcela fixa', currency_field='currency_id')
    rate = fields.Float(string='Taxa (%)', digits=(5, 2), required=True)
    source = fields.Char(string='Fonte legal')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.ref('base.AOA'))
    active = fields.Boolean(default=True)

    @api.model
    def _brackets_for(self, day):
        """[(inferior, superior|None, fixa, taxa)] da tabela em vigor na data (a mais recente com início ≤ data)."""
        # Sem tabela em vigor na data não se aplica outra: o recibo avisa e o IRT fica por calcular.
        latest = self.search([('date_from', '<=', day)], order='date_from desc', limit=1)
        if not latest:
            return []
        rows = self.search([('date_from', '=', latest.date_from)], order='lower')
        return [(row.lower, row.upper or None, row.fixed, row.rate / 100) for row in rows]
