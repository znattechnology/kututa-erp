from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import is_marked, trusted
from odoo.exceptions import AccessError, UserError, ValidationError

from .absence_rules import AT_RISK, FAILED

ATTENDANCE_STATES = [
    ('present', 'Presente'),
    ('late', 'Atraso'),
    ('absent', 'Falta injustificada'),
    ('excused', 'Falta justificada'),
]
ENROLLED = ('active', 'irregular')


class EduLesson(models.Model):
    """Aula dada (lição): a partir de um tempo do horário ou aberta pelo professor, com sumário e chamada."""

    _name = 'edu.lesson'
    _description = 'Aula (sumário)'
    _inherit = ['mail.thread']
    _order = 'date desc, hour_from, id'
    _check_company_auto = True

    class_id = fields.Many2one('edu.class', string='Turma', required=True, index=True, check_company=True)
    company_id = fields.Many2one(related='class_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='class_id.academic_year_id', store=True, index=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, index=True, check_company=True)
    schedule_id = fields.Many2one('edu.schedule', string='Tempo do horário', index=True, check_company=True)
    teacher_id = fields.Many2one(
        'hr.employee',
        string='Professor(a)',
        compute='_compute_from_schedule',
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
        compute='_compute_from_schedule',
        store=True,
        readonly=False,
        precompute=True,
        check_company=True,
    )
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today, index=True)
    hour_from = fields.Float(
        aggregator=None, string='Das', compute='_compute_from_schedule', store=True, readonly=False, precompute=True
    )
    hour_to = fields.Float(
        aggregator=None, string='Às', compute='_compute_from_schedule', store=True, readonly=False, precompute=True
    )
    trimester_id = fields.Many2one(
        'edu.trimester', string='Trimestre', compute='_compute_trimester_id', store=True, index=True
    )
    state = fields.Selection(
        [('scheduled', 'Prevista'), ('done', 'Dada'), ('cancelled', 'Não realizada')],
        string='Estado',
        default='scheduled',
        required=True,
        tracking=True,
    )
    lesson_number = fields.Integer(
        string='Lição n.º', readonly=True, copy=False, help='Numeração das aulas dadas da disciplina na turma.'
    )
    summary = fields.Text(string='Sumário', tracking=True)
    note = fields.Text(string='Observações')
    attendance_ids = fields.One2many('edu.lesson.attendance', 'lesson_id', string='Chamada')
    absent_count = fields.Integer(string='Faltas', compute='_compute_counts')
    present_count = fields.Integer(string='Presenças', compute='_compute_counts')

    _schedule_date_uniq = models.UniqueIndex(
        '(schedule_id, date) WHERE schedule_id IS NOT NULL', 'Já existe esta aula do horário nesta data.'
    )

    @api.depends('schedule_id', 'date')
    def _compute_from_schedule(self):
        for lesson in self:
            schedule = lesson.schedule_id
            if not schedule:
                if not lesson.room_id:
                    lesson.room_id = lesson.class_id.room_id
                continue
            lesson.teacher_id = schedule._teacher_on(lesson.date) if lesson.date else schedule.teacher_id
            lesson.room_id = schedule.room_id
            lesson.hour_from = schedule.hour_from
            lesson.hour_to = schedule.hour_to

    @api.depends('date', 'academic_year_id.trimester_ids.date_start', 'academic_year_id.trimester_ids.date_end')
    def _compute_trimester_id(self):
        for lesson in self:
            lesson.trimester_id = lesson.academic_year_id.trimester_ids.filtered(
                lambda t, day=lesson.date: day and t.date_start <= day <= t.date_end
            )[:1]

    def _renumber(self):
        """Numera as aulas dadas da disciplina na turma por ordem de data (as não realizadas ficam sem número)."""
        for class_id, subject_id in {(lesson.class_id.id, lesson.subject_id.id) for lesson in self}:
            lessons = self.sudo().search(
                [('class_id', '=', class_id), ('subject_id', '=', subject_id)], order='date, hour_from, id'
            )
            number = 0
            for lesson in lessons:
                if lesson.state == 'done':
                    number += 1
                    value = number
                else:
                    value = 0
                if lesson.lesson_number != value:
                    with trusted(self.env):
                        lesson.write({'lesson_number': value})

    @api.depends('attendance_ids.state')
    def _compute_counts(self):
        for lesson in self:
            lesson.absent_count = len(lesson.attendance_ids.filtered(lambda a: a.state in ('absent', 'excused')))
            lesson.present_count = len(lesson.attendance_ids.filtered(lambda a: a.state in ('present', 'late')))

    @api.depends('subject_id', 'class_id', 'date', 'lesson_number')
    def _compute_display_name(self):
        for lesson in self:
            number = f' · Lição {lesson.lesson_number}' if lesson.lesson_number else ''
            lesson.display_name = (
                f'{lesson.subject_id.name or ""} · {lesson.class_id.display_name or ""} · '
                f'{lesson.date.strftime("%d/%m/%Y") if lesson.date else ""}{number}'
            )

    @api.constrains('date', 'class_id', 'schedule_id', 'subject_id')
    def _check_lesson(self):
        for lesson in self:
            year = lesson.academic_year_id
            if not year.date_start <= lesson.date <= year.date_end:
                raise ValidationError(self.env._('A data da aula sai do ano lectivo %s.', year.name))
            schedule = lesson.schedule_id
            if schedule:
                if schedule.class_id != lesson.class_id or schedule.subject_id != lesson.subject_id:
                    raise ValidationError(self.env._('O tempo do horário é de outra turma ou disciplina.'))
                if str(lesson.date.weekday()) != schedule.weekday:
                    raise ValidationError(self.env._('Nesta data não há este tempo no horário.'))
            subjects = lesson.class_id.subject_line_ids.subject_id
            if subjects and lesson.subject_id not in subjects:
                raise ValidationError(self.env._('%s não faz parte do plano da turma.', lesson.subject_id.name))

    # ------------------------------------------------------------------
    # Permissões do professor
    # ------------------------------------------------------------------
    def _check_open_trimester(self):
        """Com o trimestre fechado, as aulas e as faltas já não mudam (as retenções por faltas dependem delas)."""
        closed = self.filtered(lambda lesson: lesson.trimester_id.state == 'closed')
        if closed:
            raise UserError(
                self.env._(
                    'O %s está fechado: as aulas e as faltas já não se alteram. A direcção pode reabri-lo.',
                    closed[0].trimester_id.name,
                )
            )

    def _check_can_manage(self):
        """O professor gere as aulas das disciplinas em que está colocado e, se for director, as da sua turma."""
        if self.env.su or self.env.user.has_group('edu_core.group_edu_user'):
            return
        employee = self.env.user.employee_id
        for lesson in self:
            # Uma colocação só num trimestre dá as aulas desse trimestre (vazia: o ano inteiro).
            assigned = (
                self.env['edu.teaching.assignment']
                .sudo()
                .search_count(
                    [
                        ('class_id', '=', lesson.class_id.id),
                        ('subject_id', '=', lesson.subject_id.id),
                        ('teacher_id', '=', employee.id),
                        '|',
                        ('trimester_id', '=', False),
                        ('trimester_id', '=', lesson.trimester_id.id),
                    ]
                )
            )
            director = lesson.class_id.sudo().director_id == employee
            # O professor que a secretaria pôs no tempo do horário dá essa aula.
            scheduled = bool(lesson.schedule_id) and lesson.schedule_id.sudo().teacher_id == employee
            # Substituto só com a substituição registada para esse tempo e data (pôr-se como professor não basta).
            substitute = bool(
                lesson.schedule_id
                and self.env['edu.schedule.replacement']
                .sudo()
                .search_count(
                    [
                        ('schedule_id', '=', lesson.schedule_id.id),
                        ('date', '=', lesson.date),
                        ('replacement_teacher_id', '=', employee.id),
                    ]
                )
            )
            if not (employee and (assigned or director or scheduled or substitute)):
                raise AccessError(self.env._('Só o professor da disciplina ou o director de turma gere esta aula.'))

    @api.model_create_multi
    def create(self, vals_list):
        lessons = super().create(vals_list)
        lessons._check_can_manage()
        lessons._check_open_trimester()
        lessons.filtered(lambda lesson: lesson.state == 'done')._renumber()
        return lessons

    def write(self, vals):
        # Geração e renumeração das aulas pelo próprio sistema: marca do servidor, não contexto do cliente.
        system = is_marked(self.env)
        if not system:
            self._check_can_manage()
        locked = {'state', 'date', 'hour_from', 'hour_to', 'class_id', 'subject_id', 'summary'} & set(vals)
        if locked and not system:
            self._check_open_trimester()
        result = super().write(vals)
        if locked and not system:
            self._check_open_trimester()
        if {'state', 'date', 'hour_from'} & set(vals):
            self._renumber()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_without_attendance(self):
        if self.attendance_ids:
            raise UserError(self.env._('A aula já tem chamada: marque-a como não realizada.'))

    # ------------------------------------------------------------------
    def _enrollments(self):
        self.ensure_one()
        return self.env['edu.enrollment']._for_class_subject(self.class_id, self.subject_id)

    def action_open_roll_call(self):
        """Abre a chamada: uma linha por aluno matriculado na disciplina, todos presentes por omissão."""
        self._check_can_manage()
        self._check_open_trimester()
        for lesson in self:
            if lesson.state == 'cancelled':
                raise UserError(self.env._('A aula não se realizou.'))
            missing = lesson._enrollments() - lesson.attendance_ids.enrollment_id
            self.env['edu.lesson.attendance'].sudo().create(
                [{'lesson_id': lesson.id, 'enrollment_id': enrollment.id} for enrollment in missing]
            )
        return True

    def action_done(self):
        today = fields.Date.context_today(self)
        for lesson in self:
            if lesson.date > today:
                raise UserError(self.env._('A aula de %s ainda não aconteceu.', lesson.date.strftime('%d/%m/%Y')))
            if not (lesson.summary or '').strip():
                raise UserError(self.env._('Escreva o sumário antes de dar a aula por dada: %s.', lesson.display_name))
            if not lesson.attendance_ids:
                lesson.action_open_roll_call()
            lesson.state = 'done'
            lesson.attendance_ids._edu_check_limits()
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_reset(self):
        self.write({'state': 'scheduled'})
        return True

    @api.model
    def _generate(self, classes, date_from, date_to):
        """Cria as aulas previstas do horário entre duas datas. Salta as aulas sem realização registadas, os feriados e
        as pausas do calendário escolar e os trimestres fechados."""
        return self.create(self._generate_vals(classes, date_from, date_to))

    @api.model
    def _generate_vals(self, classes, date_from, date_to):
        """As aulas que ``_generate`` criaria (para dizer quantas antes de as criar)."""
        existing = {
            (lesson.schedule_id.id, lesson.date)
            for lesson in self.search(
                [('class_id', 'in', classes.ids), ('date', '>=', date_from), ('date', '<=', date_to)]
            )
        }
        Calendar = self.env['edu.calendar.event']
        holidays = {}
        vals = []
        for schedule in classes.schedule_ids:
            edu_class = schedule.class_id
            key = (edu_class.company_id, edu_class.level_id)
            if key not in holidays:
                holidays[key] = Calendar._days_without_lessons(*key, date_from, date_to)
            closed = schedule.academic_year_id.trimester_ids.filtered(lambda t: t.state == 'closed')
            day = max(date_from, schedule.academic_year_id.date_start)
            end = min(date_to, schedule.academic_year_id.date_end)
            while day <= end:
                if (
                    schedule._occurs_on(day)
                    and (schedule.id, day) not in existing
                    and day not in holidays[key]
                    and not any(t.date_start <= day <= t.date_end for t in closed)
                ):
                    vals.append(
                        {
                            'class_id': schedule.class_id.id,
                            'subject_id': schedule.subject_id.id,
                            'schedule_id': schedule.id,
                            'date': day,
                        }
                    )
                day += timedelta(days=1)
        return vals


class EduLessonAttendance(models.Model):
    _name = 'edu.lesson.attendance'
    _description = 'Presença na aula'
    _order = 'lesson_id, order_number, id'
    _check_company_auto = True

    lesson_id = fields.Many2one('edu.lesson', string='Aula', required=True, ondelete='cascade', index=True)
    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True, index=True, check_company=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, index=True)
    order_number = fields.Integer(related='enrollment_id.order_number', store=True, string='N.º', aggregator=False)
    company_id = fields.Many2one(related='lesson_id.company_id', store=True, index=True)
    subject_id = fields.Many2one(related='lesson_id.subject_id', store=True, index=True)
    class_id = fields.Many2one(related='lesson_id.class_id', store=True, index=True)
    trimester_id = fields.Many2one(related='lesson_id.trimester_id', store=True, index=True)
    date = fields.Date(related='lesson_id.date', store=True)
    lesson_state = fields.Selection(related='lesson_id.state', store=True, string='Estado da aula')
    state = fields.Selection(ATTENDANCE_STATES, string='Presença', required=True, default='present')
    justification = fields.Char(string='Motivo da justificação')
    justified_by_id = fields.Many2one('res.users', string='Justificada por', readonly=True, copy=False)
    justified_date = fields.Date(string='Justificada em', readonly=True, copy=False)
    note = fields.Char(string='Notas')
    can_justify = fields.Boolean(string='Pode justificar', compute='_compute_can_justify')

    _lesson_enrollment_uniq = models.Constraint(
        'UNIQUE(lesson_id, enrollment_id)', 'O aluno já está na chamada desta aula.'
    )

    @api.constrains('enrollment_id', 'lesson_id')
    def _check_enrollment(self):
        for line in self:
            lesson = line.lesson_id
            # Também os alunos de outra turma que fazem a disciplina nesta (Decreto Executivo 60/08, arts. 9.º e 10.º).
            visiting = line.enrollment_id.lower_subject_ids.filtered(
                lambda s, lesson=lesson: s.class_id == lesson.class_id and s.subject_id == lesson.subject_id
            )
            if line.enrollment_id.class_id != lesson.class_id and not visiting:
                raise ValidationError(self.env._('%s não é desta turma.', line.student_id.name))

    @api.depends_context('uid')
    def _compute_can_justify(self):
        for line in self:
            line.can_justify = line._can_justify()

    def _can_justify(self):
        """Justificam as faltas só a secretaria (e a direcção) e o director de turma do aluno."""
        if self.env.su or self.env.user.has_group('edu_core.group_edu_user'):
            return True
        employee = self.env.user.employee_id
        return bool(employee) and employee == self.enrollment_id.class_id.sudo().director_id

    def _check_can_justify(self):
        for line in self:
            if not line._can_justify():
                raise AccessError(
                    self.env._(
                        'Só a secretaria e o director de turma justificam faltas (%s): marque a falta como '
                        'injustificada.',
                        line.student_id.name,
                    )
                )

    def _check_can_manage(self):
        """Quem gere a aula gere a chamada; o director de turma do aluno também, nas linhas dos seus alunos (as
        disciplinas que faz numa turma da classe anterior)."""
        if self.env.su or self.env.user.has_group('edu_core.group_edu_user'):
            return
        employee = self.env.user.employee_id
        mine = self.filtered(lambda line: employee and line.enrollment_id.class_id.sudo().director_id == employee)
        (self - mine).lesson_id._check_can_manage()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_can_manage()
        lines.lesson_id._check_open_trimester()
        lines.filtered(lambda line: line.state == 'excused')._check_can_justify()
        return lines

    @api.ondelete(at_uninstall=False)
    def _unlink_check(self):
        self._check_can_manage()
        self.lesson_id._check_open_trimester()

    def write(self, vals):
        self._check_can_manage()
        self.lesson_id._check_open_trimester()
        if {'state', 'justification'} & set(vals):
            # Uma falta justificada tem sempre o motivo: apagá-lo sem mudar a presença é recusado.
            if 'justification' in vals and not (vals['justification'] or '').strip() and 'state' not in vals:
                if self.filtered(lambda line: line.state == 'excused'):
                    raise UserError(self.env._('Uma falta justificada tem de ter o motivo.'))
            if vals.get('state') == 'excused':
                self._check_can_justify()
                if not vals.get('justification'):
                    missing = self.filtered(lambda line: not line.justification)
                    if missing:
                        raise UserError(
                            self.env._('Indique o motivo da justificação de %s.', missing[0].student_id.name)
                        )
            else:
                self.filtered(lambda line: line.state == 'excused')._check_can_justify()
        if vals.get('state') == 'excused':
            vals = dict(vals, justified_by_id=self.env.uid, justified_date=fields.Date.context_today(self))
        elif vals.get('state') in ('present', 'late', 'absent'):
            vals = dict(vals, justified_by_id=False, justified_date=False)
            vals.setdefault('justification', False)
        result = super().write(vals)
        if {'lesson_id', 'enrollment_id'} & set(vals):
            # Mudar a linha de aula ou de aluno: as regras valem também para o destino (não só para a origem).
            self._check_can_manage()
            self.lesson_id._check_open_trimester()
            self.filtered(lambda line: line.state == 'excused')._check_can_justify()
        if 'state' in vals:
            self.filtered(lambda line: line.lesson_state == 'done')._edu_check_limits()
        return result

    def action_justify(self):
        """Justifica a falta (o motivo fica na linha)."""
        for line in self.filtered(lambda line: line.state == 'absent'):
            if not line.justification:
                raise UserError(self.env._('Indique o motivo da justificação de %s.', line.student_id.name))
            line.state = 'excused'
        return True

    def _edu_check_limits(self):
        """Avisa o director de turma quando um aluno fica em risco ou reprovado por faltas numa disciplina."""
        Summary = self.env['edu.absence.summary'].sudo()
        self.env.flush_all()  # a vista SQL lê o que está na base de dados
        Summary.invalidate_model()
        for line in self.filtered(lambda line: line.state == 'absent'):
            summary = Summary.search(
                [
                    ('enrollment_id', '=', line.enrollment_id.id),
                    ('subject_id', '=', line.subject_id.id),
                    ('trimester_id', '=', line.trimester_id.id),
                ],
                limit=1,
            )
            if summary and summary.status in (AT_RISK, FAILED):
                line.enrollment_id.sudo()._edu_absence_alert(line.subject_id, line.trimester_id, summary)
