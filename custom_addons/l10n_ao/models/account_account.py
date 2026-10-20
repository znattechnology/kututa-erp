from odoo import fields, models

# withholdingTaxType da API de Facturação Electrónica (Anexo I do DE n.º 683/25).
AO_WITHHOLDING_TYPES = [
    ('IRT', 'IRT - Imposto sobre os Rendimentos do Trabalho'),
    ('II', 'II - Imposto Industrial'),
    ('IS', 'IS - Imposto de Selo'),
    ('IVA', 'IVA - Imposto sobre o Valor Acrescentado (cativo)'),
    ('IP', 'IP - Imposto Predial'),
    ('IAC', 'IAC - Imposto sobre Aplicação de Capitais'),
    ('OU', 'OU - Outros'),
]


class AccountAccount(models.Model):
    _inherit = 'account.account'

    l10n_ao_withholding_type = fields.Selection(
        AO_WITHHOLDING_TYPES,
        string='Retenção na fonte (AGT)',
        help='Conta de retenção/cativação sofrida: os valores lançados nos recebimentos são comunicados '
        'à AGT no recibo (withholdingTaxList).',
    )
