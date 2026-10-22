from odoo import api, models


class EduStudentPicker(models.AbstractModel):
    """Escolher um aluno nos documentos da secretaria (declarações, histórico), como o «EscolherAluno» do
    secPed-Express: no ano lectivo, pela turma (a lista dos alunos, pelo número) ou pelo nome. O ano conta porque
    quem já saiu da escola encontra-se no último ano em que esteve matriculado."""

    _name = 'edu.student.picker'
    _description = 'Escolher aluno'

    @api.model
    def picker_options(self, year_id=False):
        options = self.env['edu.grade.grid'].grid_classes(year_id)
        classes = self.env['edu.class'].sudo().browse([c['id'] for c in options['classes']])
        shifts = {c.id: c.shift_id.name or '' for c in classes}
        for row in options['classes']:
            row['shift'] = shifts.get(row['id'], '')
        return {'year_id': options['year_id'], 'years': options['years'], 'classes': options['classes']}

    @api.model
    def _enrollments(self, domain):
        return self.env['edu.enrollment'].search([('state', '!=', 'draft'), *domain])

    @api.model
    def _row(self, enrollment):
        return {
            'student_id': enrollment.student_id.id,
            'enrollment_id': enrollment.id,
            'name': enrollment.student_id.name,
            'number': enrollment.order_number or '',
            'class': enrollment.class_id._editor_label(),
            'state': dict(enrollment._fields['state']._description_selection(self.env))[enrollment.state],
            'gone': enrollment.state in ('dropped', 'transferred'),
        }

    @api.model
    def class_students(self, class_id):
        """Os alunos da turma, pelo número (quem saiu também)."""
        enrollments = self._enrollments([('class_id', '=', class_id)])
        return [self._row(e) for e in enrollments.sorted(lambda e: (e.order_number or 9999, e.student_id.name))]

    @api.model
    def search_students(self, year_id, query):
        """Pelo nome (ou n.º de processo), no ano lectivo."""
        query = (query or '').strip()
        if len(query) < 2:
            return []
        enrollments = self._enrollments(
            [
                ('academic_year_id', '=', year_id),
                '|',
                ('student_id.name', 'ilike', query),
                ('student_id.process_number', 'ilike', query),
            ]
        )
        return [self._row(e) for e in enrollments.sorted(lambda e: e.student_id.name)[:20]]
