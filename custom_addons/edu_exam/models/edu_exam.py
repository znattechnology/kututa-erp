from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import is_trusted, trusted
from odoo.exceptions import AccessError, UserError, ValidationError

PERIOD_KINDS = [
    ('trimester_test', 'Provas trimestrais'),
    ('global_exam', 'Provas globais (técnico)'),
    ('national_exam', 'Exame nacional'),
    ('resit', 'Recurso'),
    ('extraordinary', 'Extraordinário (disciplinas em atraso)'),
    ('improvement', 'Melhoria de nota'),
    ('completion', 'Época especial de conclusão de curso'),
]
SPECIAL = ('resit', 'extraordinary', 'improvement', 'completion')
ENROLLED = ('active', 'irregular')


class EduExamPeriod(models.Model):
    _name = 'edu.exam.period'
    _description = 'Época de exames'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Época', required=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    academic_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano lectivo',
        required=True,
        check_company=True,
        default=lambda self: self.env.company.edu_current_year_id,
    )
    trimester_id = fields.Many2one(
        'edu.trimester', string='Trimestre', domain="[('academic_year_id', '=', academic_year_id)]"
    )
    kind = fields.Selection(PERIOD_KINDS, string='Tipo', required=True, default='trimester_test')
    date_start = fields.Date(string='De', required=True)
    date_end = fields.Date(string='Até', required=True)
    state = fields.Selection(
        [('draft', 'Em preparação'), ('open', 'A decorrer'), ('closed', 'Encerrada')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    session_ids = fields.One2many('edu.exam.session', 'period_id', string='Sessões')
    session_count = fields.Integer(string='N.º de sessões', compute='_compute_session_count')

    @api.depends('session_ids')
    def _compute_session_count(self):
        for period in self:
            period.session_count = len(period.session_ids)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for period in self:
            if period.date_end < period.date_start:
                raise ValidationError(self.env._('A época termina antes de começar.'))

    def action_open(self):
        self.write({'state': 'open'})
        return True

    def action_close(self):
        for period in self:
            pending = period.session_ids.filtered(lambda s: s.state == 'scheduled')
            if pending:
                raise UserError(self.env._('Há sessões por realizar: %s.', ', '.join(pending.mapped('display_name'))))
            period.state = 'closed'
        return True


class EduExamSession(models.Model):
    _name = 'edu.exam.session'
    _description = 'Sessão de exame'
    _inherit = ['mail.thread']
    _order = 'date, hour_from, id'
    _check_company_auto = True

    period_id = fields.Many2one('edu.exam.period', string='Época', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='period_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='period_id.academic_year_id', store=True)
    kind = fields.Selection(related='period_id.kind', store=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, check_company=True)
    class_ids = fields.Many2many(
        'edu.class', string='Turmas', check_company=True, domain="[('academic_year_id', '=', academic_year_id)]"
    )
    assessment_ids = fields.Many2many(
        'edu.assessment',
        string='Avaliações ligadas',
        check_company=True,
        help='Provas e exames das turmas: as notas da sessão vão para estas avaliações.',
    )
    date = fields.Date(string='Data', required=True)
    hour_from = fields.Float(aggregator=None, string='Das', required=True, default=8.0)
    hour_to = fields.Float(aggregator=None, string='Às', required=True, default=10.0)
    state = fields.Selection(
        [('scheduled', 'Marcada'), ('done', 'Realizada'), ('cancelled', 'Anulada')],
        string='Estado',
        default='scheduled',
        required=True,
        tracking=True,
    )
    room_ids = fields.One2many('edu.exam.room', 'session_id', string='Salas')
    seat_ids = fields.One2many('edu.exam.seat', 'session_id', string='Alunos')
    seat_count = fields.Integer(string='N.º de alunos', compute='_compute_counts')
    capacity = fields.Integer(string='Lotação', compute='_compute_counts')
    note = fields.Text(string='Observações')

    @api.depends('seat_ids', 'room_ids.capacity')
    def _compute_counts(self):
        for session in self:
            session.seat_count = len(session.seat_ids)
            session.capacity = sum(session.room_ids.mapped('capacity'))

    @api.depends('subject_id', 'date', 'period_id')
    def _compute_display_name(self):
        for session in self:
            session.display_name = (
                f'{session.subject_id.name or ""} · {session.date.strftime("%d/%m/%Y") if session.date else ""} · '
                f'{session.period_id.name or ""}'
            )

    @api.constrains('date', 'hour_from', 'hour_to', 'period_id')
    def _check_session(self):
        for session in self:
            period = session.period_id
            if not period.date_start <= session.date <= period.date_end:
                raise ValidationError(self.env._('A sessão sai das datas da época %s.', period.name))
            if not 0 <= session.hour_from < session.hour_to <= 24:
                raise ValidationError(self.env._('As horas da sessão não são válidas.'))

    def _overlapping_sessions(self):
        self.ensure_one()
        return self.search(
            [
                ('id', '!=', self.id),
                ('date', '=', self.date),
                ('hour_from', '<', self.hour_to),
                ('hour_to', '>', self.hour_from),
                ('state', '!=', 'cancelled'),
                ('company_id', '=', self.company_id.id),
            ]
        )

    def _check_conflicts(self):
        """A mesma sala, o mesmo vigilante ou o mesmo aluno não estão em duas sessões à mesma hora."""
        for session in self.filtered(lambda s: s.state != 'cancelled'):
            # Na mesma sessão: um vigilante não fica em duas salas ao mesmo tempo.
            seen = self.env['hr.employee']
            for room in session.sudo().room_ids:
                twice = room.supervisor_ids & seen
                if twice:
                    raise ValidationError(
                        self.env._('%s não pode vigiar duas salas da mesma prova.', ', '.join(twice.mapped('name')))
                    )
                seen |= room.supervisor_ids
            others = session._overlapping_sessions()
            if not others:
                continue
            rooms = session.room_ids.room_id & others.room_ids.room_id
            if rooms:
                raise ValidationError(
                    self.env._('A sala %s já tem outra sessão a essa hora.', ', '.join(rooms.mapped('display_name')))
                )
            # Em sudo: a secretaria não lê a ficha dos funcionários e não via os vigilantes (nem o choque).
            supervisors = session.sudo().room_ids.supervisor_ids & others.sudo().room_ids.supervisor_ids
            if supervisors:
                raise ValidationError(
                    self.env._('%s já vigia outra sessão a essa hora.', ', '.join(supervisors.mapped('name')))
                )
            students = session.seat_ids.student_id & others.seat_ids.student_id
            if students:
                raise ValidationError(
                    self.env._('%s já tem outro exame a essa hora.', ', '.join(students.mapped('name')))
                )

    @api.constrains('assessment_ids', 'subject_id', 'class_ids', 'period_id')
    def _check_assessments(self):
        """As notas da sessão entram nas avaliações ligadas fora da janela do professor: só provas e exames desta
        disciplina, das turmas da sessão e do trimestre da época (nunca a avaliação contínua de outra disciplina)."""
        for session in self:
            for assessment in session.assessment_ids:
                wrong = (
                    assessment.subject_id != session.subject_id
                    or assessment.assessment_type == 'continuous'
                    or (session.class_ids and assessment.class_id not in session.class_ids)
                    or (session.period_id.trimester_id and assessment.trimester_id != session.period_id.trimester_id)
                )
                if wrong:
                    raise ValidationError(
                        self.env._(
                            '«%(assessment)s» não é uma prova de %(subject)s desta sessão.',
                            assessment=assessment.display_name,
                            subject=session.subject_id.name,
                        )
                    )

    @api.model_create_multi
    def create(self, vals_list):
        if not is_trusted(self.env) and any(vals.get('state', 'scheduled') != 'scheduled' for vals in vals_list):
            raise AccessError(self.env._('Uma sessão de exame começa sempre marcada.'))
        sessions = super().create(vals_list)
        sessions._check_conflicts()
        return sessions

    def write(self, vals):
        if 'state' in vals and not is_trusted(self.env):
            raise AccessError(self.env._('O estado da sessão só muda ao realizá-la ou anulá-la.'))
        result = super().write(vals)
        if {'date', 'hour_from', 'hour_to', 'state'} & set(vals):
            self._check_conflicts()
        return result

    def action_summon(self):
        """Convoca os alunos: nos exames especiais, os que têm exame por fazer nesta disciplina (nas turmas
        escolhidas, se houver); nas provas, os matriculados na disciplina das turmas escolhidas."""
        Seat = self.env['edu.exam.seat']
        for session in self:
            if session.state != 'scheduled':
                raise UserError(self.env._('A sessão já foi realizada ou anulada.'))
            vals = []
            present = set(session.seat_ids.student_id.ids)
            if session.kind in SPECIAL:
                kinds = ['improvement'] if session.kind == 'improvement' else ['resit', 'extraordinary']
                domain = [
                    ('subject_id', '=', session.subject_id.id),
                    ('state', '=', 'pending'),
                    ('kind', 'in', kinds),
                    ('company_id', '=', session.company_id.id),
                ]
                if session.class_ids:
                    domain.append(('class_id', 'in', session.class_ids.ids))
                for requirement in self.env['edu.exam.requirement'].search(domain):
                    if requirement.student_id.id not in present:
                        vals.append(
                            {
                                'session_id': session.id,
                                'enrollment_id': requirement.year_result_id.enrollment_id.id,
                                'requirement_id': requirement.id,
                            }
                        )
                        present.add(requirement.student_id.id)
            else:
                if not session.class_ids:
                    raise UserError(self.env._('Escolha as turmas da sessão.'))
                enrollments = self.env['edu.enrollment'].search(
                    [
                        ('class_id', 'in', session.class_ids.ids),
                        ('state', 'in', ENROLLED),
                        ('subject_ids', 'in', session.subject_id.ids),
                    ]
                )
                for enrollment in enrollments:
                    if enrollment.student_id.id not in present:
                        vals.append({'session_id': session.id, 'enrollment_id': enrollment.id})
                        present.add(enrollment.student_id.id)
            Seat.create(vals)
            session._check_conflicts()
        return True

    def action_distribute(self):
        """Distribui os alunos pelas salas, por ordem alfabética, até à lotação de cada sala."""
        for session in self:
            if not session.room_ids:
                raise UserError(self.env._('Indique as salas da sessão.'))
            if session.seat_count > session.capacity:
                raise UserError(
                    self.env._(
                        'Há %(students)s alunos para %(capacity)s lugares.',
                        students=session.seat_count,
                        capacity=session.capacity,
                    )
                )
            seats = session.seat_ids.sorted(lambda s: ((s.student_id.name or '').lower(), s.id))
            rooms = session.room_ids.sorted(lambda r: (r.room_id.code or r.room_id.name or '', r.id))
            index = 0
            for room in rooms:
                for number in range(1, room.capacity + 1):
                    if index >= len(seats):
                        break
                    seats[index].write({'room_id': room.id, 'seat_number': number})
                    index += 1
        return True

    def action_done(self):
        """Fecha a sessão: as notas vão para os exames especiais (que actualizam a pauta e a decisão) ou para as
        avaliações ligadas. Falta injustificada: 0 valores (no recurso e na melhoria, não se apresentou)."""
        for session in self:
            if session.state != 'scheduled':
                continue
            missing = session.seat_ids.filtered(lambda s: s.attended and not s.graded)
            if missing:
                raise UserError(self.env._('Faltam as notas de: %s.', ', '.join(missing.mapped('student_id.name'))))
            for seat in session.seat_ids:
                seat._push_score()
            with trusted(self.env):
                session.state = 'done'
        return True

    def action_cancel(self):
        with trusted(self.env):
            self.write({'state': 'cancelled'})
        return True


class EduExamRoom(models.Model):
    _name = 'edu.exam.room'
    _description = 'Sala de exame'
    _order = 'session_id, id'

    session_id = fields.Many2one('edu.exam.session', string='Sessão', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='session_id.company_id', store=True)
    room_id = fields.Many2one('edu.room', string='Sala', required=True)
    capacity = fields.Integer(
        string='Lugares', compute='_compute_capacity', store=True, readonly=False, precompute=True
    )
    supervisor_ids = fields.Many2many('hr.employee', string='Vigilantes', domain="[('edu_is_teacher', '=', True)]")
    # Os vigilantes no formulário da secretaria, que não lê a ficha dos funcionários: o perfil público (os mesmos
    # ids). Sem isto, a coluna aparecia vazia e gravar a linha apagava os vigilantes.
    supervisor_public_ids = fields.Many2many(
        'hr.employee.public',
        string='Vigilantes ',
        compute='_compute_supervisor_public_ids',
        inverse='_inverse_supervisor_public_ids',
        domain="[('edu_is_teacher', '=', True)]",
    )
    seat_ids = fields.One2many('edu.exam.seat', 'room_id', string='Alunos')

    _session_room_uniq = models.Constraint('UNIQUE(session_id, room_id)', 'A sala já está nesta sessão.')

    @api.depends('supervisor_ids')
    def _compute_supervisor_public_ids(self):
        Public = self.env['hr.employee.public']
        for room in self:
            room.supervisor_public_ids = Public.browse(room.sudo().supervisor_ids.ids)

    def _inverse_supervisor_public_ids(self):
        if not self.env.su and not self.env.user.has_group('edu_core.group_edu_user'):
            raise UserError(self.env._('Os vigilantes escolhe-os a secretaria.'))
        for room in self:
            room.sudo().supervisor_ids = self.env['hr.employee']._edu_exam_supervisors(
                room.supervisor_public_ids.ids, room.session_id.company_id
            )

    @api.depends('room_id')
    def _compute_capacity(self):
        for room in self:
            if not room.capacity:
                room.capacity = room.room_id.capacity

    @api.depends('room_id')
    def _compute_display_name(self):
        for room in self:
            room.display_name = room.room_id.display_name

    @api.constrains('supervisor_ids', 'room_id')
    def _check_room(self):
        self.session_id._check_conflicts()


class EduExamSeat(models.Model):
    _name = 'edu.exam.seat'
    _description = 'Aluno na sessão de exame'
    _order = 'session_id, room_id, seat_number, id'

    session_id = fields.Many2one('edu.exam.session', string='Sessão', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='session_id.company_id', store=True)
    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, index=True)
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True)
    requirement_id = fields.Many2one('edu.exam.requirement', string='Exame especial')
    room_id = fields.Many2one('edu.exam.room', string='Sala', domain="[('session_id', '=', session_id)]")
    seat_number = fields.Integer(string='Lugar')
    attended = fields.Boolean(string='Compareceu', default=True)
    score = fields.Float(string='Nota', digits=(4, 2))
    graded = fields.Boolean(string='Com nota')
    note = fields.Char(string='Observação')

    _session_student_uniq = models.Constraint('UNIQUE(session_id, enrollment_id)', 'O aluno já está nesta sessão.')

    def write(self, vals):
        if 'score' in vals and 'graded' not in vals:
            vals = dict(vals, graded=True)
        return super().write(vals)

    @api.constrains('score')
    def _check_score(self):
        for seat in self:
            policy = self.env['edu.evaluation.policy']._get(seat.company_id, seat.class_id.level_id)
            if not 0 <= seat.score <= policy.scale_max:
                raise ValidationError(self.env._('A nota vai de 0 a %s.', policy.scale_max))

    def _push_score(self):
        self.ensure_one()
        score = self.score if self.attended else 0.0
        requirement = self.requirement_id
        if requirement and requirement.state == 'pending':
            if not self.attended and requirement.kind == 'improvement':
                return  # quem falta à melhoria fica com a nota que tinha
            requirement.write({'score': score, 'date': self.session_id.date})
            requirement.action_record()
            return
        # O resultado da sessão de exame (o júri) entra na nota fora da janela de lançamento do professor (sudo).
        Grade = self.env['edu.grade'].sudo()
        for assessment in self.session_id.assessment_ids.sudo().filtered(lambda a: a.class_id == self.class_id):
            grade = assessment.grade_ids.filtered(lambda g: g.enrollment_id == self.enrollment_id)
            vals = {'score': score, 'absent': not self.attended}
            if grade:
                grade.write(vals)
            else:
                Grade.create({'assessment_id': assessment.id, 'enrollment_id': self.enrollment_id.id, **vals})


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _edu_exam_supervisors(self, ids, company):
        """Os vigilantes que se podem gravar em sudo: só professores da escola da prova."""
        teachers = self.sudo().browse(ids).exists()
        wrong = teachers.filtered(lambda t: not t.edu_is_teacher or t.company_id != company)
        if wrong:
            raise UserError(self.env._('%s não é professor desta escola.', ', '.join(wrong.mapped('name'))))
        return teachers
