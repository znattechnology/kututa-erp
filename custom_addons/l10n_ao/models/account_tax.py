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
        compute='_compute_l10n_ao_tax_region',
        store=True,
        readonly=False,
    )
    l10n_ao_exemption_id = fields.Many2one(
        'l10n_ao.tax.exemption',
        string='Motivo de isenção (AGT)',
        help='Obrigatório quando o código de imposto é ISE ou o tipo é NS (DE n.º 683/25, taxExemptionCode).',
    )

    @api.depends('country_code', 'l10n_ao_tax_type')
    def _compute_l10n_ao_tax_region(self):
        for tax in self:
            if tax.country_code != 'AO':
                tax.l10n_ao_tax_region = False
            elif not tax.l10n_ao_tax_region:
                tax.l10n_ao_tax_region = 'AO'

    def _l10n_ao_needs_exemption(self):
        self.ensure_one()
        return self.l10n_ao_tax_type == 'NS' or self.l10n_ao_tax_code == 'ISE'

    @api.constrains('country_id', 'amount', 'l10n_ao_tax_type', 'l10n_ao_tax_code', 'l10n_ao_exemption_id')
    def _check_l10n_ao_agt_fields(self):
        for tax in self.filtered(lambda t: t.country_code == 'AO' and t.l10n_ao_tax_type):
            exemption = tax.l10n_ao_exemption_id
            if tax.l10n_ao_tax_type == 'IVA' and not tax.l10n_ao_tax_code:
                raise ValidationError(
                    self.env._('O imposto "%s" é de IVA: indique o código de imposto da AGT.', tax.name)
                )
            if tax.l10n_ao_tax_type == 'NS' and tax.l10n_ao_tax_code:
                raise ValidationError(
                    self.env._('O imposto "%s" é não sujeito: não pode ter código de imposto.', tax.name)
                )
            if tax._l10n_ao_needs_exemption():
                if not exemption:
                    raise ValidationError(
                        self.env._(
                            'O imposto "%s" é isento ou não sujeito: indique o motivo de isenção da AGT.', tax.name
                        )
                    )
                if tax.amount:
                    raise ValidationError(
                        self.env._('O imposto "%s" é isento ou não sujeito: a taxa tem de ser 0.', tax.name)
                    )
            elif exemption:
                raise ValidationError(
                    self.env._('O imposto "%s" não é isento: retire o motivo de isenção da AGT.', tax.name)
                )
            if exemption and tax.l10n_ao_tax_type not in (exemption.tax_type, 'NS'):
                raise ValidationError(
                    self.env._(
                        'O motivo de isenção %(code)s é de %(type)s e não pode ser usado no imposto "%(tax)s".',
                        code=exemption.code,
                        type=exemption.tax_type,
                        tax=tax.name,
                    )
                )
