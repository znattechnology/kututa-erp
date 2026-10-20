from odoo.tests import tagged

from .common import L10nAoEdiCommon


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestL10nAoEdiPrint(L10nAoEdiCommon):
    def render(self, report, records):
        content, _type = self.env['ir.actions.report']._render_qweb_pdf(report, records.ids)
        return content.decode()

    def test_invoice_original_then_copy(self):
        invoice = self._create_invoice()
        first = self.render('account.account_invoices', invoice)
        self.assertIn('Original', first)
        self.assertNotIn('2.ª via', first)
        second = self.render('account.account_invoices', invoice)
        self.assertIn('2.ª via', second)
        self.assertEqual(invoice.l10n_ao_edi_print_count, 2)

    def test_receipt_original_then_copy(self):
        invoice = self._create_invoice()
        self.mark_sent(invoice)
        payment = self.register_payment(invoice)
        self.assertIn('Original', self.render('account.action_report_payment_receipt', payment))
        self.assertIn('2.ª via', self.render('account.action_report_payment_receipt', payment))

    def test_draft_invoice_not_counted(self):
        invoice = self._create_invoice(post=False)
        self.render('account.account_invoices', invoice)
        self.assertEqual(invoice.l10n_ao_edi_print_count, 0)
