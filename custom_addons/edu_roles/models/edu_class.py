from odoo import fields, models


class EduClass(models.Model):
    """Os números da turma para os cartões da secretaria: a designação curta, a ocupação das vagas e o estado do
    horário (os tempos, as aulas sem professor, ou sem horário quando o plano tem tempos)."""

    _inherit = 'edu.class'

    edu_label = fields.Char(string='Designação', compute='_compute_edu_card')
    edu_is_current = fields.Boolean(related='academic_year_id.is_current', string='Do ano em curso')
    edu_occupancy = fields.Integer(string='Ocupação (%)', compute='_compute_edu_card')
    edu_occupancy_width = fields.Integer(string='Ocupação (medidor)', compute='_compute_edu_card')
    edu_lessons = fields.Integer(string='Tempos no horário', compute='_compute_edu_card')
    edu_no_teacher = fields.Integer(string='Tempos sem professor', compute='_compute_edu_card')
    edu_no_schedule = fields.Boolean(string='Sem horário', compute='_compute_edu_card')

    def _compute_edu_card(self):
        for edu_class in self:
            schedules = edu_class._edu_current_schedules()
            # O ano de estágio não tem grelha semanal, nem um ano sem tempos no plano (como no painel).
            internship_year = (
                edu_class.course_id.requires_internship and edu_class.class_number == edu_class.curriculum_id.class_to
            )
            no_lessons_planned = internship_year or not edu_class.curriculum_year_id.weekly_hours
            edu_class.edu_label = edu_class._editor_label()
            edu_class.edu_occupancy = (
                round(100 * edu_class.student_count / edu_class.capacity) if edu_class.capacity else 0
            )
            edu_class.edu_occupancy_width = min(edu_class.edu_occupancy, 100)
            edu_class.edu_lessons = len(schedules)
            edu_class.edu_no_teacher = len(schedules.filtered(lambda s: not s.teacher_id))
            # Só o ano em curso precisa de horário: os anos passados ficam como foram.
            edu_class.edu_no_schedule = (
                edu_class.academic_year_id.is_current and not schedules and not no_lessons_planned
            )
