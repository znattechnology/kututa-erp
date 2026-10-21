from odoo.tests import tagged

from ..tools import jws_verify
from .common import L10nAoEdiCommon


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao_edi')
class TestL10nAoEdiPayload(L10nAoEdiCommon):
    def test_invoice_document_structure(self):
        invoice = self._create_invoice(
            lines=[(self.service, 2, 100.01, self.vat14), (self.goods, 1, 500.0, self.exempt_m21)],
        )
        document = invoice._l10n_ao_edi_document_values()
        self.assertEqual(document['documentNo'], invoice.name)
        self.assertEqual(document['documentStatus'], 'N')
        self.assertEqual(document['documentType'], 'FT')
        self.assertEqual(document['customerTaxID'], '5000000002')
        self.assertEqual(document['customerCountry'], 'AO')
        line1, line2 = document['lines']
        self.assertEqual(line1['operationType'], 'SG')
        self.assertEqual(line2['operationType'], 'TB')
        self.assertEqual(line1['creditAmount'], 200.02)
        self.assertEqual(
            line1['taxes'],
            [
                {
                    'taxType': 'IVA',
                    'taxCountryRegion': 'AO',
                    'taxCode': 'NOR',
                    'taxPercentage': 14.0,
                    'taxContribution': 28.01,
                }
            ],
        )
        self.assertEqual(line2['taxes'][0]['taxCode'], 'ISE')
        self.assertEqual(line2['taxes'][0]['taxExemptionCode'], 'M21')
        self.assertEqual(document['documentTotals'], {'taxPayable': 28.01, 'netTotal': 700.02, 'grossTotal': 728.03})
        # Os totais enviados à AGT coincidem com os da factura (imposto arredondado por excesso, regra AGT).
        self.assertEqual(invoice.amount_total, 728.03)

    def test_document_signature(self):
        invoice = self._create_invoice()
        document = invoice._l10n_ao_edi_document_values()
        public_pem = self.taxpayer_key._get_public_key_bytes(encoding='pem', formatting='raw')
        signed = jws_verify(document['jwsDocumentSignature'], public_pem)
        self.assertEqual(
            list(signed),
            [
                'documentNo',
                'taxRegistrationNumber',
                'documentType',
                'documentDate',
                'customerTaxID',
                'customerCountry',
                'companyName',
                'documentTotals',
            ],
        )
        self.assertEqual(signed['documentNo'], invoice.name)
        self.assertEqual(signed['taxRegistrationNumber'], '5000000001')
        self.assertEqual(signed['documentTotals'], document['documentTotals'])

    def test_final_consumer_without_nif(self):
        invoice = self._create_invoice(partner=self.consumer)
        self.assertEqual(invoice._l10n_ao_edi_document_values()['customerTaxID'], '999999999')
        # O documento impresso identifica o adquirente como consumidor final (DP 71/25).
        self.assertEqual(invoice._get_document_partner_ident_line(), 'NIF: Consumidor final')

    def test_credit_note_references_origin(self):
        invoice = self._create_invoice()
        invoice.l10n_ao_edi_state = 'valid'
        wizard = (
            self.env['account.move.reversal']
            .with_context(active_model='account.move', active_ids=invoice.ids)
            .create({'reason': 'Anulação: serviço não prestado ao cliente final', 'journal_id': invoice.journal_id.id})
        )
        refund = self.env['account.move'].browse(wizard.refund_moves()['res_id'])
        self.assertTrue(refund.name_placeholder.startswith(f'NC {self.series["NC"].code}/'))
        refund.action_post()
        line = refund._l10n_ao_edi_document_values()['lines'][0]
        self.assertIn('debitAmount', line)
        self.assertNotIn('creditAmount', line)
        self.assertEqual(
            line['referenceInfo'],
            {'reference': invoice.name, 'reason': 'Anulação: serviço não prestado ao cliente final'},
            'O motivo vai sem o prefixo «Estorno de: …» do Odoo',
        )

    def test_qr_code_url(self):
        invoice = self._create_invoice()
        self.assertEqual(
            invoice.l10n_ao_edi_qr_url,
            'https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe'
            f'?emissor=5000000001&document=FT%20{self.series["FT"].code}/1',
        )

    def test_printed_document_title(self):
        invoice = self._create_invoice()
        html = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', invoice.ids)[0].decode()
        self.assertIn('Factura', html)
        self.assertIn(invoice.name, html)
        self.assertNotIn('Proforma', html)
        self.assertIn('Data de emissão', html)
        self.assertIn('Processado por programa validado', html)
        self.assertIn('/report/barcode/?barcode_type=QR', html)
