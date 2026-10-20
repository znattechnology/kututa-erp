from odoo.tests import tagged

from ..tools import jws_verify
from .common import L10nAoEdiCommon


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao_edi')
class TestL10nAoEdiReceipts(L10nAoEdiCommon):
    def test_payment_issues_receipt(self):
        invoice = self._create_invoice()  # 1000 + 14% = 1140
        payment = self.register_payment(invoice)
        self.assertEqual(payment.l10n_ao_edi_document_no, f'RC {self.series["RC"].code}/1')
        self.assertEqual(payment.l10n_ao_edi_state, 'to_send')
        receipt = payment._l10n_ao_edi_document_values()
        self.assertEqual(receipt['documentType'], 'RC')
        self.assertNotIn('lines', receipt)
        self.assertEqual(
            receipt['paymentReceipt']['sourceDocuments'],
            [
                {
                    'lineNo': 1,
                    'sourceDocumentID': {'OriginatingON': invoice.name, 'documentDate': str(invoice.invoice_date)},
                    'creditAmount': 1000.0,
                }
            ],
        )
        self.assertEqual(receipt['documentTotals'], {'taxPayable': 140.0, 'netTotal': 1000.0, 'grossTotal': 1140.0})
        public_pem = self.taxpayer_key._get_public_key_bytes(encoding='pem', formatting='raw')
        self.assertEqual(jws_verify(receipt['jwsDocumentSignature'], public_pem)['documentType'], 'RC')

    def test_partial_payment(self):
        invoice = self._create_invoice()
        payment = self.register_payment(invoice, amount=570.0)
        receipt = payment._l10n_ao_edi_document_values()
        self.assertEqual(receipt['paymentReceipt']['sourceDocuments'][0]['creditAmount'], 500.0)
        self.assertEqual(receipt['documentTotals'], {'taxPayable': 70.0, 'netTotal': 500.0, 'grossTotal': 570.0})

    def test_withholding_reported_on_receipt(self):
        """Cliente retém 6,5% de Imposto Industrial sobre o serviço (base sem IVA): 65 Kz em 34.1.2."""
        invoice = self._create_invoice()
        account = self.env['account.account'].search(
            [*self.env['account.account']._check_company_domain(self.company), ('code', '=', '34.1.2')]
        )
        payment = self.register_payment(
            invoice,
            amount=1075.0,
            payment_difference_handling='reconcile',
            writeoff_account_id=account.id,
            writeoff_label='Retenção na fonte 6,5%',
        )
        receipt = payment._l10n_ao_edi_document_values()
        self.assertEqual(receipt['documentTotals']['grossTotal'], 1140.0, 'O recibo liquida a factura toda')
        self.assertEqual(len(receipt['withholdingTaxList']), 1)
        self.assertEqual(receipt['withholdingTaxList'][0]['withholdingTaxType'], 'II')
        self.assertEqual(receipt['withholdingTaxList'][0]['withholdingTaxAmount'], 65.0)

    def test_invoice_receipt_needs_no_receipt(self):
        invoice = self._create_invoice(post=False)
        invoice.l10n_ao_document_type = 'FR'
        invoice.action_post()
        payment = self.register_payment(invoice)
        self.assertFalse(payment.l10n_ao_edi_document_no, 'A Factura/Recibo já é o recibo')

    def test_receipt_waits_for_its_invoice(self):
        invoice = self._create_invoice()
        payment = self.register_payment(invoice)
        calls = []

        def register(payload):
            calls.append([document['documentNo'] for document in payload['documents']])
            return 200, {'requestID': f'2026000000000{len(calls)}', 'errorList': []}

        with self.mock_agt({'registarFactura': register}):
            Document = self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)
            Document._cron_send()
            Document._cron_send()
        self.assertEqual(calls, [[invoice.name], [payment.l10n_ao_edi_document_no]])
        self.assertEqual(payment.l10n_ao_edi_state, 'sent')

    def test_sent_receipt_locks_payment(self):
        invoice = self._create_invoice()
        payment = self.register_payment(invoice)
        self.mark_sent(payment)
        with self.assertRaisesRegex(Exception, 'comunicado à AGT'):
            payment.action_draft()
