from odoo import api, fields, models
from odoo.addons.edu_timetable.models.edu_time_slot import format_hour

DAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']


class EduLesson(models.Model):
    """As aulas e sumários da secretaria em cartões: quando foi, a lição, quem a deu, o sumário e as faltas."""

    _inherit = 'edu.lesson'

    edu_when_label = fields.Char(string='Quando', compute='_compute_edu_labels')
    edu_class_label = fields.Char(string='Turma (curta)', compute='_compute_edu_labels')
    # Prevista com a data já passada: a aula não foi fechada (nem dada nem marcada como não realizada).
    edu_overdue = fields.Boolean(string='Por fechar', compute='_compute_edu_labels')

    @api.depends('date', 'hour_from', 'hour_to', 'class_id', 'state')
    def _compute_edu_labels(self):
        today = fields.Date.context_today(self)
        for lesson in self:
            day = lesson.date
            hours = f'{format_hour(lesson.hour_from)}–{format_hour(lesson.hour_to)}' if lesson.hour_to else ''
            lesson.edu_when_label = ' · '.join(
                p for p in [day and f'{DAYS[day.weekday()]}, {day.strftime("%d/%m")}', hours] if p
            )
            lesson.edu_class_label = lesson.class_id._editor_label() if lesson.class_id else False
            lesson.edu_overdue = lesson.state == 'scheduled' and bool(day) and day < today


class EduLessonAttendance(models.Model):
    """A justificação de faltas em cartões (secretaria e directores de turma): quando foi a falta, a turma e a
    disciplina, e «Justificar», que abre a justificação do período já com o aluno e o dia."""

    _inherit = 'edu.lesson.attendance'

    edu_when_label = fields.Char(string='Quando', compute='_compute_edu_labels')
    edu_class_label = fields.Char(string='Turma (curta)', compute='_compute_edu_labels')
    edu_student_name = fields.Char(related='student_id.name', string='Aluno (nome)')

    @api.depends('lesson_id.date', 'lesson_id.hour_from', 'lesson_id.hour_to', 'class_id')
    def _compute_edu_labels(self):
        for line in self:
            line.edu_when_label = line.lesson_id.edu_when_label
            line.edu_class_label = line.class_id._editor_label() if line.class_id else False

    def action_edu_justify(self):
        """Abre a justificação do período com o aluno e o dia da falta (o atestado pode cobrir mais dias)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Justificar faltas'),
            'res_model': 'edu.absence.justify',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_student_id': self.student_id.id,
                'default_date_from': self.date,
                'default_date_to': self.date,
            },
        }
