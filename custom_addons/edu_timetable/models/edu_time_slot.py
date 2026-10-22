from odoo import api, fields, models
from odoo.exceptions import ValidationError


def format_hour(value):
    hours, minutes = divmod(round(value * 60), 60)
    return f'{hours:02d}:{minutes:02d}'


class EduTimeSlot(models.Model):
    _name = 'edu.time.slot'
    _description = 'Tempo lectivo'
    _order = 'shift_id, hour_from'
    _check_company_auto = True

    name = fields.Char(string='Tempo', required=True, help='Por exemplo, «1.º tempo».')
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    shift_id = fields.Many2one('edu.shift', string='Turno', required=True, index=True, check_company=True)
    hour_from = fields.Float(string='Das', required=True)
    hour_to = fields.Float(string='Às', required=True)
    is_break = fields.Boolean(string='Intervalo')
    active = fields.Boolean(default=True)

    _shift_hour_uniq = models.Constraint('UNIQUE(shift_id, hour_from)', 'O turno já tem um tempo a esta hora.')

    @api.depends('name', 'hour_from', 'hour_to')
    def _compute_display_name(self):
        for slot in self:
            hours = f'{format_hour(slot.hour_from)}–{format_hour(slot.hour_to)}'
            # A migração do secPed dá aos tempos o nome das horas («07:00–07:45»): não as repetir.
            slot.display_name = slot.name if slot.name.replace('-', '–') == hours else f'{slot.name} ({hours})'

    @api.constrains('hour_from', 'hour_to', 'shift_id')
    def _check_hours(self):
        for slot in self:
            if not 0 <= slot.hour_from < slot.hour_to <= 24:
                raise ValidationError(self.env._('As horas do tempo %s não são válidas.', slot.name))
            shift = slot.shift_id
            if slot.hour_from < shift.hour_from or slot.hour_to > shift.hour_to:
                raise ValidationError(
                    self.env._('O %(slot)s sai do horário do turno %(shift)s.', slot=slot.name, shift=shift.name)
                )
            overlap = self.search_count(
                [
                    ('shift_id', '=', shift.id),
                    ('id', '!=', slot.id),
                    ('hour_from', '<', slot.hour_to),
                    ('hour_to', '>', slot.hour_from),
                ]
            )
            if overlap:
                raise ValidationError(self.env._('Os tempos do turno %s sobrepõem-se.', shift.name))


class EduShift(models.Model):
    _inherit = 'edu.shift'

    time_slot_ids = fields.One2many('edu.time.slot', 'shift_id', string='Tempos lectivos')

    def action_generate_slots(self):
        """Grelha de tempos de 45 minutos com um intervalo de 15 minutos a meio do turno."""
        for shift in self:
            if shift.time_slot_ids:
                continue
            duration, pause = 0.75, 0.25
            count = int((shift.hour_to - shift.hour_from - pause) // duration)
            start = shift.hour_from
            vals = []
            for number in range(1, count + 1):
                vals.append(
                    {
                        'name': self.env._('%sº tempo', number),
                        'shift_id': shift.id,
                        'company_id': shift.company_id.id,
                        'hour_from': start,
                        'hour_to': start + duration,
                    }
                )
                start += duration
                if number == count // 2:
                    vals.append(
                        {
                            'name': self.env._('Intervalo'),
                            'shift_id': shift.id,
                            'company_id': shift.company_id.id,
                            'hour_from': start,
                            'hour_to': start + pause,
                            'is_break': True,
                        }
                    )
                    start += pause
            self.env['edu.time.slot'].create(vals)
        return True
