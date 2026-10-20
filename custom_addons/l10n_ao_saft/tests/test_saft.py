from datetime import date

from lxml import etree

from odoo import Command
from odoo.addons.l10n_ao_edi.tests.common import TODAY, L10nAoEdiCommon
from odoo.exceptions import UserError
from odoo.tests import tagged

NS = {'s': 'urn:OECD:StandardAuditFile-Tax:AO_1.01_01'}


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao')
class TestL10nAoSaft(L10nAoEdiCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.write(
            {'l10n_ao_saft_producer_tax_id': '5000000009', 'street': 'Rua Major Kanhangulo', 'city': 'Luanda'}
        )
        cls.supplier = cls.env['res.partner'].create(
            {'name': 'Fornecedor, Lda', 'country_id': cls.env.ref('base.ao').id, 'vat': '5000000003'}
        )

    def _export(self, file_type):
        wizard = self.env['l10n_ao_saft.export'].create(
            {'file_type': file_type, 'date_from': date(TODAY.year, 1, 1), 'date_to': date(TODAY.year, 12, 31)}
        )
        return etree.fromstring(wizard._generate())

    def _scenario(self):
        invoice = self._create_invoice(
            lines=[(self.service, 2, 1000.0, self.vat14), (self.goods, 1, 500.0, self.exempt_m21)]
        )
        self.mark_sent(invoice)
        refund = invoice._reverse_moves(
            [{'invoice_date': TODAY, 'l10n_ao_edi_reason': 'Devolução de artigos'}], cancel=False
        )
        refund.action_post()
        self.mark_sent(refund)
        paid = self._create_invoice()
        self.mark_sent(paid)
        payment = self.register_payment(paid, amount=1000.0)
        bill = self.env['account.move'].create(
            {
                'move_type': 'in_invoice',
                'partner_id': self.supplier.id,
                'ref': 'FT A/123',
                'invoice_date': TODAY,
                'invoice_line_ids': [
                    Command.create(
                        {
                            'name': 'Papel',
                            'quantity': 1,
                            'price_unit': 300.0,
                            'tax_ids': [self._ao_tax('ao_iva_purchase_14').id],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return invoice, refund, payment, bill, paid

    def test_integrated_file_is_valid(self):
        invoice, refund, payment, bill, paid = self._scenario()
        root = self._export('I')
        self.assertEqual(root.findtext('s:Header/s:TaxAccountingBasis', namespaces=NS), 'I')
        self.assertEqual(root.findtext('s:Header/s:TaxRegistrationNumber', namespaces=NS), '5000000001')
        self.assertEqual(root.findtext('s:Header/s:ProductCompanyTaxID', namespaces=NS), '5000000009')
        # Programa ainda sem número de validação no formato NNN/AGT/AAAA
        self.assertEqual(root.findtext('s:Header/s:SoftwareValidationNumber', namespaces=NS), '0')
        invoices = root.findall('s:SourceDocuments/s:SalesInvoices/s:Invoice', NS)
        numbers = [node.findtext('s:InvoiceNo', namespaces=NS) for node in invoices]
        self.assertEqual(sorted(numbers), sorted([invoice.name, refund.name, paid.name]))
        ft = invoices[numbers.index(invoice.name)]
        self.assertEqual(ft.findtext('s:DocumentTotals/s:GrossTotal', namespaces=NS), '2780.00')
        self.assertTrue(ft.findtext('s:TransactionID', namespaces=NS))
        exempt = ft.findall('s:Line', NS)[1]
        self.assertEqual(exempt.findtext('s:TaxExemptionCode', namespaces=NS), 'M21')
        nc = invoices[numbers.index(refund.name)]
        self.assertEqual(nc.findtext('s:Line/s:References/s:Reference', namespaces=NS), invoice.name)
        self.assertIsNotNone(nc.find('s:Line/s:DebitAmount', NS))
        receipts = root.findall('s:SourceDocuments/s:Payments/s:Payment', NS)
        self.assertEqual(
            [r.findtext('s:PaymentRefNo', namespaces=NS) for r in receipts], [payment.l10n_ao_edi_document_no]
        )
        self.assertEqual(receipts[0].findtext('s:PaymentType', namespaces=NS), 'RG')
        purchases = root.findall('s:SourceDocuments/s:PurchaseInvoices/s:Invoice', NS)
        self.assertEqual([p.findtext('s:InvoiceNo', namespaces=NS) for p in purchases], ['FT A/123'])
        self.assertEqual(purchases[0].findtext('s:DocumentTotals/s:GrossTotal', namespaces=NS), '342.00')
        customer_ids = {c.findtext('s:CustomerID', namespaces=NS) for c in root.findall('s:MasterFiles/s:Customer', NS)}
        self.assertIn(str(self.partner_ao.id), customer_ids)
        products = {p.findtext('s:ProductCode', namespaces=NS) for p in root.findall('s:MasterFiles/s:Product', NS)}
        self.assertEqual(products, {'CONS', 'CAD'})
        self.assertTrue(bill)

    def test_accounting_file(self):
        self._scenario()
        root = self._export('C')
        self.assertIsNone(root.find('s:SourceDocuments', NS))
        ledger = root.find('s:GeneralLedgerEntries', NS)
        self.assertEqual(
            ledger.findtext('s:TotalDebit', namespaces=NS), ledger.findtext('s:TotalCredit', namespaces=NS)
        )
        entries = int(ledger.findtext('s:NumberOfEntries', namespaces=NS))
        self.assertEqual(entries, len(ledger.findall('s:Journal/s:Transaction', NS)))
        accounts = {
            a.findtext('s:AccountID', namespaces=NS): a
            for a in root.findall('s:MasterFiles/s:GeneralLedgerAccounts/s:Account', NS)
        }
        self.assertEqual(accounts['31'].findtext('s:GroupingCategory', namespaces=NS), 'GR')
        self.assertEqual(accounts['31.1.2.1'].findtext('s:GroupingCategory', namespaces=NS), 'GM')
        self.assertEqual(accounts['31.1.2.1'].findtext('s:GroupingCode', namespaces=NS), '31.1.2')
        # A conta-mãe agrega os saldos das subcontas
        self.assertEqual(
            accounts['31'].findtext('s:ClosingDebitBalance', namespaces=NS),
            accounts['31.1'].findtext('s:ClosingDebitBalance', namespaces=NS),
        )
        supplier_ids = {s.findtext('s:SupplierID', namespaces=NS) for s in root.findall('s:MasterFiles/s:Supplier', NS)}
        self.assertEqual(supplier_ids, {str(self.supplier.id)})

    def test_invoicing_file(self):
        self._scenario()
        root = self._export('F')
        self.assertEqual(root.findtext('s:Header/s:TaxEntity', namespaces=NS), 'Global')
        self.assertIsNone(root.find('s:GeneralLedgerEntries', NS))
        self.assertIsNone(root.find('s:SourceDocuments/s:PurchaseInvoices', NS))
        self.assertEqual(len(root.findall('s:SourceDocuments/s:SalesInvoices/s:Invoice', NS)), 3)

    def test_requires_producer_and_single_year(self):
        self.company.l10n_ao_saft_producer_tax_id = False
        with self.assertRaisesRegex(UserError, 'produtor'):
            self._export('C')
        self.company.l10n_ao_saft_producer_tax_id = '5000000009'
        wizard = self.env['l10n_ao_saft.export'].create(
            {'file_type': 'C', 'date_from': date(TODAY.year - 1, 6, 1), 'date_to': date(TODAY.year, 1, 31)}
        )
        with self.assertRaisesRegex(UserError, 'mais do que um exercício'):
            wizard._generate()
