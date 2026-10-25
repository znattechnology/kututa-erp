from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .edu_time_slot import format_hour

WEEKDAYS = [
    ('0', 'Segunda-feira'),
    ('1', 'Terça-feira'),
    ('2', 'Quarta-feira'),
    ('3', 'Quinta-feira'),
    ('4', 'Sexta-feira'),
    ('5', 'Sábado'),
    ('6', 'Domingo'),
]


class EduSchedule(models.Model):
    """Tempo do horário semanal da turma. Cada linha é um tempo lectivo e conta para a carga semanal do plano."""

    _name = 'edu.schedule'
    _description = 'Horário (tempo semanal)'
    _order = 'class_id, weekday, hour_from'
    _check_company_auto = True

    class_id = fields.Many2one(
        'edu.class', string='Turma', required=True, index=True, ondelete='cascade', check_company=True
    )
    company_id = fields.Many2one(related='class_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='class_id.academic_year_id', store=True, index=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, index=True, check_company=True)
    teacher_id = fields.Many2one(
        'hr.employee',
        string='Professor(a)',
        compute='_compute_teacher_id',
        store=True,
        readonly=False,
        precompute=True,
        index=True,
        check_company=True,
        domain="[('edu_is_teacher', '=', True)]",
    )
    room_id = fields.Many2one(
        'edu.room',
        string='Sala',
        compute='_compute_room_id',
        store=True,
        readonly=False,
        precompute=True,
        check_company=True,
    )
    trimester_id = fields.Many2one(
        'edu.trimester',
        string='Trimestre',
        domain="[('academic_year_id', '=', academic_year_id)]",
        help='Vazio: o ano lectivo inteiro.',
    )
    weekday = fields.Selection(WEEKDAYS, string='Dia', required=True, default='0')
    time_slot_id = fields.Many2one(
        'edu.time.slot',
        string='Tempo',
        domain="[('is_break', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
    hour_from = fields.Float(
        aggregator=None,
        string='Das',
        compute='_compute_hours',
        store=True,
        readonly=False,
        precompute=True,
        required=True,
    )
    hour_to = fields.Float(
        aggregator=None,
        string='Às',
        compute='_compute_hours',
        store=True,
        readonly=False,
        precompute=True,
        required=True,
    )
    exception_ids = fields.One2many('edu.schedule.exception', 'schedule_id', string='Aulas sem realização')
    replacement_ids = fields.One2many('edu.schedule.replacement', 'schedule_id', string='Substituições')

    @api.depends('class_id', 'subject_id', 'trimester_id')
    def _compute_teacher_id(self):
        for schedule in self:
            if schedule.class_id and schedule.subject_id and not schedule.teacher_id:
                schedule.teacher_id = schedule._assigned_teacher()

    def _assigned_teacher(self):
        """O professor colocado: o do trimestre do tempo, se o houver, senão o do ano."""
        self.ensure_one()
        day = self.trimester_id.date_start or None
        return self.env['edu.teaching.assignment']._teacher_for(self.class_id, self.subject_id, day=day)

    def write(self, vals):
        result = super().write(vals)
        if {'subject_id', 'class_id', 'trimester_id'} & set(vals) and 'teacher_id' not in vals:
            # Outra disciplina (ou turma, ou trimestre): o professor é o dessa colocação.
            for schedule in self:
                schedule.teacher_id = schedule._assigned_teacher()
        return result

    @api.depends('class_id')
    def _compute_room_id(self):
        for schedule in self:
            if not schedule.room_id:
                schedule.room_id = schedule.class_id.room_id

    @api.depends('time_slot_id')
    def _compute_hours(self):
        for schedule in self:
            if schedule.time_slot_id:
                schedule.hour_from = schedule.time_slot_id.hour_from
                schedule.hour_to = schedule.time_slot_id.hour_to

    @api.depends('subject_id', 'weekday', 'hour_from', 'hour_to', 'class_id')
    @api.depends_context('edu_schedule_show_class')
    def _compute_display_name(self):
        days = dict(WEEKDAYS)
        show_class = self.env.context.get('edu_schedule_show_class')
        for schedule in self:
            name = (
                f'{days.get(schedule.weekday, "")} {format_hour(schedule.hour_from)}-'
                f'{format_hour(schedule.hour_to)} · {schedule.subject_id.name or ""}'
            )
            if show_class and schedule.class_id:
                name = f'{name} · {schedule.class_id.display_name}'
            schedule.display_name = name

    def _overlapping(self, field_name):
        """Outros tempos no mesmo dia e hora, com o mesmo valor em ``field_name``, em trimestres que se cruzam."""
        self.ensure_one()
        domain = [
            ('id', '!=', self.id),
            (field_name, '=', self[field_name].id),
            ('academic_year_id', '=', self.academic_year_id.id),
            ('weekday', '=', self.weekday),
            ('hour_from', '<', self.hour_to),
            ('hour_to', '>', self.hour_from),
        ]
        if self.trimester_id:
            domain.append(('trimester_id', 'in', [False, self.trimester_id.id]))
        return self.search(domain, limit=1)

    @api.constrains('class_id', 'teacher_id', 'room_id', 'weekday', 'hour_from', 'hour_to', 'trimester_id')
    def _check_conflicts(self):
        for schedule in self:
            if not 0 <= schedule.hour_from < schedule.hour_to <= 24:
                raise ValidationError(self.env._('As horas do tempo não são válidas.'))
            if schedule.weekday == '6':
                raise ValidationError(self.env._('Não há aulas ao domingo.'))
            if schedule.trimester_id and schedule.trimester_id.academic_year_id != schedule.academic_year_id:
                raise ValidationError(self.env._('O trimestre não é do ano lectivo da turma.'))
            subjects = schedule.class_id.subject_line_ids.subject_id
            if subjects and schedule.subject_id not in subjects:
                raise ValidationError(self.env._('%s não faz parte do plano da turma.', schedule.subject_id.name))
            checks = [
                ('class_id', self.env._('A turma %(name)s já tem %(other)s.')),
                ('teacher_id', self.env._('O(A) professor(a) %(name)s já está ocupado(a): %(other)s.')),
                ('room_id', self.env._('A sala %(name)s já está ocupada: %(other)s.')),
            ]
            # Migração: o horário afixado entra como está, com os choques de professor e de sala; ficam no relatório.
            if self.env.context.get('edu_schedule_import'):
                checks = checks[:1]
            for field_name, message in checks:
                if not schedule[field_name]:
                    continue
                clash = schedule._overlapping(field_name)
                if clash:
                    raise ValidationError(
                        message
                        % {
                            'name': schedule[field_name].display_name,
                            'other': f'{clash.display_name} ({clash.class_id.display_name})',
                        }
                    )
            # O professor não pode ter, à mesma hora, uma substituição marcada noutra turma.
            if schedule.teacher_id and not self.env.context.get('edu_schedule_import'):
                busy = self.env['edu.schedule.replacement'].search(
                    [
                        ('replacement_teacher_id', '=', schedule.teacher_id.id),
                        ('date', '>=', fields.Date.context_today(self)),
                        ('schedule_id', '!=', schedule.id),
                        ('schedule_id.weekday', '=', schedule.weekday),
                        ('schedule_id.hour_from', '<', schedule.hour_to),
                        ('schedule_id.hour_to', '>', schedule.hour_from),
                    ],
                    limit=1,
                )
                if busy and schedule._occurs_on(busy.date):
                    raise ValidationError(
                        self.env._(
                            '%(teacher)s tem uma substituição a essa hora: %(other)s.',
                            teacher=schedule.teacher_id.name,
                            other=busy.display_name,
                        )
                    )

    def _occurs_on(self, day):
        """O tempo realiza-se nesta data: dia da semana, trimestre e sem excepção registada."""
        self.ensure_one()
        if str(day.weekday()) != self.weekday:
            return False
        if self.trimester_id and not self.trimester_id.date_start <= day <= self.trimester_id.date_end:
            return False
        year = self.academic_year_id
        if not year.date_start <= day <= year.date_end:
            return False
        return not self.exception_ids.filtered(lambda e: e.date == day)

    def _teacher_on(self, day):
        """Professor que dá a aula nesta data (o substituto, se houver)."""
        self.ensure_one()
        replacement = self.replacement_ids.filtered(lambda r: r.date == day)
        return replacement.replacement_teacher_id if replacement else self.teacher_id


class EduScheduleException(models.Model):
    _name = 'edu.schedule.exception'
    _description = 'Aula sem realização'
    _order = 'date desc'

    schedule_id = fields.Many2one('edu.schedule', string='Tempo', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='schedule_id.company_id', store=True)
    date = fields.Date(string='Data', required=True)
    reason = fields.Char(string='Motivo', help='Feriado, greve, actividade da escola…')

    _schedule_date_uniq = models.Constraint('UNIQUE(schedule_id, date)', 'Já está registado para esta data.')

    @api.constrains('date', 'schedule_id')
    def _check_date(self):
        for exception in self:
            if str(exception.date.weekday()) != exception.schedule_id.weekday:
                raise ValidationError(self.env._('Nesta data não há este tempo no horário.'))


class EduScheduleReplacement(models.Model):
    _name = 'edu.schedule.replacement'
    _description = 'Substituição de professor'
    _order = 'date desc'
    _check_company_auto = True

    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    weekday = fields.Char(compute='_compute_weekday')
    # Gravados a partir do tempo (nunca diferentes dele): a lista, a pesquisa e a carga lectiva paga lêem-nos.
    class_id = fields.Many2one(related='schedule_id.class_id', string='Turma', store=True, index=True)
    original_teacher_id = fields.Many2one(
        related='schedule_id.teacher_id', string='Professor(a) que falta', store=True, index=True
    )
    # Só para escolher a aula no formulário: a turma, o professor que falta, ou os dois.
    filter_class_id = fields.Many2one(
        'edu.class', string='Turma ', compute='_compute_filters', readonly=False, store=False
    )
    filter_teacher_id = fields.Many2one(
        'hr.employee',
        string='Professor(a) que falta ',
        compute='_compute_filters',
        readonly=False,
        store=False,
        domain="[('edu_is_teacher', '=', True)]",
    )
    schedule_id = fields.Many2one(
        'edu.schedule',
        string='Aula',
        required=True,
        ondelete='cascade',
        index=True,
        domain="[('weekday', '=', weekday), ('class_id', '=?', filter_class_id), "
        "('teacher_id', '=?', filter_teacher_id), ('academic_year_id.date_start', '<=', date), "
        "('academic_year_id.date_end', '>=', date)]",
    )
    company_id = fields.Many2one(related='schedule_id.company_id', store=True)
    replacement_teacher_id = fields.Many2one(
        'hr.employee',
        string='Substituto(a)',
        required=True,
        check_company=True,
        domain="[('edu_is_teacher', '=', True), ('id', 'in', free_teacher_ids)]",
    )
    reason = fields.Char(string='Motivo')
    # Para escolher o substituto: só os professores livres a essa hora (sem aula e sem outra substituição).
    # No perfil público (a secretaria não lê a ficha dos funcionários); os ids são os mesmos de hr.employee.
    free_teacher_ids = fields.Many2many(
        'hr.employee.public', string='Professores livres', compute='_compute_free_teacher_ids'
    )
    # O quadro das substituições mostra a aula sem a abrir.
    subject_id = fields.Many2one(related='schedule_id.subject_id', string='Disciplina')
    hour_from = fields.Float(related='schedule_id.hour_from', string='Das', store=True)  # ordena o quadro
    time_label = fields.Char(string='Hora', compute='_compute_labels')
    class_label = fields.Char(string='Turma (curta)', compute='_compute_labels')

    _schedule_date_uniq = models.Constraint('UNIQUE(schedule_id, date)', 'Esta aula já tem substituto nesta data.')

    @api.depends('date')
    def _compute_weekday(self):
        for replacement in self:
            replacement.weekday = str(replacement.date.weekday()) if replacement.date else False

    @api.depends('schedule_id')
    def _compute_filters(self):
        for replacement in self:
            replacement.filter_class_id = replacement.schedule_id.class_id
            replacement.filter_teacher_id = replacement.schedule_id.teacher_id

    @api.depends('schedule_id')
    def _compute_labels(self):
        for replacement in self:
            schedule = replacement.schedule_id
            replacement.time_label = (
                f'{format_hour(schedule.hour_from)} – {format_hour(schedule.hour_to)}' if schedule else False
            )
            replacement.class_label = schedule.class_id._editor_label() if schedule.class_id else False

    @api.depends('schedule_id', 'date')
    def _compute_free_teacher_ids(self):
        Public = self.env['hr.employee.public']
        for replacement in self:
            schedule = replacement.schedule_id.sudo()
            if not schedule or not replacement.date:
                replacement.free_teacher_ids = Public
                continue
            teachers = (
                self.env['hr.employee']
                .sudo()
                .search([('edu_is_teacher', '=', True), ('company_id', '=', schedule.company_id.id)])
            )
            free = teachers - schedule.teacher_id - replacement.sudo()._busy_teachers()
            replacement.free_teacher_ids = Public.browse(free.ids)

    def _busy_teachers(self):
        """Os professores com aula ou outra substituição à hora desta aula, nesta data."""
        self.ensure_one()
        schedule, day = self.schedule_id, self.date
        lessons = self.env['edu.schedule'].search(
            [
                ('weekday', '=', schedule.weekday),
                ('hour_from', '<', schedule.hour_to),
                ('hour_to', '>', schedule.hour_from),
                ('company_id', '=', schedule.company_id.id),
                ('id', '!=', schedule.id),
            ]
        )
        busy = self.env['hr.employee'].union(*[lesson._teacher_on(day) for lesson in lessons if lesson._occurs_on(day)])
        others = self.search(
            [
                ('id', '!=', self._origin.id or 0),
                ('date', '=', day),
                ('schedule_id.hour_from', '<', schedule.hour_to),
                ('schedule_id.hour_to', '>', schedule.hour_from),
            ]
        )
        return busy | others.replacement_teacher_id

    @api.depends('schedule_id', 'date')
    def _compute_display_name(self):
        for replacement in self:
            schedule = replacement.schedule_id.with_context(edu_schedule_show_class=True)
            day = replacement.date.strftime('%d/%m/%Y') if replacement.date else ''
            replacement.display_name = f'{day} · {schedule.display_name}' if schedule else day

    @api.constrains('date', 'schedule_id', 'replacement_teacher_id')
    def _check_replacement(self):
        for replacement in self:
            schedule = replacement.schedule_id
            if not schedule._occurs_on(replacement.date):
                raise ValidationError(self.env._('Nesta data não há esta aula.'))
            off = self.env['edu.calendar.event']._days_without_lessons(
                schedule.company_id, schedule.class_id.level_id, replacement.date, replacement.date
            )
            if off:
                raise ValidationError(self.env._('Nesta data não há aulas (feriado ou pausa do calendário escolar).'))
            if replacement.replacement_teacher_id == schedule.teacher_id:
                raise ValidationError(self.env._('O substituto é o próprio professor da turma.'))
            busy = self.env['edu.schedule'].search(
                [
                    ('teacher_id', '=', replacement.replacement_teacher_id.id),
                    ('weekday', '=', schedule.weekday),
                    ('hour_from', '<', schedule.hour_to),
                    ('hour_to', '>', schedule.hour_from),
                ]
            )
            teacher = replacement.replacement_teacher_id
            if any(
                other._occurs_on(replacement.date) and other._teacher_on(replacement.date) == teacher for other in busy
            ):
                raise ValidationError(self.env._('%s tem aula a essa hora.', replacement.replacement_teacher_id.name))
            other = self.search(
                [
                    ('id', '!=', replacement.id),
                    ('date', '=', replacement.date),
                    ('replacement_teacher_id', '=', teacher.id),
                    ('schedule_id.hour_from', '<', schedule.hour_to),
                    ('schedule_id.hour_to', '>', schedule.hour_from),
                ],
                limit=1,
            )
            if other:
                raise ValidationError(
                    self.env._('%(teacher)s já substitui outra aula a essa hora: %(other)s.', teacher=teacher.name,
                               other=other.display_name)
                )  # fmt: skip
