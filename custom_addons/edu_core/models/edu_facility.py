from odoo import api, fields, models
from odoo.exceptions import ValidationError

ROOM_TYPES = [
    ('classroom', 'Sala de aula'),
    ('laboratory', 'Laboratório'),
    ('science_lab', 'Laboratório de ciências'),
    ('computer_lab', 'Sala de informática'),
    ('workshop', 'Oficina'),
    ('library', 'Biblioteca'),
    ('gymnasium', 'Pavilhão / ginásio'),
    ('auditorium', 'Auditório'),
    ('office', 'Gabinete'),
    ('cafeteria', 'Refeitório'),
    ('other', 'Outro'),
]


class EduCampus(models.Model):
    _name = 'edu.campus'
    _description = 'Campus'
    _order = 'is_main desc, name'

    name = fields.Char(string='Campus', required=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    address = fields.Char(string='Morada')
    phone = fields.Char(string='Telefone')
    is_main = fields.Boolean(string='Principal')
    building_ids = fields.One2many('edu.building', 'campus_id', string='Edifícios')
    active = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint('UNIQUE(company_id, name)', 'Já existe um campus com este nome.')


class EduBuilding(models.Model):
    _name = 'edu.building'
    _description = 'Edifício'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string='Edifício', required=True)
    code = fields.Char(string='Código')
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    campus_id = fields.Many2one('edu.campus', check_company=True)
    floors = fields.Integer(string='Pisos')
    room_ids = fields.One2many('edu.room', 'building_id', string='Salas')
    active = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint('UNIQUE(company_id, name)', 'Já existe um edifício com este nome.')


class EduRoom(models.Model):
    _name = 'edu.room'
    _description = 'Sala'
    _order = 'code, name'
    _check_company_auto = True

    name = fields.Char(string='Sala', required=True)
    code = fields.Char(string='Código')
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    building_id = fields.Many2one('edu.building', string='Edifício', check_company=True)
    campus_id = fields.Many2one(
        'edu.campus',
        compute='_compute_campus_id',
        store=True,
        readonly=False,
        precompute=True,
        check_company=True,
    )
    floor = fields.Integer(string='Piso')
    room_type = fields.Selection(ROOM_TYPES, string='Tipo', required=True, default='classroom')
    capacity = fields.Integer(string='Lotação', default=30)
    has_projector = fields.Boolean(string='Projector')
    has_ac = fields.Boolean(string='Ar condicionado')
    note = fields.Text(string='Notas')
    active = fields.Boolean(default=True)

    _code_company_uniq = models.Constraint('UNIQUE(company_id, code)', 'Já existe uma sala com este código.')

    @api.depends('building_id')
    def _compute_campus_id(self):
        for room in self:
            if room.building_id.campus_id:
                room.campus_id = room.building_id.campus_id

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for room in self:
            room.display_name = f'{room.code} · {room.name}' if room.code and room.code != room.name else room.name

    @api.constrains('capacity')
    def _check_capacity(self):
        for room in self:
            if room.capacity < 0:
                raise ValidationError(self.env._('A lotação não pode ser negativa.'))


class EduShift(models.Model):
    _name = 'edu.shift'
    _description = 'Turno'
    _order = 'hour_from, name'

    name = fields.Char(string='Turno', required=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    shift_type = fields.Selection(
        [('morning', 'Manhã'), ('afternoon', 'Tarde'), ('evening', 'Noite'), ('full_day', 'Dia inteiro')],
        string='Período',
        required=True,
        default='morning',
    )
    hour_from = fields.Float(aggregator=None, string='Das', required=True, default=7.5)
    hour_to = fields.Float(aggregator=None, string='Às', required=True, default=12.5)
    active = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint('UNIQUE(company_id, name)', 'Já existe um turno com este nome.')

    @api.constrains('hour_from', 'hour_to')
    def _check_hours(self):
        for shift in self:
            if not 0 <= shift.hour_from < shift.hour_to <= 24:
                raise ValidationError(self.env._('As horas do turno %s não são válidas.', shift.name))
