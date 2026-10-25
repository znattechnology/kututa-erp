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
