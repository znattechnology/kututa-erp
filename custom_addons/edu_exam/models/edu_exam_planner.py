import re
from collections import Counter

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .edu_exam import SPECIAL

ROMAN_TRIMESTER = {'I': 1, 'II': 2, 'III': 3}


def guess_kind(name):
    """O tipo da época pelo nome do evento do calendário escolar (Calendário Escolar Nacional)."""
    text = (name or '').casefold()
    for words, kind in (
        (('recurso',), 'resit'),
        (('extraordin',), 'extraordinary'),
        (('melhoria',), 'improvement'),
        (('especial', 'conclusão'), 'completion'),
        (('prova global',), 'global_exam'),
        (('exame',), 'national_exam'),
    ):
        if any(word in text for word in words):
            return kind
    return 'trimester_test'


class EduExamPeriod(models.Model):
    """Calendário de provas (acção cliente ``edu_exam.exam_planner``), como o do secPed-Express: as épocas do ano, as
    provas de cada turma (uma sessão por turma, com a sala e o vigilante), vistas por sessão (as turmas que fazem
    prova à mesma hora), por turma e por professor (a escala de vigilância). O mesmo professor nunca vigia duas
    turmas à mesma hora; «Distribuir vigilantes» preenche as que faltam."""

    _inherit = 'edu.exam.period'

    @api.model
    def _planner_check(self):
        if not self.env.su and not self.env.user.has_group('edu_core.group_edu_user'):
            raise AccessError(self.env._('O calendário de provas é da secretaria.'))

    @api.model
    def _planner_year(self):
        return self.env['edu.academic.year'].search(
            [('is_current', '=', True), ('company_id', 'in', self.env.companies.ids)], limit=1
        )

    @api.model
    def planner_options(self):
        """As épocas do ano em curso e as do calendário escolar ainda por criar."""
        self._planner_check()
        year = self._planner_year()
        periods = self.search([('academic_year_id', '=', year.id)], order='date_start, id') if year else self
        return {
            'year': year.name if year else False,
            'periods': [period._planner_period() for period in periods],
            'proposals': self._planner_proposals(year, periods),
            'can_print': hasattr(self, 'planner_print'),
        }

    def _planner_period(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'kind': self.kind,
            'kind_label': dict(self._fields['kind']._description_selection(self.env)).get(self.kind),
            'special': self.kind in SPECIAL,
            'date_start': fields.Date.to_string(self.date_start),
            'date_end': fields.Date.to_string(self.date_end),
            'state': self.state,
        }

    @api.model
    def _planner_proposals(self, year, periods):
        """Os eventos «Provas e exames» do calendário escolar do ano (até ao início do ano seguinte: o recurso e a
        época especial caem em Julho e Agosto) que ainda não são uma época de provas."""
        if not year:
            return []
        events = self.env['edu.calendar.event'].search(
            [
                ('company_id', '=', year.company_id.id),
                ('event_type', '=', 'exam'),
                ('date_start', '>=', year.date_start),
                ('date_start', '<', year.date_start + relativedelta(years=1)),
            ],
            order='date_start, id',
        )
        taken = {(p.name, p.date_start) for p in periods}
        return [
            {
                'id': event.id,
                'name': event.name,
                'date_start': fields.Date.to_string(event.date_start),
                'date_end': fields.Date.to_string(event.date_end or event.date_start),
                'levels': ', '.join(event.level_ids.mapped('name')),
            }
            for event in events
            if (event.name, event.date_start) not in taken
        ]

    @api.model
    def planner_create_from_event(self, event_id):
        """Cria a época a partir do evento do calendário: as datas, o tipo e o trimestre."""
        self._planner_check()
        event = self.env['edu.calendar.event'].browse(event_id).exists()
        if not event:
            raise UserError(self.env._('O evento já não existe no calendário escolar.'))
        year = event.academic_year_id
        start, end = event.date_start, event.date_end or event.date_start
        trimester = year.trimester_ids.filtered(lambda t: t.date_start <= start <= t.date_end)[:1]
        match = re.search(r'\b(I{1,3})\s+Trimestre', event.name or '', re.IGNORECASE)
        if match:
            number = ROMAN_TRIMESTER.get(match.group(1).upper())
            trimester = year.trimester_ids.filtered(lambda t: t.number == number)[:1] or trimester
        period = self.create(
            {
                'name': event.name,
                'academic_year_id': year.id,
                'company_id': event.company_id.id,
                'kind': guess_kind(event.name),
                'trimester_id': trimester.id,
                'date_start': start,
                'date_end': end,
            }
        )
        return period.id

    def planner_data(self):
        """Tudo o que a página precisa da época: as provas (sessões), as turmas do ano, os professores, as salas e as
        vigilâncias noutras épocas à mesma hora (para os choques se verem antes de escolher)."""
        self._planner_check()
        self.ensure_one()
        year = self.academic_year_id
        sessions = self.session_ids.filtered(lambda s: s.state != 'cancelled').sorted(
            lambda s: (s.date, s.hour_from, s.hour_to, s.id)
        )
        classes = self.env['edu.class'].search([('academic_year_id', '=', year.id)])
        classes = classes.sorted(lambda c: (c.class_number, c.course_id.code or '', c.name or ''))
        teachers = (
            self.env['hr.employee']
            .sudo()
            .search([('edu_is_teacher', '=', True), ('company_id', '=', self.company_id.id)], order='name')
        )
        assignments = self.env['edu.teaching.assignment'].sudo().search([('academic_year_id', '=', year.id)])
        others = self.env['edu.exam.session'].search(
            [
                ('company_id', '=', self.company_id.id),
                ('period_id', '!=', self.id),
                ('state', '!=', 'cancelled'),
                ('date', '>=', self.date_start),
                ('date', '<=', self.date_end),
            ]
        )
        return {
            'period': self._planner_period(),
            'sessions': [session._planner_session() for session in sessions],
            'classes': [
                {
                    'id': c.id,
                    'name': c._editor_label(),
                    'number': c.class_number,
                    'course': c.course_id.name or '',
                    'subject_ids': c.subject_line_ids.filtered('weekly_hours').subject_id.ids,
                    'room_id': c._planner_room().id,
                }
                for c in classes
            ],
            'subjects': [
                {'id': s.id, 'name': s.name}
                for s in classes.subject_line_ids.filtered('weekly_hours').subject_id.sorted('name')
            ],
            'teachers': [{'id': t.id, 'name': t.name} for t in teachers],
            'rooms': [{'id': r.id, 'name': r.display_name} for r in self.env['edu.room'].search([], order='name')],
            'subject_teachers': [[a.class_id.id, a.subject_id.id, a.teacher_id.id] for a in assignments],
            'elsewhere': [
                {
                    'teacher_id': teacher.id,
                    'date': fields.Date.to_string(session.date),
                    'from': session.hour_from,
                    'to': session.hour_to,
                    'label': f'{session.subject_id.name} ({session.period_id.name})',
                }
                for session in others
                for teacher in session._supervisors()
            ],
        }

    def planner_mark(self, subject_id, date, hour_from, hour_to, class_ids):
        """Marca a mesma prova (disciplina, dia e horas) em várias turmas de uma vez: uma sessão por turma, na sala
        da turma (a fixa ou a habitual do horário). As turmas que não podem (choque de sala, já com prova a essa
        hora) ficam de fora, com o motivo."""
        self._planner_check()
        self.ensure_one()
        if hour_to <= hour_from:
            raise UserError(self.env._('A prova acaba antes de começar.'))
        subject = self.env['edu.subject'].browse(subject_id)
        created, failures = [], []
        for edu_class in self.env['edu.class'].browse(class_ids):
            try:
                with self.env.cr.savepoint():
                    session = self.env['edu.exam.session'].create(
                        {
                            'period_id': self.id,
                            'subject_id': subject.id,
                            'class_ids': [fields.Command.set(edu_class.ids)],
                            'date': date,
                            'hour_from': hour_from,
                            'hour_to': hour_to,
                            'assessment_ids': [fields.Command.set(self._planner_assessments(edu_class, subject).ids)],
                        }
                    )
                    room = edu_class._planner_room()
                    if room:
                        session.room_ids = [fields.Command.create({'room_id': room.id})]
                    created.append(session.id)
            except (UserError, ValueError) as error:
                failures.append(f'{edu_class._editor_label()}: {error.args[0] if error.args else error}')
        return {'created': len(created), 'failures': failures}

    def _planner_assessments(self, edu_class, subject):
        """A avaliação da turma a que vão as notas da prova (a prova trimestral, a global ou o exame nacional)."""
        kinds = {'trimester_test': 'trimester_test', 'global_exam': 'global_exam', 'national_exam': 'national_exam'}
        kind = kinds.get(self.kind)
        if not kind:
            return self.env['edu.assessment']
        domain = [('class_id', '=', edu_class.id), ('subject_id', '=', subject.id), ('assessment_type', '=', kind)]
        if self.trimester_id:
            domain.append(('trimester_id', '=', self.trimester_id.id))
        return self.env['edu.assessment'].search(domain, limit=1)

    def planner_distribute(self, date, hour_from, hour_to):
        """Põe um vigilante em cada prova da sessão que ainda não tem: um professor por turma, nunca em dois sítios à
        mesma hora, primeiro quem dá aulas a essa hora (já está na escola), depois quem tem menos vigilâncias na
        época; o professor da disciplina naquela turma só se não houver outro livre."""
        self._planner_check()
        self.ensure_one()
        day = fields.Date.to_date(date)
        sessions = self.session_ids.filtered(
            lambda s: s.state == 'scheduled' and s.date == day and s.hour_from == hour_from and s.hour_to == hour_to
        )
        Session = self.env['edu.exam.session']
        overlapping = Session.search(
            [
                ('company_id', '=', self.company_id.id),
                ('state', '!=', 'cancelled'),
                ('date', '=', day),
                ('hour_from', '<', hour_to),
                ('hour_to', '>', hour_from),
            ]
        )
        busy = set(overlapping._supervisors().ids)
        load = Counter()
        for session in self.session_ids:
            for teacher in session._supervisors():
                load[teacher.id] += 1
        teachers = (
            self.env['hr.employee']
            .sudo()
            .search([('edu_is_teacher', '=', True), ('company_id', '=', self.company_id.id)], order='name')
        )
        # Quem dá aulas a essa hora (em qualquer dia da semana): o turno em que já está na escola.
        lessons = (
            self.env['edu.schedule']
            .sudo()
            .search(
                [
                    ('academic_year_id', '=', self.academic_year_id.id),
                    ('hour_from', '<', hour_to),
                    ('hour_to', '>', hour_from),
                    ('teacher_id', '!=', False),
                ]
            )
        )
        in_shift = set(lessons.teacher_id.ids)
        Assignment = self.env['edu.teaching.assignment'].sudo()
        assigned = without = no_room = 0
        for session in sessions.filtered(lambda s: not s._supervisors()):
            if not session.room_ids:
                no_room += 1
                continue
            edu_class = session.class_ids[:1]
            own = set(
                Assignment.search(
                    [('class_id', '=', edu_class.id), ('subject_id', '=', session.subject_id.id)]
                ).teacher_id.ids
            )
            candidates = sorted(
                (t for t in teachers if t.id not in busy),
                key=lambda t, own=own: (t.id in own, t.id not in in_shift, load[t.id], t.name or ''),
            )
            if not candidates:
                without += 1
                continue
            teacher = candidates[0]
            session.room_ids[:1].sudo().supervisor_ids = teacher
            busy.add(teacher.id)
            load[teacher.id] += 1
            assigned += 1
        return {'assigned': assigned, 'without': without, 'no_room': no_room}

    @api.model
    def planner_set_supervisor(self, session_id, teacher_id):
        """O vigilante da prova (um por turma): fica na sala da prova."""
        self._planner_check()
        session = self.env['edu.exam.session'].browse(session_id).exists()
        if not session:
            raise UserError(self.env._('A prova já não existe.'))
        if not session.room_ids:
            raise UserError(self.env._('Escolha primeiro a sala da prova.'))
        # Em sudo (depois do _planner_check): a secretaria não lê a ficha dos funcionários e o Odoo recusava gravar o
        # vigilante. Os choques continuam a ser verificados (_check_conflicts).
        session.room_ids[:1].sudo().supervisor_ids = self.env['hr.employee'].browse(teacher_id or [])
        return session._planner_session()

    @api.model
    def planner_set_room(self, session_id, room_id):
        self._planner_check()
        session = self.env['edu.exam.session'].browse(session_id).exists()
        if not session:
            raise UserError(self.env._('A prova já não existe.'))
        line = session.room_ids[:1]
        if not room_id:
            session.room_ids.unlink()
        elif line:
            line.room_id = room_id
        else:
            session.room_ids = [fields.Command.create({'room_id': room_id})]
        return session._planner_session()

    @api.model
    def planner_remove(self, session_id):
        self._planner_check()
        session = self.env['edu.exam.session'].browse(session_id).exists()
        if session.state != 'scheduled' or session.seat_ids.filtered('graded'):
            raise UserError(self.env._('A prova já tem notas ou foi realizada: anule-a na sessão.'))
        session.unlink()
        return True

    def planner_summon(self, date, hour_from, hour_to):
        """Exames especiais: convoca para as provas da sessão os alunos com exame por fazer na disciplina."""
        self._planner_check()
        self.ensure_one()
        day = fields.Date.to_date(date)
        sessions = self.session_ids.filtered(
            lambda s: s.state == 'scheduled' and s.date == day and s.hour_from == hour_from and s.hour_to == hour_to
        )
        before = len(sessions.seat_ids)
        sessions.action_summon()
        return len(sessions.seat_ids) - before


class EduExamSession(models.Model):
    _inherit = 'edu.exam.session'

    room_label = fields.Char(string='Salas', compute='_compute_labels')
    supervisor_label = fields.Char(string='Vigilantes', compute='_compute_labels')
    incomplete = fields.Boolean(string='Sem sala ou vigilante', compute='_compute_labels', search='_search_incomplete')

    @api.depends('room_ids.room_id', 'room_ids.supervisor_ids')
    def _compute_labels(self):
        for session in self:
            session.room_label = ', '.join(session.room_ids.room_id.mapped('display_name')) or False
            supervisors = session._supervisors()
            session.supervisor_label = ', '.join(supervisors.mapped('name')) or False
            session.incomplete = not session.room_ids or not supervisors

    def _search_incomplete(self, operator, value):
        if operator not in ('=', '!='):
            return NotImplemented
        complete = self.sudo().search([('room_ids.supervisor_ids', '!=', False)]).ids
        wanted = (operator == '=') == bool(value)
        return [('id', 'not in' if wanted else 'in', complete)]

    def _supervisors(self):
        """Os vigilantes das provas. Em sudo: a secretaria não lê a ficha dos funcionários e o Odoo escondia-lhe os
        vigilantes (a prova parecia sem vigilante e «Distribuir vigilantes» substituía-o)."""
        return self.sudo().room_ids.supervisor_ids

    def _planner_session(self):
        self.ensure_one()
        edu_class = self.class_ids[:1]
        return {
            'id': self.id,
            'date': fields.Date.to_string(self.date),
            'from': self.hour_from,
            'to': self.hour_to,
            'class_id': edu_class.id,
            'class_ids': self.class_ids.ids,
            # Uma prova pode ter várias turmas (marcada na sessão): mostram-se todas.
            'class': ', '.join(c._editor_label() for c in self.class_ids),
            'subject_id': self.subject_id.id,
            'subject': self.subject_id.name,
            'room_id': self.room_ids[:1].room_id.id,
            'room': self.room_label or False,
            'room_count': len(self.room_ids),
            'supervisors': [{'id': t.id, 'name': t.name} for t in self._supervisors()],
            'seats': len(self.seat_ids),
            'state': self.state,
        }


class EduClass(models.Model):
    _inherit = 'edu.class'

    def _planner_room(self):
        """A sala da prova da turma: a fixa; sem ela, a habitual (onde tem mais aulas no horário)."""
        self.ensure_one()
        if self.room_id:
            return self.room_id
        best = Counter(s.room_id.id for s in self.schedule_ids if s.room_id).most_common(1)
        return self.env['edu.room'].browse(best[0][0]) if best else self.env['edu.room']


class EduExamRequirement(models.Model):
    _inherit = 'edu.exam.requirement'

    seat_ids = fields.One2many('edu.exam.seat', 'requirement_id', string='Convocatórias')
    session_id = fields.Many2one('edu.exam.session', string='Sessão', compute='_compute_session_id')

    @api.depends('seat_ids.session_id')
    def _compute_session_id(self):
        for requirement in self:
            requirement.session_id = requirement.seat_ids.session_id.sorted('date')[-1:]
