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
    # (retenções na fonte sofridas, IVA cativo, descontos) no próprio recebimento, em bancos e em caixa.
    def _l10n_ao_assign_outstanding_accounts(self, payment_type):
        """Liga a conta de valores em trânsito aos métodos de pagamento sem conta (não mexe nas já configuradas)."""
        journals = self.filtered(
            lambda j: (
                j.type in ('bank', 'cash')
                and j.company_id.chart_template
                and 'ao' in self.env['account.chart.template']._get_parent_template(j.company_id.chart_template)
            )
        )
        account_xmlid = (
            'account_journal_payment_debit_account_id'
            if payment_type == 'inbound'
            else 'account_journal_payment_credit_account_id'
        )
        for company, company_journals in journals.grouped('company_id').items():
            account = (
                self.env['account.chart.template'].with_company(company).ref(account_xmlid, raise_if_not_found=False)
            )
            lines = company_journals[f'{payment_type}_payment_method_line_ids'].filtered(
                lambda line: not line.payment_account_id
            )
            if account and lines:
                lines.payment_account_id = account

    def _compute_inbound_payment_method_line_ids(self):
        result = super()._compute_inbound_payment_method_line_ids()
        self._l10n_ao_assign_outstanding_accounts('inbound')
        return result

    def _compute_outbound_payment_method_line_ids(self):
        result = super()._compute_outbound_payment_method_line_ids()
        self._l10n_ao_assign_outstanding_accounts('outbound')
        return result
