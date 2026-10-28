from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import trusted


class EduSchedule(models.Model):
    _inherit = 'edu.schedule'

    def write(self, vals):
        result = super().write(vals)
        moved = {'weekday', 'hour_from', 'hour_to', 'time_slot_id', 'trimester_id', 'subject_id', 'class_id'}
        if moved & set(vals):
            self._edu_drop_future_lessons()
        elif {'teacher_id', 'room_id'} & set(vals):
            self._edu_sync_future_lessons()
        return result

    def _edu_future_lessons(self):
        """As aulas ainda por dar, sem chamada, de hoje em diante: as que o horário pode refazer."""
        return (
            self.env['edu.lesson']
            .sudo()
            .search(
                [
                    ('schedule_id', 'in', self.ids),
                    ('state', '=', 'scheduled'),
                    ('date', '>=', fields.Date.context_today(self)),
                ]
            )
            .filtered(lambda lesson: not lesson.attendance_ids)
        )

    def _edu_drop_future_lessons(self):
        """O tempo mudou de dia, de hora ou de disciplina: as aulas futuras geradas saem (voltam a gerar-se no sítio
        novo); as que já têm chamada ficam como estão."""
        self._edu_future_lessons().unlink()

    def _edu_sync_future_lessons(self):
        """Outro professor ou outra sala: as aulas futuras acompanham (com substituição, fica o substituto)."""
        for lesson in self._edu_future_lessons():
            schedule = lesson.schedule_id
            with trusted(self.env):
                lesson.write({'teacher_id': schedule._teacher_on(lesson.date).id, 'room_id': schedule.room_id.id})


class EduScheduleReplacement(models.Model):
    _inherit = 'edu.schedule.replacement'

    @api.model_create_multi
    def create(self, vals_list):
        replacements = super().create(vals_list)
        replacements._sync_lessons(replacements._lesson_keys())
        return replacements

    def write(self, vals):
        keys = self._lesson_keys()
        result = super().write(vals)
        self._sync_lessons(keys | self._lesson_keys())
        return result

    def unlink(self):
        keys = self._lesson_keys()
        result = super().unlink()
        self._sync_lessons(keys)
        return result

    def _lesson_keys(self):
        return {(replacement.schedule_id.id, replacement.date) for replacement in self}

    @api.model
    def _sync_lessons(self, keys):
        """A aula já gerada passa para o substituto (que faz a chamada e o sumário) ou volta ao professor da turma."""
        Lesson = self.env['edu.lesson'].sudo()
        for schedule_id, day in keys:
            schedule = self.env['edu.schedule'].browse(schedule_id).exists()
            if not schedule:
                continue
            teacher = schedule._teacher_on(day)
            lessons = Lesson.search([('schedule_id', '=', schedule.id), ('date', '=', day)])
            lessons.filtered(lambda lesson, t=teacher: lesson.teacher_id != t).write({'teacher_id': teacher.id})
