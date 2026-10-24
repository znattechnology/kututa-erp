from odoo import api, models


class ReportExamCalendar(models.AbstractModel):
    """O calendário de provas: quem o abre tem de poder ler o documento (o aluno, o da sua turma; o professor, a sua
    escala); a época e as sessões que mostra lêem-se depois em sudo. O acesso verifica-se ANTES do sudo: a rota dos
    relatórios não o faz."""

    _inherit = 'report.edu_documents.report_exam_calendar'

    @api.model
    def _get_report_values(self, docids, data=None):
        self.env['edu.exam.calendar.print'].browse(docids).check_access('read')
        return super(ReportExamCalendar, self.sudo())._get_report_values(docids, data)
