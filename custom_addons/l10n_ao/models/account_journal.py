from odoo import api, models

from .template_ao import BANK_FOREIGN_PREFIX


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def _create_default_account(self, company, journal_type, vals):
        """PGC: os depósitos à ordem em moeda estrangeira ficam em 43.2, não em 43.1."""
        account_id = super()._create_default_account(company, journal_type, vals)
        currency_id = vals.get('currency_id')
        is_foreign_bank = journal_type == 'bank' and currency_id and currency_id != company.currency_id.id
        if not account_id or not is_foreign_bank:
            return account_id
        chart_template = self.env['account.chart.template'].with_company(company)
        if 'ao' not in chart_template._get_parent_template(company.chart_template):
            return account_id
        account = self.env['account.account'].with_company(company).browse(account_id)
        account.write(
            {
                'code': account._search_new_account_code(BANK_FOREIGN_PREFIX, cache=set()),
                'parent_id': chart_template._get_account_parent_id(BANK_FOREIGN_PREFIX),
            }
        )
        return account_id

    # Pagamentos por contas de valores em trânsito (48.1/48.2): permite registar diferenças de pagamento
    # (retenções na fonte sofridas, IVA cativo, descontos) no próprio recebimento.
    def _compute_inbound_payment_method_line_ids(self):
        result = super()._compute_inbound_payment_method_line_ids()
        self._assign_outstanding_account_to_payment_method_lines('inbound', chart_template='ao')
        return result

    def _compute_outbound_payment_method_line_ids(self):
        result = super()._compute_outbound_payment_method_line_ids()
        self._assign_outstanding_account_to_payment_method_lines('outbound', chart_template='ao')
        return result
