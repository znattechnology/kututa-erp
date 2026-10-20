from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import L10nAoEdiCommon


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao_edi')
class TestL10nAoEdiNumbering(L10nAoEdiCommon):
    def test_agt_numbering_without_gaps(self):
        first = self._create_invoice()
        second = self._create_invoice()
        code = self.series['FT'].code
        self.assertEqual(first.name, f'FT {code}/1')
        self.assertEqual(second.name, f'FT {code}/2')
        self.assertEqual(first.l10n_ao_edi_state, 'to_send')
        self.assertEqual(self.series['FT'].next_number, 3)

    def test_document_types(self):
        invoice = self._create_invoice()
        self.assertEqual(invoice.l10n_ao_document_type, 'FT')
        receipt = self._create_invoice(post=False)
        receipt.l10n_ao_document_type = 'FR'
        receipt.action_post()
        self.assertTrue(receipt.name.startswith(f'FR {self.series["FR"].code}/'))

    def test_missing_series_blocks_posting(self):
        self.series['FT'].action_close()
        with self.assertRaisesRegex(UserError, 'série AGT activa'):
            self._create_invoice()

    def test_missing_configuration_blocks_posting(self):
        self.company.l10n_ao_edi_taxpayer_key_id = False
        with self.assertRaisesRegex(UserError, 'Configuração AGT incompleta'):
            self._create_invoice()

    def test_communicated_documents_are_locked(self):
        invoice = self._create_invoice()
        with self.assertRaisesRegex(UserError, 'nota de crédito'):
            invoice.button_draft()
        with self.assertRaisesRegex(UserError, 'nota de crédito'):
            invoice.button_cancel()

    def test_credit_note_rules(self):
        invoice = self._create_invoice()
        invoice.l10n_ao_edi_state = 'valid'
        refund = invoice._reverse_moves([{'invoice_date': invoice.invoice_date}], cancel=False)
        # A referência do Odoo («Estorno de: …») não conta como motivo: só o motivo AGT escrito pelo utilizador.
        refund.ref = 'Estorno de: FT'
        with self.assertRaisesRegex(UserError, 'motivo'):
            refund.action_post()
        refund.l10n_ao_edi_reason = 'Devolução do serviço'
        refund.action_post()
        self.assertEqual(refund.l10n_ao_document_type, 'NC')
        self.assertTrue(refund.name.startswith(f'NC {self.series["NC"].code}/'))

    def test_lines_need_agt_taxes(self):
        with self.assertRaisesRegex(UserError, 'classificação AGT'):
            self._create_invoice(lines=[(self.service, 1, 100.0, self.env['account.tax'])])

    def test_future_date_rejected(self):
        move = self._create_invoice(post=False)
        move.invoice_date = move.invoice_date.replace(year=move.invoice_date.year + 1)
        with self.assertRaisesRegex(UserError, 'posterior'):
            move.action_post()

    def test_non_angolan_company_unaffected(self):
        self.company.l10n_ao_edi_enabled = False
        invoice = self._create_invoice()
        self.assertFalse(invoice.l10n_ao_edi_series_id)
        self.assertFalse(invoice.l10n_ao_edi_state)

    def test_credit_note_needs_communicated_origin(self):
        invoice = self._create_invoice()
        refund = invoice._reverse_moves([{'invoice_date': invoice.invoice_date}], cancel=False)
        refund.ref = 'Devolução'
        with self.assertRaisesRegex(UserError, 'não foi aceite pela AGT'):
            refund.action_post()

    def test_empty_invoice_date_defaults_to_today(self):
        move = self._create_invoice(post=False)
        move.invoice_date = False
        move.action_post()
        self.assertEqual(move.invoice_date, fields.Date.context_today(move))
        self.assertTrue(move.name.startswith('FT '))
