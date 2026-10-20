from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Valores de taxType / taxCode da API de Facturação Electrónica (Anexo I do DE n.º 683/25).
AO_TAX_TYPES = [
    ('IVA', 'IVA - Imposto sobre o Valor Acrescentado'),
    ('IS', 'IS - Imposto de Selo'),
    ('IEC', 'IEC - Imposto Especial de Consumo'),
    ('CEOC', 'CEOC - Contribuição Especial de Consumo'),
    ('NS', 'NS - Não sujeito'),
]
AO_TAX_CODES = [
    ('NOR', 'NOR - Taxa normal'),
    ('INT', 'INT - Taxa intermédia'),
    ('RED', 'RED - Taxa reduzida'),
    ('ISE', 'ISE - Isento'),
    ('OUT', 'OUT - Outra'),
]


class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_ao_tax_type = fields.Selection(AO_TAX_TYPES, string='Tipo de imposto (AGT)')
    l10n_ao_tax_code = fields.Selection(AO_TAX_CODES, string='Código de imposto (AGT)')
    l10n_ao_tax_region = fields.Selection(
        selection=[('AO', 'Angola'), ('AO-CAB', 'Cabinda')],
        string='Região do imposto (AGT)',
        default='AO',
    )
    l10n_ao_exemption_id = fields.Many2one(
        'l10n_ao.tax.exemption',
        string='Motivo de isenção (AGT)',
        help='Obrigatório quando o código de imposto é ISE ou o tipo é NS (DE n.º 683/25, taxExemptionCode).',
    )

    @api.constrains('l10n_ao_tax_type', 'l10n_ao_tax_code', 'l10n_ao_exemption_id')
    def _check_l10n_ao_exemption(self):
        for tax in self:
            needs_reason = tax.l10n_ao_tax_type == 'NS' or tax.l10n_ao_tax_code == 'ISE'
            if needs_reason and not tax.l10n_ao_exemption_id:
                raise ValidationError(
                    self.env._(
                        'O imposto "%s" é isento ou não sujeito: indique o motivo de isenção da AGT.',
                        tax.name,
                    )
                )
            exemption_type = tax.l10n_ao_exemption_id.tax_type
            if exemption_type and tax.l10n_ao_tax_type not in (exemption_type, 'NS'):
                raise ValidationError(
                    self.env._(
                        'O motivo de isenção %(code)s é de %(type)s e não pode ser usado no imposto "%(tax)s".',
                        code=tax.l10n_ao_exemption_id.code,
                        type=exemption_type,
                        tax=tax.name,
                    )
                )
