from odoo import api, models


class ReportPayslip(models.AbstractModel):
    """Recibo de salário: o trabalhador abre os seus recibos fechados (a regra de acesso do recibo); o contrato, a folha
    do mês e a conta bancária que o recibo mostra lêem-se em sudo (no Odoo 20 o cargo e o departamento vêm do
    contrato). O acesso verifica-se ANTES do sudo: a rota dos relatórios não o faz."""

    _name = 'report.l10n_ao_payroll.report_payslip'
    _description = 'Recibo de salário'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['l10n_ao_payroll.payslip'].browse(docids)
        docs.check_access('read')
        return {'doc_ids': docids, 'doc_model': 'l10n_ao_payroll.payslip', 'docs': docs.sudo(), 'data': data}
