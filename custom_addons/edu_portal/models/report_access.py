from odoo import api, models
from odoo.exceptions import AccessError


class EduReportMixin(models.AbstractModel):
    """Os documentos da escola pelas moradas dos relatórios: o aluno só abre o horário da sua turma (o calendário de
    provas verifica o acesso no seu relatório, antes do sudo). As turmas e o pessoal lêem-se como utilizador interno,
    por isso sem esta verificação o aluno abria o horário de qualquer turma ou a lista dos professores."""

    _inherit = 'edu.report.mixin'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not self.env.su and self.env.user._edu_student_only():
            allowed = False
            if self._name == 'report.edu_documents.report_class_schedule':
                Portal = self.env['edu.student.portal']
                student = Portal._student()
                classes = Portal._enrollment(student).class_id if student else self.env['edu.class']
                allowed = bool(docids) and set(docids) <= set(classes.ids)
            if not allowed:
                raise AccessError(self.env._('Este documento não está disponível na área do estudante.'))
        return super()._get_report_values(docids, data)
