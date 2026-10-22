from odoo import api, models


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
        Lesson = self.env['edu.lesson'].sudo().with_context(edu_lesson_system=True)
        for schedule_id, day in keys:
            schedule = self.env['edu.schedule'].browse(schedule_id).exists()
            if not schedule:
                continue
            teacher = schedule._teacher_on(day)
            lessons = Lesson.search([('schedule_id', '=', schedule.id), ('date', '=', day)])
            lessons.filtered(lambda lesson, t=teacher: lesson.teacher_id != t).write({'teacher_id': teacher.id})
