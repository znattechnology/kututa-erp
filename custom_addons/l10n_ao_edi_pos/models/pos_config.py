from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class PosConfig(models.Model):
    _inherit = 'pos.config'

    @api.constrains('set_tip_after_payment', 'company_id')
    def _check_l10n_ao_edi_tips(self):
        for config in self.filtered(lambda c: c.set_tip_after_payment and c.company_id.l10n_ao_edi_enabled):
            raise ValidationError(
                self.env._(
                    '%s: a gorjeta depois do pagamento alteraria um talão já emitido e comunicado à AGT. '
                    'Registe a gorjeta antes de pagar.',
                    config.name,
                )
            )

    def _l10n_ao_edi_required_document_types(self):
        """Tipos AGT que esta caixa pode emitir: talões, notas de crédito e, se factura, FR (e FT a crédito)."""
        self.ensure_one()
        types = ['TV', 'NC', 'FR']
        if any(method.type == 'pay_later' for method in self.payment_method_ids):
            types.append('FT')
        return types

    def _check_before_creating_new_session(self):
        """Não se abre uma sessão sem séries AGT activas: as vendas ficariam por numerar."""
        result = super()._check_before_creating_new_session()
        Series = self.env['l10n_ao_edi.series']
        year = fields.Date.context_today(self.with_context(tz='Africa/Luanda')).year
        for config in self.filtered('company_id.l10n_ao_edi_enabled'):
            company = config.company_id
            if config.currency_id != company.currency_id:
                raise UserError(
                    self.env._(
                        '%(pos)s: o Ponto de Venda tem de vender em %(currency)s.',
                        pos=config.name,
                        currency=company.currency_id.name,
                    )
                )
            missing = [
                doc_type
                for doc_type in config._l10n_ao_edi_required_document_types()
                if not Series._l10n_ao_edi_find(company, doc_type, year, contingency=company.l10n_ao_edi_contingency)
            ]
            if missing:
                raise UserError(
                    self.env._(
                        'Faltam séries AGT activas para o Ponto de Venda (%s). '
                        'Peça-as em Facturação > Configuração > Angola (AGT) > Séries AGT.',
                        ', '.join(missing),
                    )
                )
        return result
