from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ao_closing_type = fields.Selection(
        [('close', 'Apuramento de resultados'), ('transfer', 'Transferência para resultados transitados')],
        string='Encerramento PGC',
        readonly=True,
        copy=False,
        index='btree_not_null',
    )
    l10n_ao_closing_year = fields.Integer(string='Exercício encerrado', readonly=True, copy=False)
