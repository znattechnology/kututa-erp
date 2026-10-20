from odoo import models

# Relatórios dos documentos AGT: facturas (todos os relatórios de factura) e recibos.
PAYMENT_RECEIPT_REPORT = 'account.report_payment_receipt'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _l10n_ao_edi_printed_documents(self, report_ref, res_ids):
        report = self._get_report(report_ref)
        if self._is_invoice_report(report_ref):
            records = self.env['account.move'].browse(res_ids)
            return records.filtered('l10n_ao_edi_series_id')
        if report.report_name == PAYMENT_RECEIPT_REPORT:
            records = self.env['account.payment'].browse(res_ids)
            return records.filtered('l10n_ao_edi_document_no')
        return None

    def _pre_render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """Cada PDF de um documento AGT conta como impressão: o primeiro é o «Original», os seguintes a «2.ª via»."""
        ids = [res_ids] if isinstance(res_ids, int) else res_ids or []
        if documents := self._l10n_ao_edi_printed_documents(report_ref, ids):
            for document in documents.sudo():
                document.l10n_ao_edi_print_count += 1
        return super()._pre_render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
