from odoo import api, models


class ReportL10nAoReportsFinancial(models.AbstractModel):
    _name = 'report.l10n_ao_reports.report_financial'
    _description = 'Demonstrações financeiras PGC (impressão)'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['l10n_ao_reports.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'l10n_ao_reports.wizard',
            'docs': wizards,
            'reports': [wizard._get_report_data() for wizard in wizards],
        }
