from odoo import fields, models
from odoo.exceptions import UserError

# Documentos emitidos no POS sem factura: talões de venda e notas de crédito das devoluções.
POS_DOCUMENT_TYPES = ('TV', 'NC')


class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _check_before_creating_new_session(self):
        """Não se abre uma sessão sem séries AGT activas: as vendas ficariam por numerar."""
        result = super()._check_before_creating_new_session()
        Series = self.env['l10n_ao_edi.series']
        year = fields.Date.context_today(self).year
        for config in self.filtered('company_id.l10n_ao_edi_enabled'):
            company = config.company_id
            missing = [
                doc_type
                for doc_type in POS_DOCUMENT_TYPES
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
