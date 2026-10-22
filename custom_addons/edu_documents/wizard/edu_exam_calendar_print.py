from odoo import fields, models

WEEKDAYS = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
MONTHS = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro',
    'Dezembro',
]  # fmt: skip


def hour(value):
    hours, minutes = divmod(round((value or 0) * 60), 60)
    return f'{hours:02d}:{minutes:02d}'


class EduExamCalendarPrint(models.TransientModel):
    """O calendário de provas de uma turma (para afixar e dar aos alunos) ou a escala de vigilância de um professor,
    como no secPed-Express: as provas da época por dia, com a hora, a disciplina, quem vigia (ou a turma) e a sala;
    o cabeçalho e as assinaturas da pauta."""

    _name = 'edu.exam.calendar.print'
    _description = 'Calendário de provas para imprimir'

    period_id = fields.Many2one('edu.exam.period', string='Época', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='period_id.company_id')
    class_id = fields.Many2one('edu.class', string='Turma')
    teacher_id = fields.Many2one('hr.employee', string='Professor')

    def _sessions(self):
        self.ensure_one()
        sessions = self.period_id.session_ids.filtered(lambda s: s.state != 'cancelled')
        if self.class_id:
            sessions = sessions.filtered(lambda s: self.class_id in s.class_ids)
        else:
            sessions = sessions.filtered(lambda s: self.teacher_id in s.room_ids.supervisor_ids)
        return sessions.sorted(lambda s: (s.date, s.hour_from, s.id))

    def _calendar_doc(self):
        self.ensure_one()
        period = self.period_id
        teacher = self.teacher_id.sudo()
        days = []
        for session in self._sessions():
            label = f'{WEEKDAYS[session.date.weekday()]}, {session.date.day} de {MONTHS[session.date.month - 1]}'
            if not days or days[-1]['date'] != session.date:
                days.append({'date': session.date, 'label': label, 'rows': []})
            days[-1]['rows'].append(
                {
                    'hours': f'{hour(session.hour_from)}–{hour(session.hour_to)}',
                    'subject': session.subject_id.name,
                    'middle': session.supervisor_label
                    if self.class_id
                    else ', '.join(c._editor_label() for c in session.class_ids),
                    'room': session.room_label or '—',
                }
            )
        span = f'{period.name} ({period.date_start.strftime("%d/%m")} a {period.date_end.strftime("%d/%m/%Y")})'
        if self.class_id:
            title = 'CALENDÁRIO DE PROVAS'
            context = self.class_id._document_context(span)
        else:
            title = 'ESCALA DE VIGILÂNCIA'
            context = f'PROFESSOR(A): {teacher.name}  {span}  ANO LECTIVO: {period.academic_year_id.name}'
        return {
            'title': title,
            'context': context,
            'middle': 'Vigilante' if self.class_id else 'Turma',
            'days': days,
            'signatures': bool(self.class_id),
        }


class EduExamPeriod(models.Model):
    _inherit = 'edu.exam.period'

    def planner_print(self, kind, res_id):
        """«Imprimir» do calendário de provas: o da turma ou a escala do professor, visualizado na aplicação."""
        self.ensure_one()
        self._planner_check()
        vals = {'period_id': self.id, 'class_id' if kind == 'class' else 'teacher_id': res_id}
        document = self.env['edu.exam.calendar.print'].create(vals)
        return self.env.ref('edu_documents.action_report_exam_calendar').preview_action(document)
