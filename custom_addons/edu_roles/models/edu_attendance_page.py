from odoo import api, fields, models
from odoo.addons.edu_attendance.models.absence_rules import absence_limit
from odoo.exceptions import AccessError, UserError

from .edu_teacher_home import WEEKDAYS, _hour

# A ordem dos botões da chamada, como no secPed.
STATES = ['present', 'late', 'absent', 'excused']


def _long_day(day):
    """«Terça-feira, 27/10/2026»."""
    return f'{WEEKDAYS[day.weekday()].capitalize()}, {day.strftime("%d/%m/%Y")}'


class EduAttendancePage(models.AbstractModel):
    """«Presenças» do professor (acção cliente ``edu_roles.attendance``), como a página do secPed: as aulas de hoje
    pelo horário, com a chamada a um toque; «Outra aula», pela turma e pela disciplina (o director de turma marca
    qualquer disciplina da sua turma), com as aulas do ano e «Registar outra aula»; e a chamada, com o sumário.

    A chamada começa com todos presentes mas só fica registada quando se guarda; com o sumário escrito, guardar dá
    também a aula por dada (a que conta no número de aulas e nas faltas). As regras de sempre continuam no modelo: só
    o professor da disciplina ou o director gere a aula, só o director (e a secretaria) justifica, e um trimestre
    fechado já não muda."""

    _name = 'edu.attendance.page'
    _description = 'Presenças do professor'

    @api.model
    def _employee(self):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(self.env._('O seu utilizador não está ligado a uma ficha de professor.'))
        return employee

    @api.model
    def _staff(self):
        return self.env.user.has_group('edu_core.group_edu_user')

    @api.model
    def _lesson(self, lesson_id):
        """A aula, com a verificação de sempre (professor da disciplina, director de turma ou substituto)."""
        lesson = self.env['edu.lesson'].browse(lesson_id).exists()
        if not lesson:
            raise UserError(self.env._('A aula já não existe.'))
        lesson._check_can_manage()
        return lesson

    @api.model
    def _lesson_row(self, lesson):
        lesson = lesson.sudo()
        return {
            'id': lesson.id,
            'class_id': lesson.class_id.id,
            'subject_id': lesson.subject_id.id,
            'date': fields.Date.to_string(lesson.date),
            'day': _long_day(lesson.date),
            'hours': f'{_hour(lesson.hour_from)}–{_hour(lesson.hour_to)}' if lesson.hour_to else '',
            'subject': lesson.subject_id.name,
            'class': lesson.class_id._editor_label(),
            'summary': lesson.summary or '',
            'state': lesson.state,
            'number': lesson.lesson_number,
            'roll_saved': bool(lesson.attendance_ids),
        }

    # A página

    @api.model
    def options(self):
        """As aulas de hoje pelo horário e as turmas do professor (com as disciplinas que pode marcar)."""
        employee = self.env.user.employee_id
        today = fields.Date.context_today(self)
        # «Hoje, sábado, 24/10/2026»: o dia da semana a meio da frase vai em minúsculas.
        data = {
            'has_employee': bool(employee),
            'today': f'{WEEKDAYS[today.weekday()]}, {today.strftime("%d/%m/%Y")}',
            'lessons': [],
            'classes': [],
        }
        if not employee:
            return data
        day, rows = self.env['edu.teacher.home']._next_lessons(employee, today)
        if day == today:
            lessons = self.env['edu.lesson'].sudo().browse([row['lesson_id'] for row in rows if row['lesson_id']])
            saved = {lesson.id for lesson in lessons if lesson.attendance_ids}
            data['lessons'] = [dict(row, roll_saved=row['lesson_id'] in saved) for row in rows]
        current = [('academic_year_id.is_current', '=', True), ('company_id', 'in', self.env.companies.ids)]
        assignments = self.env['edu.teaching.assignment'].sudo().search([('teacher_id', '=', employee.id), *current])
        directed = self.env['edu.class'].sudo().search([('director_id', '=', employee.id), *current])
        classes = (assignments.class_id | directed).sorted(lambda c: (c.class_number, c.name or ''))
        for edu_class in classes:
            mine = assignments.filtered(lambda a, c=edu_class: a.class_id == c).subject_id
            directs = edu_class in directed
            subjects = edu_class.subject_line_ids.filtered('weekly_hours').subject_id if directs else mine
            data['classes'].append(
                {
                    'id': edu_class.id,
                    'name': edu_class._editor_label(),
                    'directs': directs,
                    'subjects': [
                        {'id': s.id, 'name': s.name, 'as_director': s not in mine}
                        for s in subjects.sorted(lambda s: s.name or '')
                    ],
                }
            )
        return data

    @api.model
    def _check_class_subject(self, class_id, subject_id):
        edu_class = self.env['edu.class'].sudo().browse(class_id).exists()
        subject = self.env['edu.subject'].sudo().browse(subject_id).exists()
        if not edu_class or not subject:
            raise UserError(self.env._('A turma ou a disciplina já não existe.'))
        if not self._staff():
            employee = self._employee()
            teaches = (
                self.env['edu.teaching.assignment']
                .sudo()
                .search_count(
                    [('class_id', '=', edu_class.id), ('subject_id', '=', subject.id), ('teacher_id', '=', employee.id)]
                )
            )
            if not (teaches or edu_class.director_id == employee):
                raise AccessError(self.env._('Só o professor da disciplina ou o director de turma vê estas aulas.'))
        return edu_class, subject

    @api.model
    def lessons(self, class_id, subject_id):
        """As aulas deste ano da turma e da disciplina, das mais recentes para as mais antigas."""
        edu_class, subject = self._check_class_subject(class_id, subject_id)
        lessons = (
            self.env['edu.lesson']
            .sudo()
            .search(
                [('class_id', '=', edu_class.id), ('subject_id', '=', subject.id), ('state', '!=', 'cancelled')],
                order='date desc, hour_from desc, id desc',
            )
        )
        return [self._lesson_row(lesson) for lesson in lessons]

    @api.model
    def open_today(self, schedule_id):
        """A aula de hoje desse tempo do horário (registada se ainda não existe), sem a chamada: só se regista quando
        se guarda."""
        employee = self._employee()
        today = fields.Date.context_today(self)
        schedule = self.env['edu.schedule'].sudo().browse(schedule_id).exists()
        if not schedule or schedule._teacher_on(today) != employee:
            raise UserError(self.env._('Este tempo não é seu.'))
        if not schedule._occurs_on(today):
            raise UserError(self.env._('Hoje não há aula neste tempo.'))
        lesson = (
            self.env['edu.lesson'].sudo().search([('schedule_id', '=', schedule.id), ('date', '=', today)], limit=1)
        )
        if not lesson:
            lesson = self.env['edu.lesson'].create(
                {
                    'class_id': schedule.class_id.id,
                    'subject_id': schedule.subject_id.id,
                    'schedule_id': schedule.id,
                    'date': today,
                }
            )
        return self._lesson_row(lesson)

    @api.model
    def slots(self, class_id, subject_id, date):
        """Os tempos do horário da turma e da disciplina nesse dia da semana, para «Registar outra aula»."""
        edu_class, subject = self._check_class_subject(class_id, subject_id)
        day = fields.Date.to_date(date)
        if not day:
            return []
        schedules = (
            self.env['edu.schedule']
            .sudo()
            .search(
                [
                    ('class_id', '=', edu_class.id),
                    ('subject_id', '=', subject.id),
                    ('weekday', '=', str(day.weekday())),
                ],
                order='hour_from',
            )
        )
        return [
            {
                'id': s.id,
                'hour_from': s.hour_from,
                'hour_to': s.hour_to,
                'label': f'{_hour(s.hour_from)}–{_hour(s.hour_to)}'
                + (f', {s.room_id.display_name}' if s.room_id else ''),
            }
            for s in schedules
            if s._occurs_on(day)
        ]

    @api.model
    def new_lesson(self, class_id, subject_id, values):
        """Regista uma aula noutro dia (uma que faltou registar, uma reposição). Se já existe uma aula da turma e
        da disciplina nesse dia e hora, abre essa (sem lhe mudar o sumário)."""
        edu_class, subject = self._check_class_subject(class_id, subject_id)
        # ``values``: o dia (``date``), as horas (``hour_from``, ``hour_to``) e o sumário (``summary``).
        day = fields.Date.to_date(values.get('date'))
        hour_from, hour_to = values.get('hour_from') or 0.0, values.get('hour_to') or 0.0
        summary = values.get('summary') or ''
        if not day:
            raise UserError(self.env._('Escolha o dia da aula.'))
        if day > fields.Date.context_today(self):
            raise UserError(self.env._('A aula ainda não aconteceu: registe-a no próprio dia.'))
        if not hour_to or hour_to <= hour_from:
            raise UserError(self.env._('A aula tem de acabar depois de começar.'))
        Lesson = self.env['edu.lesson']
        existing = Lesson.sudo().search(
            [
                ('class_id', '=', edu_class.id),
                ('subject_id', '=', subject.id),
                ('date', '=', day),
                ('hour_from', '=', hour_from),
            ],
            limit=1,
        )
        if existing:
            return dict(self._lesson_row(existing), existed=True)
        schedule = (
            self.env['edu.schedule']
            .sudo()
            .search(
                [
                    ('class_id', '=', edu_class.id),
                    ('subject_id', '=', subject.id),
                    ('weekday', '=', str(day.weekday())),
                    ('hour_from', '=', hour_from),
                ],
                limit=1,
            )
        )
        vals = {'class_id': edu_class.id, 'subject_id': subject.id, 'date': day, 'summary': (summary or '').strip()}
        if schedule:
            vals['schedule_id'] = schedule.id
        else:
            vals.update(hour_from=hour_from, hour_to=hour_to)
        lesson = Lesson.create(vals)
        if schedule and (lesson.hour_from, lesson.hour_to) != (hour_from, hour_to):
            lesson.write({'hour_from': hour_from, 'hour_to': hour_to})
        return dict(self._lesson_row(lesson), existed=False)

    # A chamada

    @api.model
    def roll(self, lesson_id):
        """Os alunos da aula com a presença de cada um. Sem chamada guardada, todos presentes (por guardar)."""
        lesson = self._lesson(lesson_id).sudo()
        employee = self.env.user.employee_id
        staff = self._staff()
        if lesson.attendance_ids:
            lines = lesson.attendance_ids.sorted(lambda line: (line.order_number, line.student_id.name or ''))
            rows = [
                {
                    'enrollment_id': line.enrollment_id.id,
                    'number': line.order_number or '',
                    'name': line.student_id.name,
                    'state': line.state,
                    'justification': line.justification or '',
                    'can_justify': staff or employee == line.enrollment_id.class_id.director_id,
                }
                for line in lines
            ]
        else:
            enrollments = lesson._enrollments().sorted(lambda e: (e.order_number, e.student_id.name or ''))
            rows = [
                {
                    'enrollment_id': enrollment.id,
                    'number': enrollment.order_number or '',
                    'name': enrollment.student_id.name,
                    'state': 'present',
                    'justification': '',
                    'can_justify': staff or employee == enrollment.class_id.director_id,
                }
                for enrollment in enrollments
            ]
        closed = lesson.trimester_id.state == 'closed'
        return {
            'lesson': self._lesson_row(lesson),
            'rows': rows,
            'saved': bool(lesson.attendance_ids),
            'closed': closed,
            'reason': self.env._('O %s está fechado: a chamada já não se altera.', lesson.trimester_id.name)
            if closed
            else '',
            'future': lesson.date > fields.Date.context_today(self),
        }

    @api.model
    def save(self, lesson_id, rows, summary=''):
        """Guarda a chamada e o sumário. Com o sumário escrito e a aula já acontecida, a aula fica dada."""
        lesson = self._lesson(lesson_id)
        if lesson.state == 'cancelled':
            raise UserError(self.env._('A aula não se realizou.'))
        if not lesson.attendance_ids:
            lesson.action_open_roll_call()
        lines = {line.enrollment_id.id: line for line in lesson.attendance_ids}
        for row in rows:
            line = lines.get(row.get('enrollment_id'))
            state = row.get('state')
            if not line or state not in STATES:
                continue
            vals = {}
            if line.state != state:
                vals['state'] = state
            justification = (row.get('justification') or '').strip()
            if state == 'excused' and justification != (line.justification or ''):
                vals['justification'] = justification
            if vals:
                line.write(vals)
        summary = (summary or '').strip()
        if summary != (lesson.summary or ''):
            lesson.summary = summary
        done = False
        if lesson.state == 'scheduled' and summary and lesson.date <= fields.Date.context_today(self):
            lesson.action_done()
            done = True
        return dict(self.roll(lesson.id), done=done)

    # Relatório de faltas

    @api.model
    def absence_report(self, trimester_id=False, class_id=False):
        """«Relatório de faltas» (acção cliente ``edu_roles.absence_report``), como no secPed: os alunos a uma falta
        do limite ou que já o atingiram nas disciplinas do professor, por aluno; e, para o director de turma, o mapa da
        turma (faltas injustificadas por disciplina, com as justificadas e o limite). Os limites são os da lei (geral:
        por trimestre e disciplina; técnico: anual, o triplo dos tempos semanais)."""
        employee = self.env.user.employee_id
        company = employee.company_id or self.env.company
        year = self.env['edu.academic.year'].search(
            [('company_id', '=', company.id), ('is_current', '=', True)], limit=1
        )
        trimesters = year.trimester_ids.sorted('number')
        trimester = (
            trimesters.filtered(lambda t: t.id == trimester_id)[:1]
            or trimesters.filtered('is_current')[:1]
            or trimesters[:1]
        )
        data = {
            'has_employee': bool(employee),
            'year': year.name or '',
            'trimesters': [{'id': t.id, 'name': t.name, 'current': t.is_current} for t in trimesters],
            'trimester_id': trimester.id or False,
            'mine': [],
            'classes': [],
            'board': None,
        }
        if not employee or not trimester:
            return data
        Summary = self.env['edu.absence.summary'].sudo()
        self.env.flush_all()
        Summary.invalidate_model()
        # Nas minhas disciplinas: as linhas em risco ou reprovadas, agrupadas por aluno.
        assignments = (
            self.env['edu.teaching.assignment']
            .sudo()
            .search([('teacher_id', '=', employee.id), ('academic_year_id', '=', year.id)])
        )
        pairs = {(a.class_id.id, a.subject_id.id) for a in assignments}
        rows = Summary.search(
            [('trimester_id', '=', trimester.id), ('class_id', 'in', assignments.class_id.ids), ('absent', '>=', 1)]
        ).filtered(lambda s: (s.class_id.id, s.subject_id.id) in pairs and s.status != 'ok')
        students = {}
        for summary in rows:
            regime = summary.class_id._edu_regime()
            group = students.setdefault(
                summary.enrollment_id.id,
                {
                    'id': summary.enrollment_id.id,
                    'name': summary.student_id.name,
                    'class': summary.class_id._editor_label(),
                    'worst': 'at_risk',
                    'items': [],
                },
            )
            group['items'].append(
                {
                    'subject': summary.subject_id.name,
                    'counted': summary.counted,
                    'limit': summary.limit,
                    'annual': regime == 'technical',
                    'excused': summary.excused,
                    'status': summary.status,
                }
            )
            if summary.status == 'failed':
                group['worst'] = 'failed'
        data['mine'] = sorted(students.values(), key=lambda g: (g['worst'] != 'failed', (g['name'] or '').lower()))
        # A turma que dirijo: o mapa da turma inteira.
        directed = (
            self.env['edu.class']
            .sudo()
            .search([('director_id', '=', employee.id), ('academic_year_id', '=', year.id)])
            .sorted(lambda c: (c.class_number, c.name or ''))
        )
        data['classes'] = [{'id': c.id, 'name': c._editor_label()} for c in directed]
        edu_class = directed.filtered(lambda c: c.id == class_id)[:1] or directed[:1]
        if edu_class:
            data['board'] = self._absence_board(edu_class, trimester)
        return data

    @api.model
    def _absence_board(self, edu_class, trimester):
        regime = edu_class._edu_regime()
        summaries = (
            self.env['edu.absence.summary']
            .sudo()
            .search([('trimester_id', '=', trimester.id), ('enrollment_id.class_id', '=', edu_class.id)])
        )
        subjects = summaries.subject_id.sorted(lambda s: s.name or '')
        by_key = {(s.enrollment_id.id, s.subject_id.id): s for s in summaries}
        enrollments = edu_class.enrollment_ids.filtered(lambda e: e.state in ('active', 'irregular')).sorted(
            lambda e: (e.order_number, e.student_id.name or '')
        )
        students = []
        counts = {'failed': 0, 'at_risk': 0}
        for enrollment in enrollments:
            cells = {}
            worst = 'ok'
            for subject in subjects:
                summary = by_key.get((enrollment.id, subject.id))
                if not summary:
                    continue
                cells[subject.id] = {
                    'counted': summary.counted,
                    'excused': summary.excused,
                    'limit': summary.limit,
                    'status': summary.status,
                }
                if summary.status == 'failed' or (summary.status == 'at_risk' and worst == 'ok'):
                    worst = summary.status
            if worst != 'ok':
                counts[worst] += 1
            students.append(
                {
                    'id': enrollment.id,
                    'number': enrollment.order_number or '',
                    'name': enrollment.student_id.name,
                    'worst': worst,
                    'cells': cells,
                }
            )
        return {
            'class_id': edu_class.id,
            'class': edu_class._editor_label(),
            'regime': regime,
            'subjects': [
                {'id': s.id, 'name': s.name, 'code': s.code or s.name, 'limit': absence_limit_of(edu_class, s)}
                for s in subjects
            ],
            'students': students,
            'failed': counts['failed'],
            'at_risk': counts['at_risk'],
        }


def absence_limit_of(edu_class, subject):
    """O limite de faltas injustificadas da disciplina na turma (o mesmo do resumo de faltas)."""
    return absence_limit(edu_class._edu_weekly_hours(subject), edu_class._edu_regime()) or 0
