from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import L10nAoEdiCommon


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao_edi')
class TestL10nAoEdiContingency(L10nAoEdiCommon):
    def test_contingency_uses_contingency_series_and_holds_sending(self):
        self.company.l10n_ao_edi_contingency = True
        self.assertTrue(self.company.l10n_ao_edi_contingency_start)
        invoice = self._create_invoice()
        self.assertTrue(invoice.name.startswith(f'FT {self.contingency_series.code}/'))
        self.assertTrue(invoice.l10n_ao_edi_contingency)
        html = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', invoice.ids)[0].decode()
        self.assertIn('Emitido em contingência, pendente de autorização', html)

        with self.mock_agt({'registarFactura': (200, {'requestID': '202600000000009', 'errorList': []})}):
            self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._cron_send()
            self.assertEqual(invoice.l10n_ao_edi_state, 'to_send', 'Em contingência nada é enviado')
            self.company.l10n_ao_edi_contingency = False
            self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._cron_send()
        self.assertEqual(invoice.l10n_ao_edi_state, 'sent')

    def test_missing_contingency_series(self):
        self.contingency_series.action_close()
        self.company.l10n_ao_edi_contingency = True
        with self.assertRaisesRegex(UserError, 'de contingência'):
            self._create_invoice()

    def test_sixty_days_without_communication_blocks_issuing(self):
        old = self._create_invoice()
        old.l10n_ao_edi_system_entry_date = fields.Datetime.now() - timedelta(days=61)
        self.company.l10n_ao_edi_last_communication = False
        with self.assertRaisesRegex(UserError, '60 dias'):
            self._create_invoice()
        # Uma comunicação recente com a AGT desbloqueia a emissão.
        self.company.l10n_ao_edi_last_communication = fields.Datetime.now()
        self.assertTrue(self._create_invoice().name)
