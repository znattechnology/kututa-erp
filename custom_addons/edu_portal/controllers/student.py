from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition


class StudentPortal(http.Controller):
    @http.route('/edu_portal/horario.pdf', type='http', auth='user', sitemap=False)
    def schedule_pdf(self, **kw):
        """O horário da turma do aluno em PDF (o documento da secretaria), aberto num separador. O aluno não lê as
        turmas, por isso o documento faz-se em sudo, só para a turma da sua matrícula."""
        Portal = request.env['edu.student.portal']
        student = Portal._student()
        enrollment = Portal._enrollment(student) if student else None
        if not enrollment:
            return request.not_found()
        report = request.env.ref('edu_documents.action_report_class_schedule').sudo()
        pdf, _type = report._render_qweb_pdf(report.report_name, enrollment.class_id.ids)
        name = f'Horario {enrollment.class_id._editor_label()}.pdf'
        return request.make_response(
            pdf,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf)),
                ('Content-Disposition', content_disposition(name, disposition_type='inline')),
            ],
        )
