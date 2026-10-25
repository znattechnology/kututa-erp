from odoo import api, fields, models

ENROLLED = ('active', 'irregular')
# A régua do dia nos cartões dos turnos: das 6h às 23h.
DAY_START, DAY_END = 6.0, 23.0


def _hhmm(value):
    hours, minutes = divmod(round(value * 60), 60)
    return f'{hours:02d}:{minutes:02d}'


def _pct(value):
    return round(100 * (min(max(value, DAY_START), DAY_END) - DAY_START) / (DAY_END - DAY_START), 2)


class EduShift(models.Model):
    """Os números do turno para os cartões da secretaria: as horas, a duração, a faixa na régua do dia com os tempos
    lectivos, e as turmas e os alunos do ano em curso."""

    _inherit = 'edu.shift'

    edu_hours = fields.Char(string='Horário', compute='_compute_edu_band')
    edu_duration = fields.Char(string='Duração', compute='_compute_edu_band')
    edu_band = fields.Json(string='Régua do dia', compute='_compute_edu_band')
    edu_slot_count = fields.Integer(string='Tempos lectivos', compute='_compute_edu_band')
    edu_class_count = fields.Integer(string='Turmas', compute='_compute_edu_counts')
    edu_student_count = fields.Integer(string='Alunos', compute='_compute_edu_counts')

    @api.depends('hour_from', 'hour_to', 'time_slot_ids.hour_from', 'time_slot_ids.hour_to', 'time_slot_ids.is_break')
    def _compute_edu_band(self):
        for shift in self:
            minutes = round((shift.hour_to - shift.hour_from) * 60)
            hours, rest = divmod(minutes, 60)
            shift.edu_hours = f'{_hhmm(shift.hour_from)}–{_hhmm(shift.hour_to)}'
            shift.edu_duration = f'{hours} h {rest:02d}' if rest else f'{hours} h'
            slots = shift.time_slot_ids.sorted('hour_from')
            shift.edu_slot_count = len(slots.filtered(lambda s: not s.is_break))
            start, end = _pct(shift.hour_from), _pct(shift.hour_to)
            shift.edu_band = {
                'left': start,
                'width': round(end - start, 2),
                'slots': [
                    {
                        'id': slot.id,
                        'left': round(100 * (slot.hour_from - shift.hour_from) / (shift.hour_to - shift.hour_from), 2),
                        'width': round(100 * (slot.hour_to - slot.hour_from) / (shift.hour_to - shift.hour_from), 2),
                        'break': slot.is_break,
                        'title': f'{slot.name}: {_hhmm(slot.hour_from)}–{_hhmm(slot.hour_to)}',
                    }
                    for slot in slots
                ]
                if shift.hour_to > shift.hour_from
                else [],
            }

    def _compute_edu_counts(self):
        Class = self.env['edu.class'].sudo()
        Enrollment = self.env['edu.enrollment'].sudo()
        for shift in self:
            classes = Class.search([('shift_id', '=', shift.id), ('academic_year_id.is_current', '=', True)])
            shift.edu_class_count = len(classes)
            shift.edu_student_count = (
                Enrollment.search_count([('class_id', 'in', classes.ids), ('state', 'in', ENROLLED)]) if classes else 0
            )


class EduTimeSlot(models.Model):
    """Os números do tempo lectivo para os cartões da secretaria: as horas, a duração, a posição dentro do turno e
    quantas aulas por semana o horário do ano em curso tem neste tempo."""

    _inherit = 'edu.time.slot'

    edu_hours = fields.Char(string='Horas', compute='_compute_edu_band')
    edu_duration = fields.Char(string='Duração', compute='_compute_edu_band')
    edu_band = fields.Json(string='No turno', compute='_compute_edu_band')
    edu_lesson_count = fields.Integer(string='Aulas por semana', compute='_compute_edu_lesson_count')

    @api.depends('hour_from', 'hour_to', 'shift_id.hour_from', 'shift_id.hour_to')
    def _compute_edu_band(self):
        for slot in self:
            shift = slot.shift_id
            slot.edu_hours = f'{_hhmm(slot.hour_from)}–{_hhmm(slot.hour_to)}'
            slot.edu_duration = f'{round((slot.hour_to - slot.hour_from) * 60)} min'
            span = (shift.hour_to - shift.hour_from) or 1
            slot.edu_band = {
                'left': round(100 * (slot.hour_from - shift.hour_from) / span, 2),
                'width': round(100 * (slot.hour_to - slot.hour_from) / span, 2),
            }

    def _compute_edu_lesson_count(self):
        groups = (
            self.env['edu.schedule']
            .sudo()
            ._read_group(
                [('time_slot_id', 'in', self.ids), ('class_id.academic_year_id.is_current', '=', True)],
                ['time_slot_id'],
                ['__count'],
            )
        )
        counts = {slot.id: count for slot, count in groups}
        for slot in self:
            slot.edu_lesson_count = counts.get(slot.id, 0)
