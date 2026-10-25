from odoo import api, fields, models
from odoo.exceptions import UserError

# O resultado do ano no passado, como no secPed (o ano já fechou), e a cor da linha.
RESULTS = {
    'promoted': ('Transitou', 'pos'),
    'graduated': ('Concluiu', 'pos'),
    'conditional': ('Transitou com disciplinas em atraso', 'pos'),
    'exam': ('Admitido a exame de recurso', 'warn'),
    'retained': ('Não transitou', 'neg'),
    'pending': ('Por decidir', 'muted'),
}
# Matrículas sem resultado do ano: em curso ou a saída da escola.
EXITS = {
    'active': ('Em curso', 'current'),
    'irregular': ('Em curso (irregular)', 'current'),
    'transferred': ('Transferido', 'muted'),
    'dropped': ('Anulou a matrícula', 'muted'),
    'completed': ('Sem decisão do conselho', 'muted'),
    'retained': ('Não transitou', 'neg'),
}


class EduHistoryPage(models.AbstractModel):
    """Página «Histórico do aluno» (acção cliente ``edu_documents.student_history``), como a do secPed-Express: o
    percurso do aluno na escola, um ano lectivo por linha (do primeiro ao último), com a turma, a média final, a
    assiduidade e o resultado; o ano em curso e as saídas (transferência, anulação) também são linhas. Daqui imprime-se
    o termo de cada ano e o termo do curso."""

    _name = 'edu.history.page'
    _description = 'Histórico do aluno'

    @api.model
    def _student(self, student_id):
        student = self.env['edu.student'].browse(student_id).exists()
        if not student:
            raise UserError(self.env._('O aluno já não existe.'))
        return student

    @api.model
    def student_history(self, student_id):
        student = self._student(student_id)
        enrollments = student.enrollment_ids.filtered(lambda e: e.state != 'draft').sorted(
            lambda e: (e.academic_year_id.date_start, e.date, e.id)
        )
        results = {r.enrollment_id.id: r for r in student.year_result_ids}
        rows = []
        for enrollment in enrollments:
            edu_class = enrollment.class_id
            result = results.get(enrollment.id)
            gone = enrollment.state in ('transferred', 'dropped')
            ongoing = enrollment.state in ('active', 'irregular') and (not result or result.status == 'pending')
            if result and not gone and not ongoing:
                label, tone = RESULTS.get(result.status, (result.status, 'muted'))
            else:
                # A saída e o ano em curso vêm da matrícula (um resultado «por decidir» do ano corrente não conta).
                label, tone = EXITS.get(enrollment.state, (enrollment.state, 'muted'))
            if enrollment.state in ('transferred', 'dropped') and enrollment.drop_date:
                label = f'{label} em {enrollment.drop_date.strftime("%d/%m/%Y")}'
            rows.append(
                {
                    'enrollment_id': enrollment.id,
                    'year': enrollment.academic_year_id.name,
                    'class': f'{edu_class.class_number}ª {edu_class.name}' if edu_class else '',
                    'course': edu_class.course_id.name or '',
                    'number': enrollment.order_number or '',
                    'average': round(result.average, 1) if result and result.status != 'pending' else None,
                    'attendance': result.attendance_rate if result and result.attendance_rate else None,
                    'result': label,
                    'tone': tone,
                    'year_result_id': result.id if result and not ongoing else False,
                    'status': result.status if result else False,
                    'manual': bool(result and result.manual),
                    'decision_note': self._decision_note(result) if result and result.manual else '',
                    'terminal': bool(result) and result._policy()._rules(result.class_id).terminal,
                }
            )
        last = enrollments[-1:]
        situation = ''
        if last:
            situation = self.env['edu.student.picker']._row(last)['state']
        return {
            'student': {
                'id': student.id,
                'name': student.name,
                'process_number': student.process_number or '',
                'class': last.class_id._editor_label() if last else '',
                'situation': situation,
            },
            'summary': student.history_summary,
            'rows': rows,
            'has_attendance': any(r['attendance'] for r in rows),
            'has_results': bool(student.year_result_ids),
            'can_decide': self.env.user.has_group('edu_core.group_edu_manager'),
        }

    @api.model
    def _decision_note(self, result):
        """«Decisão da direcção (Maria, 12/07/2026): fundamento»."""
        if not result.decided_by_id:
            # Decisões que vieram da migração (a pauta assinada): só o fundamento.
            return result.reason or self.env._('Decisão manual')
        # Na data local (a data guardada é UTC: perto da meia-noite em Luanda seria o dia errado).
        when = (
            fields.Datetime.context_timestamp(self, result.decided_date).strftime('%d/%m/%Y')
            if result.decided_date
            else ''
        )
        head = self.env._('Decisão da direcção (%s)', ', '.join(filter(None, [result.decided_by_id.name, when])))
        return f'{head}: {result.reason}' if result.reason else head

    @api.model
    def decide(self, year_result_id, status, reason):
        """A direcção altera a decisão do ano, com o fundamento (fica registado quem e quando)."""
        result = self.env['edu.year.result'].browse(year_result_id).exists()
        if not result:
            raise UserError(self.env._('Este ano ainda não tem resultado do conselho.'))
        result.manual_decide(status, reason)
        return self.student_history(result.student_id.id)

    @api.model
    def reset_decision(self, year_result_id):
        """Volta à decisão automática (a das regras, com as notas do ano)."""
        result = self.env['edu.year.result'].browse(year_result_id).exists()
        if not result:
            raise UserError(self.env._('Este ano ainda não tem resultado do conselho.'))
        result.action_reset_automatic()
        return self.student_history(result.student_id.id)

    @api.model
    def print_year_term(self, year_result_id):
        result = self.env['edu.year.result'].browse(year_result_id).exists()
        if not result:
            raise UserError(self.env._('Este ano ainda não tem resultado do conselho.'))
        return result.action_print_year_term()

    @api.model
    def print_course_term(self, student_id):
        student = self._student(student_id)
        if not student.year_result_ids:
            raise UserError(self.env._('%s ainda não tem anos no histórico.', student.name))
        return student.action_print_course_term()

    @api.model
    def subject_history(self, student_id):
        return self._student(student_id).action_view_subject_history()
