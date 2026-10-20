from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_round

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

    # -------------------------------------------------------------------------
    # Arredondamento do imposto por linha (espelhado em static/src/helpers/account_tax.js)
    # -------------------------------------------------------------------------

    @api.model
    def _add_tax_details_in_base_line(self, base_line, company, rounding_method=None):
        """AGT (DE n.º 683/25, taxContribution): o imposto de cada linha é arredondado por excesso
        ao cêntimo seguinte (23,144 -> 23,15). A base continua a ser arredondada ao mais próximo.
        Sem isto, o total da factura podia diferir 1 cêntimo do total comunicado à AGT."""
        rounding_method = rounding_method or company.tax_calculation_rounding_method
        if company.account_fiscal_country_id.code != 'AO' or rounding_method != 'round_per_line':
            return super()._add_tax_details_in_base_line(base_line, company, rounding_method=rounding_method)

        super()._add_tax_details_in_base_line(base_line, company, rounding_method='round_globally')
        tax_details = base_line['tax_details']
        currency = base_line['currency_id']
        company_currency = company.currency_id

        def round_up(amount, rounding):
            return float_round(amount, precision_rounding=rounding, rounding_method='UP')

        tax_details['raw_total_excluded_currency'] = currency.round(tax_details['raw_total_excluded_currency'])
        tax_details['raw_total_excluded'] = company_currency.round(tax_details['raw_total_excluded'])
        for tax_data in tax_details['taxes_data']:
            tax_data['raw_tax_amount_currency'] = round_up(tax_data['raw_tax_amount_currency'], currency.rounding)
            tax_data['raw_tax_amount'] = round_up(tax_data['raw_tax_amount'], company_currency.rounding)
            tax_data['raw_base_amount_currency'] = currency.round(tax_data['raw_base_amount_currency'])
            tax_data['raw_base_amount'] = company_currency.round(tax_data['raw_base_amount'])
            tax_data['tax_amount'] = tax_data['raw_tax_amount_currency']
            tax_data['base_amount'] = tax_data['raw_base_amount_currency']
        tax_details['raw_total_included_currency'] = tax_details['raw_total_excluded_currency'] + sum(
            tax_data['raw_tax_amount_currency'] for tax_data in tax_details['taxes_data']
        )
        tax_details['raw_total_included'] = tax_details['raw_total_excluded'] + sum(
            tax_data['raw_tax_amount'] for tax_data in tax_details['taxes_data']
        )
        return None
