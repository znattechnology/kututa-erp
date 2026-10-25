from odoo import api, models
from odoo.exceptions import AccessError


class EduReportMixin(models.AbstractModel):
    """Os documentos da escola pelas moradas dos relatórios: o aluno só abre o horário da sua turma (o calendário de
    provas verifica o acesso no seu relatório, antes do sudo) e o encarregado só o RDEC dos educandos. As turmas e o
    pessoal lêem-se como utilizador interno, por isso sem esta verificação o aluno e o encarregado abriam o horário de
    qualquer turma ou a lista dos professores."""

    _inherit = 'edu.report.mixin'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not self.env.su and self.env.user._edu_guardian_only():
            # O encarregado só abre o RDEC dos educandos (o documento lê a turma e a escola: em sudo, depois de ver).
            if self._name == 'report.edu_documents.report_rdec':
                Portal = self.env['edu.guardian.portal']
                students = Portal._children()
                rdecs = self.env['edu.rdec'].sudo().browse(docids).exists()
                if (
                    docids
                    and len(rdecs) == len(docids)
                    and rdecs.student_id <= students
                    and not any(s._edu_gate('grades')[0] for s in rdecs.student_id)
                ):
                    return super(EduReportMixin, self.sudo())._get_report_values(docids, data)
            raise AccessError(self.env._('Este documento não está disponível na área do encarregado.'))
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
