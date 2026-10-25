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


class EduRoom(models.Model):
    """A ocupação da sala no ano em curso, pelos horários, para os cartões da secretaria: as turmas que lá têm aulas
    em cada turno (com as aulas por semana e o aviso quando a turma é maior do que a lotação), o uso semanal face
    aos tempos lectivos dos turnos (de segunda a sexta) e os turnos em que está livre."""

    _inherit = 'edu.room'

    edu_usage = fields.Json(string='Ocupação (cartão)', compute='_compute_edu_usage')
    edu_week_used = fields.Integer(string='Aulas por semana', compute='_compute_edu_usage')
    edu_week_total = fields.Integer(string='Tempos por semana', compute='_compute_edu_usage')
    edu_week_width = fields.Integer(string='Uso semanal (%)', compute='_compute_edu_usage')
    edu_free_shifts = fields.Char(string='Livre', compute='_compute_edu_usage')

    def _compute_edu_usage(self):
        shifts = self.env['edu.shift'].sudo().search([('company_id', 'in', self.env.companies.ids)])
        schedules = (
            self.env['edu.schedule']
            .sudo()
            .search([('room_id', 'in', self.ids), ('class_id.academic_year_id.is_current', '=', True)])
        )
        for room in self:
            mine = schedules.filtered(lambda s, r=room: s.room_id == r)
            rows = {}
            for schedule in mine:
                edu_class = schedule.class_id
                row = rows.setdefault(
                    edu_class.id,
                    {
                        'id': edu_class.id,
                        'shift': edu_class.shift_id.name or '',
                        'hour': edu_class.shift_id.hour_from,
                        'label': edu_class._editor_label(),
                        'students': edu_class.student_count,
                        'over': bool(room.capacity) and edu_class.student_count > room.capacity,
                        'lessons': 0,
                    },
                )
                row['lessons'] += 1
            usage = sorted(rows.values(), key=lambda r: (r['hour'], r['label']))
            for row in usage:
                row.pop('hour')
            room.edu_usage = usage
            own_shifts = shifts.filtered(lambda s, c=room.company_id: s.company_id == c)
            total = 5 * sum(len(s.time_slot_ids.filtered(lambda t: not t.is_break)) for s in own_shifts)
            room.edu_week_used = len(mine)
            room.edu_week_total = total
            room.edu_week_width = min(100, round(100 * len(mine) / total)) if total else 0
            used = mine.class_id.shift_id
            room.edu_free_shifts = ', '.join(own_shifts.filtered(lambda s, u=used: s not in u).mapped('name'))
