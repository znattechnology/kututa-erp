from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import TODAY, L10nAoEdiCommon


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestL10nAoEdiAudit(L10nAoEdiCommon):
    """Casos encontrados na auditoria da fase 2."""

    def _accountant(self):
        return self.env['res.users'].create(
            {
                'name': 'Contabilista',
                'login': 'contabilista_ao',
                'company_id': self.company.id,
                'company_ids': [Command.set(self.company.ids)],
                'group_ids': [Command.set(self.env.ref('account.group_account_manager').ids)],
            }
        )

    # --- numeração e tipos ------------------------------------------------------------------------------

    def test_sales_receipt_cannot_take_agt_number(self):
        receipt = self.env['account.move'].create(
            {
                'move_type': 'out_receipt',
                'partner_id': self.partner_ao.id,
                'invoice_date': TODAY,
                'invoice_line_ids': [
                    Command.create({'name': 'X', 'price_unit': 10, 'tax_ids': [Command.set(self.vat14.ids)]})
                ],
            }
        )
        with self.assertRaisesRegex(UserError, 'recibos de venda'):
            receipt.action_post()

    def test_non_agt_moves_do_not_continue_agt_sequence(self):
        self._create_invoice()
        entry = self.env['account.move'].create(
            {
                'move_type': 'entry',
                'journal_id': self.company_data['default_journal_sale'].id,
                'date': TODAY,
                'line_ids': [
                    Command.create(
                        {'name': 'a', 'account_id': self.company_data['default_account_revenue'].id, 'credit': 10}
                    ),
                    Command.create(
                        {'name': 'b', 'account_id': self.company_data['default_account_receivable'].id, 'debit': 10}
                    ),
                ],
            }
        )
        entry.action_post()
        self.assertFalse(entry.name.startswith('FT '), entry.name)
        self.assertEqual(self._create_invoice().name, f'FT {self.series["FT"].code}/2')

    def test_document_type_must_match_move_type(self):
        with self.assertRaises(ValidationError):
            self._create_invoice(post=False, l10n_ao_document_type='NC')
        with self.assertRaises(ValidationError):
            self._create_invoice(post=False, l10n_ao_document_type='RG')

    def test_communicated_document_cannot_be_renamed(self):
        invoice = self._create_invoice()
        with self.assertRaisesRegex(UserError, 'não é possível alterar'):
            invoice.name = 'FT FT99X/1'
        with self.assertRaisesRegex(UserError, 'não é possível alterar'):
            invoice.partner_id = self.consumer
        invoice.narration = 'Notas internas podem mudar'

    # --- validações ---------------------------------------------------------------------------------------

    def test_negative_line_blocked(self):
        with self.assertRaisesRegex(UserError, 'valor negativo'):
            self._create_invoice(lines=[(self.service, 1, 1000.0, self.vat14), (self.service, 1, -100.0, self.vat14)])

    def test_credit_notes_cannot_exceed_invoice(self):
        invoice = self._create_invoice()
        self.mark_sent(invoice)
        first = invoice._reverse_moves([{'invoice_date': TODAY, 'l10n_ao_edi_reason': 'Anulação'}])
        first.action_post()
        second = invoice._reverse_moves([{'invoice_date': TODAY, 'l10n_ao_edi_reason': 'Anulação'}])
        with self.assertRaisesRegex(UserError, 'excedem'):
            second.action_post()

    def test_backdated_invoice_rejected(self):
        self._create_invoice()
        with self.assertRaisesRegex(UserError, 'ordem cronológica'):
            self._create_invoice(invoice_date=fields.Date.subtract(TODAY, days=40))

    def test_foreign_customer_needs_tax_id(self):
        foreigner = self.env['res.partner'].create({'name': 'Cliente PT', 'country_id': self.env.ref('base.pt').id})
        with self.assertRaisesRegex(UserError, 'estrangeiro'):
            self._create_invoice(partner=foreigner)

    def test_debit_note_reason_from_wizard(self):
        invoice = self._create_invoice()
        self.mark_sent(invoice)
        wizard = (
            self.env['account.debit.note']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'reason': 'Juros de mora', 'copy_lines': True})
        )
        debit_note = self.env['account.move'].browse(wizard.create_debit()['res_id'])
        self.assertEqual(debit_note.l10n_ao_edi_reason, 'Juros de mora')

    # --- payload ------------------------------------------------------------------------------------------

    def test_payload_frozen_and_consistent_with_totals(self):
        invoice = self._create_invoice(lines=[(self.service, 3, 10.0, self.vat14)])
        invoice.invoice_line_ids.discount = 28.56
        payload = invoice._l10n_ao_edi_payload_values()
        self.assertEqual(payload['documentTotals']['grossTotal'], invoice.amount_total)
        self.partner_ao.name = 'Outro'
        self.assertEqual(invoice._l10n_ao_edi_payload_values()['companyName'], 'Cliente Angola, Lda')

    def test_price_included_payload_without_tax(self):
        included = self.vat14.copy({'name': 'IVA 14% incl.', 'price_include_override': 'tax_included'})
        invoice = self._create_invoice(lines=[(self.service, 1, 114.0, included)])
        [line] = invoice._l10n_ao_edi_payload_values()['lines']
        self.assertEqual(line['unitPrice'], 100.0)
        self.assertEqual(line['unitPriceBase'], 100.0)
        self.assertEqual(line['settlementAmount'], 0.0)
        self.assertEqual(invoice._l10n_ao_edi_payload_values()['documentTotals']['grossTotal'], invoice.amount_total)

    # --- envio --------------------------------------------------------------------------------------------

    def test_non_admin_can_sign_and_send(self):
        invoice = self._create_invoice()
        with self.mock_agt({'registarFactura': (200, {'requestID': 'R1', 'errorList': []})}):
            invoice.with_user(self._accountant()).action_l10n_ao_edi_send_now()
        self.assertEqual(invoice.l10n_ao_edi_state, 'sent')

    def test_already_registered_counts_as_received(self):
        invoice = self._create_invoice()
        error = {'documentNo': invoice.name, 'idError': 'E09', 'descriptionError': 'Já consta'}
        with self.mock_agt({'registarFactura': (200, {'requestID': 'R1', 'errorList': [error]})}):
            self.send_and_poll_send_only()
        self.assertEqual(invoice.l10n_ao_edi_state, 'sent')

    def test_document_missing_from_status_goes_back_to_queue(self):
        invoice = self._create_invoice()
        responses = {
            'registarFactura': (200, {'requestID': 'R1', 'errorList': []}),
            'obterEstado': (200, {'resultCode': '0', 'documentStatusList': []}),
        }
        with self.mock_agt(responses):
            self.send_and_poll()
        self.assertEqual(invoice.l10n_ao_edi_state, 'to_send')

    def test_failing_batch_does_not_block_queue(self):
        invoice = self._create_invoice()

        def boom(payload):
            raise ValueError('rede')

        with self.mock_agt({'registarFactura': boom}):
            self.send_and_poll_send_only()
        self.assertEqual(invoice.l10n_ao_edi_state, 'to_send')
        self.assertIn('rede', invoice.l10n_ao_edi_error)

    # --- séries -------------------------------------------------------------------------------------------

    def test_manual_activation_starts_at_first_authorized_number(self):
        series = self.env['l10n_ao_edi.series'].create(
            {'document_type': 'FG', 'year': TODAY.year, 'code': 'FG26P', 'first_number': 10001, 'last_number': 20000}
        )
        series.action_activate()
        self.assertEqual(series.next_number, 10001)

    def test_sync_series_continues_numbering_and_skips_closed(self):
        body = {
            'seriesInfo': [
                {
                    'seriesCode': 'GF26X',
                    'seriesYear': TODAY.year,
                    'documentType': 'GF',
                    'seriesStatus': 'U',
                    'invoicingMethod': 'FESF',
                    'firstDocumentApproved': '1',
                    'lastDocumentApproved': '1000',
                    'lastDocumentCreated': '57',
                },
                {'seriesCode': 'GF25F', 'seriesYear': TODAY.year - 1, 'documentType': 'GF', 'seriesStatus': 'F'},
                {'seriesCode': 'GF26P', 'seriesYear': TODAY.year, 'documentType': 'GF', 'invoicingMethod': 'FEPC'},
            ]
        }
        with self.mock_agt({'listarSeries': (200, body)}):
            self.env['l10n_ao_edi.series'].action_l10n_ao_edi_sync_series()
        Series = self.env['l10n_ao_edi.series']
        self.assertEqual(Series.search([('code', '=', 'GF26X')]).next_number, 58)
        self.assertFalse(Series.search([('code', 'in', ('GF25F', 'GF26P'))]))
        self.assertEqual(self.agt_calls[0][1]['establishmentNumber'], 'SEDE')
        log = self.env['l10n_ao_edi.document'].search([('service', '=', 'listarSeries')])
        self.assertEqual(log.state, 'done')

    # --- recibos ------------------------------------------------------------------------------------------

    def test_receipt_is_rg_and_frozen(self):
        invoice = self._create_invoice()
        self.mark_sent(invoice)
        payment = self.register_payment(invoice)
        self.assertTrue(payment.l10n_ao_edi_document_no.startswith('RG '))
        self.assertEqual(payment.l10n_ao_edi_source_move_ids, invoice)
        payload = payment._l10n_ao_edi_payload_values()
        self.assertEqual(payload['documentType'], 'RG')
        self.assertNotIn('lines', payload)
        with self.assertRaisesRegex(UserError, 'desconciliado'):
            payment.move_id.line_ids.remove_move_reconcile()

    def test_rejected_receipt_is_corrected(self):
        invoice = self._create_invoice()
        self.mark_sent(invoice)
        payment = self.register_payment(invoice)
        first = payment.l10n_ao_edi_document_no
        payment.l10n_ao_edi_state = 'invalid'
        payment.action_l10n_ao_edi_issue_receipt()
        self.assertNotEqual(payment.l10n_ao_edi_document_no, first)
        payload = payment._l10n_ao_edi_payload_values()
        self.assertEqual(payload['documentStatus'], 'C')
        self.assertEqual(payload['rejectedDocumentNo'], first)

    def test_receipt_waits_until_source_is_sent(self):
        invoice = self._create_invoice()
        payment = self.register_payment(invoice)
        self.assertTrue(payment.l10n_ao_edi_document_no)
        self.assertFalse(payment._l10n_ao_edi_ready_to_send())
        self.mark_sent(invoice)
        self.assertTrue(payment._l10n_ao_edi_ready_to_send())

    def test_partial_receipts_never_exceed_invoice(self):
        invoice = self._create_invoice()
        self.mark_sent(invoice)
        payments = [self.register_payment(invoice, amount=380.0) for _i in range(3)]
        nets = [p._l10n_ao_edi_payload_values()['documentTotals']['netTotal'] for p in payments]
        self.assertEqual(nets[:2], [333.33, 333.33])
        self.assertAlmostEqual(sum(nets), 1000.0, places=2)
