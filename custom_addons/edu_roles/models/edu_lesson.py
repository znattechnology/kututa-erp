from odoo import api, fields, models
from odoo.addons.edu_attendance.models.absence_rules import GENERAL
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


class EduAbsenceSummary(models.Model):
    """O resumo de faltas em cartões: as injustificadas que contam numa barra face ao limite da lei (por trimestre no
    geral, no ano no técnico), com as justificadas e os atrasos ao lado."""

    _inherit = 'edu.absence.summary'

    edu_class_label = fields.Char(string='Turma (curta)', compute='_compute_edu_meter')
    edu_student_name = fields.Char(related='student_id.name', string='Aluno (nome)')
    edu_meter = fields.Integer(string='Barra (%)', compute='_compute_edu_meter')
    edu_meter_label = fields.Char(string='Faltas que contam', compute='_compute_edu_meter')

    @api.depends('status', 'counted', 'limit')
    def _compute_edu_meter(self):
        for summary in self:
            summary.edu_class_label = summary.class_id._editor_label() if summary.class_id else False
            if not summary.limit:
                summary.edu_meter = 0
                summary.edu_meter_label = self.env._('%s injustificadas (sem limite por disciplina)', summary.counted)
                continue
            general = summary.class_id.sudo()._edu_regime() == GENERAL
            # No geral retém ao atingir o limite; no técnico reprova ao passar o máximo.
            failing = summary.limit if general else summary.limit + 1
            summary.edu_meter = min(100, round(summary.counted * 100 / failing))
            summary.edu_meter_label = (
                self.env._('%(count)s de %(limit)s no trimestre (retido com %(limit)s)', count=summary.counted,
                           limit=summary.limit)
                if general
                else self.env._('%(count)s no ano (máximo %(limit)s)', count=summary.counted, limit=summary.limit)
            )  # fmt: skip

    def action_edu_open_absences(self):
        """As faltas do aluno nesta disciplina, na justificação de faltas."""
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('edu_attendance.action_edu_lesson_attendance')
        action['domain'] = [
            ('enrollment_id', '=', self.enrollment_id.id),
            ('subject_id', '=', self.subject_id.id),
            ('state', 'in', ('absent', 'excused')),
            ('lesson_state', '=', 'done'),
        ]
        action['context'] = {}
        action['name'] = f'{self.student_id.name} · {self.subject_id.name}'
        return action


class EduExamSession(models.Model):
    """As sessões de exame em cartões: a hora, a disciplina, as turmas, a sala e o vigilante."""

    _inherit = 'edu.exam.session'

    edu_time_label = fields.Char(string='Hora', compute='_compute_edu_labels')
    edu_class_label = fields.Char(string='Turmas (curto)', compute='_compute_edu_labels')

    @api.depends('date', 'hour_from', 'hour_to', 'class_ids')
    def _compute_edu_labels(self):
        for session in self:
            day = session.date
            hours = f'{format_hour(session.hour_from)}–{format_hour(session.hour_to)}'
            session.edu_time_label = f'{DAYS[day.weekday()]}, {day.strftime("%d/%m")} · {hours}' if day else hours
            session.edu_class_label = ', '.join(c._editor_label() for c in session.class_ids) or False
