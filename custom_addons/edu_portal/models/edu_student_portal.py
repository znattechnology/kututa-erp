from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models
from odoo.addons.edu_attendance.models.absence_rules import TECHNICAL, absence_limit, absence_status
from odoo.addons.edu_evaluation.tools import grading
from odoo.tools import format_amount

WEEKDAYS = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
MONTHS = [
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]  # fmt: skip
# A matrícula do ano que o aluno vê: as anuladas e as de quem saiu da escola não contam.
VISIBLE_STATES = ('draft', 'active', 'irregular', 'completed', 'retained')
ENROLLMENT_STATES = {
    'draft': 'À espera de confirmação',
    'active': 'Activa',
    'irregular': 'Activa, com propinas em atraso',
    'completed': 'Concluída',
    'retained': 'Retido',
}
RELATIONSHIPS = {
    'father': 'Pai',
    'mother': 'Mãe',
    'stepfather': 'Padrasto',
    'stepmother': 'Madrasta',
    'grandparent': 'Avô ou avó',
    'sibling': 'Irmão ou irmã',
    'uncle_aunt': 'Tio ou tia',
    'legal_guardian': 'Encarregado legal',
    'other': 'Familiar',
}
ABSENCE_STATUS = {
    'ok': 'Dentro do limite',
    'at_risk': 'A uma falta do limite',
    'failed': 'Limite ultrapassado',
}


def hhmm(value):
    """8.5 → «08:30»."""
    hours = int(value)
    return f'{hours:02d}:{round((value - hours) * 60):02d}'


def long_date(day):
    """«22 de outubro de 2026»."""
    return f'{day.day} de {MONTHS[day.month - 1]} de {day.year}' if day else ''


def grade_text(value):
    """As notas como no secPed: no máximo uma casa decimal, com vírgula (13,5; 14)."""
    if value is None:
        return '—'
    text = f'{round(value, 1):.1f}'.replace('.', ',')
    return text[:-2] if text.endswith(',0') else text


def plural(n, one, many):
    return one if n == 1 else f'{n} {many}'


class EduStudentPortal(models.AbstractModel):
    """A área do estudante (menu «Área do Estudante»), como a do secPed-Express: o painel, as notas, o horário, as
    provas, as faltas, as propinas e o perfil. O aluno é o do contacto do utilizador e tudo se lê em sudo, sempre
    filtrado a esse aluno: nada do que aqui se devolve vem de um identificador escolhido pelo browser."""

    _name = 'edu.student.portal'
    _description = 'Área do estudante'

    # O aluno e a matrícula

    @api.model
    def _student(self, user=None):
        """O aluno do utilizador (pelo contacto); com várias fichas, a que tem a matrícula mais recente."""
        user = user or self.env.user
        students = self.env['edu.student'].sudo().search([('partner_id', '=', user.partner_id.id)])
        if len(students) > 1:
            enrollments = (
                self.env['edu.enrollment']
                .sudo()
                .search([('student_id', 'in', students.ids)], order='academic_year_id desc, id desc', limit=1)
            )
            return enrollments.student_id or students[:1]
        return students

    @api.model
    def _enrollment(self, student):
        """A matrícula do ano lectivo em curso da escola do aluno."""
        return (
            self.env['edu.enrollment']
            .sudo()
            .search(
                [
                    ('student_id', '=', student.id),
                    ('academic_year_id.is_current', '=', True),
                    ('state', 'in', VISIBLE_STATES),
                ],
                order='id desc',
                limit=1,
            )
        )

    @api.model
    def _enrollments(self, student):
        """As matrículas do aluno em todos os anos (do mais recente para o mais antigo), menos as pendentes e as
        anuladas: as dos anos migrados do secPed também, com as notas da pauta assinada."""
        return (
            self.env['edu.enrollment']
            .sudo()
            .search([('student_id', '=', student.id), ('state', 'not in', ('draft', 'dropped'))])
            .sorted(lambda e: (e.academic_year_id.date_start, e.id), reverse=True)
        )

    @api.model
    def _now(self, student):
        """A data e a hora locais (o fuso do utilizador; por omissão o de Luanda)."""
        tz = pytz.timezone(self.env.user.tz or 'Africa/Luanda')
        return datetime.now(pytz.utc).astimezone(tz).replace(tzinfo=None)

    @api.model
    def _debt(self, student):
        """O aviso das propinas em atraso (sem isenção), como no secPed: o valor, desde quando e se bloqueia."""
        if not student.edu_in_debt or student.edu_gate_exempt:
            return None
        cutoff = fields.Date.context_today(self) - timedelta(days=student.company_id.edu_gate_grace_days or 0)
        overdue = student._edu_open_invoices().filtered(lambda m: m.invoice_date_due and m.invoice_date_due < cutoff)
        oldest = min(overdue.mapped('invoice_date_due')) if overdue else False
        return {
            'amount': format_amount(self.env, student.edu_overdue_amount, student.edu_currency_id),
            'since': oldest and oldest.strftime('%d/%m/%Y'),
            'enforced': student.company_id.edu_gate_mode == 'block',
        }

    @api.model
    def page_data(self, page, options=None):
        """Os dados de uma página da área do estudante (as acções cliente ``edu_portal.student_*``), sempre do aluno do
        utilizador: ``home``, ``grades`` (com ``{'trimester_id'}``), ``schedule``, ``exams``, ``absences``, ``fees`` e
        ``profile``."""
        options = options or {}
        student = self._student()
        data = {'has_student': bool(student), 'page': page}
        if not student:
            return data
        enrollment = self._enrollment(student)
        edu_class = enrollment.class_id
        data.update(
            {
                'name': student.name,
                'first_name': (student.name or '').split(' ')[0],
                'has_enrollment': bool(enrollment),
                'class': edu_class._editor_label() if edu_class else '',
                'level': edu_class.level_id.name or '',
                'year': enrollment.academic_year_id.name or '',
                'debt': self._debt(student) if page != 'fees' else None,
            }
        )
        if page == 'home':
            lessons = self.schedule(student, enrollment)
            exams = [row for period in self.exams(student, enrollment) for row in period['rows'] if not row['done']]
            data.update(
                {
                    'today': self.today(student, enrollment, lessons),
                    'has_schedule': bool(lessons),
                    'grades': self.grades(student, enrollment),
                    'absences': self.absences(student, enrollment),
                    'next_exams': exams[:3],
                }
            )
        elif page == 'grades':
            enrollments = self._enrollments(student)
            chosen = enrollments.filtered(lambda e: e.id == options.get('enrollment_id'))[:1]
            chosen = chosen or (enrollment if enrollment in enrollments else enrollments[:1])
            grades = self.grades(student, chosen, options.get('trimester_id'))
            grades['years'] = [
                {
                    'id': e.id,
                    'label': f'{e.academic_year_id.name}, {e.class_id._editor_label()}',
                    'current': e.academic_year_id.is_current,
                }
                for e in enrollments
            ]
            grades['enrollment_id'] = chosen.id
            data['grades'] = grades
        elif page == 'schedule':
            lessons = self.schedule(student, enrollment)
            data.update(
                {
                    'lessons': lessons,
                    'summary': self.schedule_summary(lessons) if lessons else '',
                    'grid': self.schedule_grid(lessons),
                }
            )
        elif page == 'exams':
            data['periods'] = self.exams(student, enrollment)
        elif page == 'absences':
            data['absences'] = self.absences(student, enrollment)
        elif page == 'fees':
            data['fees'] = self.fees(student)
        elif page == 'profile':
            data['profile'] = self.profile(student, enrollment)
        return data

    @api.model
    def change_password(self):
        """O assistente do Odoo para mudar a palavra-passe do próprio utilizador."""
        return self.env.user.preference_change_password()

    # Notas

    @api.model
    def grades(self, student, enrollment, trimester_id=None):
        """A pauta do aluno por trimestre, como a do secPed: as notas que formam o trimestre (no geral as contínuas, a
        MAC e a prova; no técnico a NPP e a NPT), a classificação do trimestre (MT ou CT, que no técnico engloba os
        anteriores) e as classificações do ano com as siglas da pauta (técnico CF, PG, CA, CFD; geral CA, EN, CF, CFD).
        As notas vêem-se logo que são lançadas. Com propinas em atraso, a escola pode escondê-las (modo «bloquear»)."""
        data = {'blocked': False, 'preschool': False, 'trimesters': [], 'subjects': [], 'year_result': None}
        if not enrollment:
            return data
        edu_class = enrollment.class_id
        data.update(
            {
                'year': enrollment.academic_year_id.name,
                'class': edu_class._editor_label(),
                'level': edu_class.level_id.name or '',
                'past': not enrollment.academic_year_id.is_current,
            }
        )
        blocked, _message = student._edu_gate('grades')
        if blocked:
            data['blocked'] = True
            return data
        if edu_class.level_id.code == 'INICIACAO':
            data['preschool'] = True
            return data
        policy = self.env['edu.evaluation.policy']._get(enrollment.company_id, edu_class.level_id)
        technical = policy.regime == TECHNICAL
        round_fn = grading.rounder(policy.rounding)
        trimesters = enrollment.academic_year_id.trimester_ids.sorted('number')
        last = trimesters[-1:]
        exam_class = policy._is_exam_class(edu_class.class_number)
        terms = self.env['edu.term.result'].sudo().search([('enrollment_id', '=', enrollment.id)])
        term_by_key = {(t.subject_id.id, t.trimester_id.id): t for t in terms}
        results = self.env['edu.subject.result'].sudo().search([('enrollment_id', '=', enrollment.id)])
        result_by_subject = {r.subject_id.id: r for r in results}
        continuous = (
            self.env['edu.grade']
            .sudo()
            .search(
                [('enrollment_id', '=', enrollment.id), ('assessment_type', '=', 'continuous'), ('graded', '=', True)],
                order='id',
            )
        )
        subjects = (enrollment.subject_ids | results.subject_id).sorted(lambda s: (s.name or '').lower())

        def value(record, field, flag):
            return record[field] if record and record[flag] else None

        rows = []
        for subject in subjects:
            result = result_by_subject.get(subject.id)
            classifications = result._trimester_classifications() if result else [None] * len(trimesters)
            by_trimester = {}
            for trimester, classification in zip(trimesters, classifications, strict=True):
                term = term_by_key.get((subject.id, trimester.id))
                parts = continuous.filtered(lambda g, s=subject, t=trimester: g.subject_id == s and g.trimester_id == t)
                by_trimester[trimester.id] = {
                    'components': [
                        {
                            'name': g.assessment_id.name,
                            'value': grading.normalise(g.score, g.assessment_id.max_score, policy.scale_max),
                        }
                        for g in parts
                    ],
                    'mac': value(term, 'mac', 'has_mac'),
                    'npt': value(term, 'npt', 'has_npt'),
                    'ct': classification,
                }
            span_terminal = result._subject_span() if result else ([edu_class.class_number], True)
            complete = bool(result and result.complete)
            rows.append(
                {
                    'id': subject.id,
                    'name': subject.name,
                    'code': subject.code or '',
                    'by_trimester': by_trimester,
                    'cf': result.cf if result and result.trimesters_graded else None,
                    'pg': result.pg if result and result.has_pg else None,
                    'national': result.national if result and result.has_national else None,
                    'annual': result.annual if complete else None,
                    'final': result.final if complete else None,
                    'cfd': result.cfd if complete and result.terminal_subject and len(span_terminal[0]) > 1 else None,
                }
            )
        data.update(
            {
                'technical': technical,
                'pass_grade': policy.pass_grade,
                'pass_text': grade_text(policy.pass_grade),
                'subjects': rows,
                'trimesters': [
                    {
                        'id': t.id,
                        'number': t.number,
                        'name': t.name,
                        # Sem prova trimestral no último trimestre: no técnico (há a prova global) e na classe de exame.
                        'has_npt': not ((technical or exam_class) and t == last),
                    }
                    for t in trimesters
                ],
                'show_pg': any(r['pg'] is not None for r in rows),
                'show_national': any(r['national'] is not None for r in rows),
            }
        )
        # O trimestre aberto: o pedido, ou o último que já tem alguma nota.
        with_grades = [
            t['id']
            for t in data['trimesters']
            if any(
                r['by_trimester'][t['id']]['ct'] is not None or r['by_trimester'][t['id']]['components'] for r in rows
            )
        ]
        ids = [t['id'] for t in data['trimesters']]
        # Sem notas, o trimestre corrente (ou o primeiro).
        current = trimesters.filtered('is_current')[:1].id or (ids[0] if ids else None)
        if trimester_id in ids:
            active = trimester_id
        else:
            active = with_grades[-1] if with_grades else current
        data['active'] = next((t for t in data['trimesters'] if t['id'] == active), None)
        data['components'] = (
            0
            if technical or not active
            else max((len(r['by_trimester'][active]['components']) for r in rows), default=0)
        )
        data['summary'] = self._grades_summary(data, rows, active, round_fn)
        data['year_result'] = self._year_result(enrollment)

        # Para o browser: cada nota já escrita como no secPed e marcada positiva ou negativa (pela regra de
        # arredondamento da escola: 9,5 é positiva onde se arredonda).
        def cell(v):
            return None if v is None else {'text': grade_text(v), 'pos': round_fn(v) >= policy.pass_grade}

        for row in rows:
            for item in row['by_trimester'].values():
                for key in ('mac', 'npt', 'ct'):
                    item[key] = cell(item[key])
                for component in item['components']:
                    component['value'] = cell(component['value'])
            for key in ('cf', 'pg', 'national', 'annual', 'final', 'cfd'):
                row[key] = cell(row[key])
        return data

    @api.model
    def _grades_summary(self, data, rows, active, round_fn):
        """A frase de cima: quantas disciplinas têm nota no trimestre, a média e as negativas."""
        if not active:
            return ''
        graded = [r for r in rows if r['by_trimester'][active]['ct'] is not None]
        name = data['active']['name']
        if not graded:
            if data.get('past'):
                return f'Não há notas do {name} neste ano lectivo.'
            return f'Ainda não tens notas no {name}. Aparecem aqui logo que os professores as lançam.'
        average = sum(r['by_trimester'][active]['ct'] for r in graded) / len(graded)
        negatives = [r['name'] for r in graded if round_fn(r['by_trimester'][active]['ct']) < data['pass_grade']]
        text = (
            f'No {name} {"tiveste" if data.get("past") else "tens"} nota a '
            f'{plural(len(graded), "uma disciplina", "disciplinas")}, '
            f'com média de {grade_text(average)}. '
        )
        if not negatives:
            if data.get('past'):
                return text + ('Positiva a todas.' if len(graded) > 1 else 'Foi positiva.')
            return text + ('Positiva a todas.' if len(graded) > 1 else 'É positiva.')
        return text + (f'{plural(len(negatives), "Uma negativa", "negativas").capitalize()}: {", ".join(negatives)}.')

    @api.model
    def _year_result(self, enrollment):
        """A decisão do ano (transita, retido, concluiu…), quando já existe: a média e as disciplinas negativas."""
        result = self.env['edu.year.result'].sudo().search([('enrollment_id', '=', enrollment.id)], limit=1)
        if not result or result.status == 'pending':
            return None
        status = dict(result._fields['status']._description_selection(self.env))[result.status]
        return {
            'status': status,
            'good': result.status in ('promoted', 'graduated'),
            'bad': result.status == 'retained',
            'average': grade_text(result.average) if result.average else '',
            'negatives': sorted(result.negative_subject_ids.mapped('name'), key=str.lower),
            'absence': result.absence_excluded,
        }

    # Horário

    @api.model
    def schedule(self, student, enrollment):
        """O horário da turma que está a decorrer (os tempos do ano e os do trimestre em curso)."""
        if not enrollment:
            return []
        entries = enrollment.class_id.sudo()._edu_current_schedules().sorted(lambda s: (s.weekday, s.hour_from))
        return [
            {
                'id': entry.id,
                'weekday': int(entry.weekday),
                'start': entry.hour_from,
                'end': entry.hour_to,
                'hours': f'{hhmm(entry.hour_from)}–{hhmm(entry.hour_to)}',
                'subject': entry.subject_id.name,
                'teacher': entry.teacher_id.name or '',
                'room': entry.room_id.display_name or '',
            }
            for entry in entries
        ]

    @api.model
    def schedule_summary(self, lessons):
        """«28 aulas por semana, de segunda a sexta, em 11 disciplinas.»"""
        days = sorted({lesson['weekday'] for lesson in lessons})
        names = [WEEKDAYS[d] for d in days]
        consecutive = all(i == 0 or d == days[i - 1] + 1 for i, d in enumerate(days))
        if len(names) > 2 and consecutive:
            span = f'de {names[0]} a {names[-1]}'
        elif len(names) == 1:
            span = f'à {names[0]}'
        else:
            span = f'{", ".join(names[:-1])} e {names[-1]}'
        subjects = len({lesson['subject'] for lesson in lessons})
        return (
            f'{plural(len(lessons), "Uma aula", "aulas")} por semana, {span}, '
            f'em {plural(subjects, "uma disciplina", "disciplinas")}.'
        ).capitalize()

    @api.model
    def schedule_grid(self, lessons):
        """A semana em colunas (os dias com aulas), com cada aula numa linha por hora de início."""
        days = sorted({lesson['weekday'] for lesson in lessons} | {0, 1, 2, 3, 4})
        starts = sorted({(lesson['start'], lesson['end']) for lesson in lessons})
        rows = []
        for start, end in starts:
            cells = {
                d: [lesson for lesson in lessons if lesson['weekday'] == d and lesson['start'] == start] for d in days
            }
            rows.append({'hours': f'{hhmm(start)}–{hhmm(end)}', 'cells': cells})
        return {'days': [{'number': d, 'name': WEEKDAYS[d]} for d in days], 'rows': rows}

    @api.model
    def today(self, student, enrollment, lessons):
        """«Hoje»: a aula a decorrer ou a seguinte, e o resto das de hoje; sem aulas por dar, a primeira do próximo dia
        de aulas (os feriados e as pausas do calendário escolar não têm aulas)."""
        now = self._now(student)
        today = now.date()
        minute = now.hour + now.minute / 60
        edu_class = enrollment.class_id
        Calendar = self.env['edu.calendar.event'].sudo()

        def lessons_on(day):
            if edu_class and day in Calendar._days_without_lessons(edu_class.company_id, edu_class.level_id, day, day):
                return []
            return [lesson for lesson in lessons if lesson['weekday'] == day.weekday()]

        todays = lessons_on(today)
        following = next((lesson for lesson in todays if lesson['end'] > minute), None)
        data = {
            'title': f'Hoje, {WEEKDAYS[today.weekday()]}',
            'next': following,
            'now': bool(following and following['start'] <= minute),
            'rest': [lesson for lesson in todays if following and lesson['start'] > following['start']],
            'had_lessons': bool(todays),
            'holiday': bool(lessons)
            and not todays
            and bool([lesson for lesson in lessons if lesson['weekday'] == today.weekday()]),
            'next_day': None,
        }
        if not following:
            for ahead in range(1, 15):
                day = today + timedelta(days=ahead)
                found = lessons_on(day)
                if found:
                    when = (
                        'Amanhã'
                        if ahead == 1
                        else ('No' if day.weekday() >= 5 else 'Na') + f' {WEEKDAYS[day.weekday()]}'
                    )
                    data['next_day'] = {'when': when, 'lesson': found[0]}
                    break
        return data

    # Provas

    @api.model
    def exams(self, student, enrollment):
        """As provas da turma (e as que o aluno tem marcadas noutras sessões, como os exames especiais), por época:
        o dia, a hora, a disciplina, a sala e quem vigia (as mesmas que o professor vê nas «Vigilâncias»)."""
        if not enrollment:
            return []
        sessions = (
            self.env['edu.exam.session']
            .sudo()
            .search(
                [
                    '|',
                    ('class_ids', 'in', enrollment.class_id.ids),
                    ('seat_ids.enrollment_id', '=', enrollment.id),
                    ('state', '!=', 'cancelled'),
                    ('academic_year_id', '=', enrollment.academic_year_id.id),
                ]
            )
            .sorted(lambda s: (s.date, s.hour_from, s.id))
        )
        today = self._now(student).date()
        periods = {}
        for session in sessions:
            period = session.period_id
            group = periods.setdefault(
                period.id,
                {
                    'name': period.name,
                    'span': f'{period.date_start.strftime("%d/%m")} a {period.date_end.strftime("%d/%m/%Y")}',
                    'start': fields.Date.to_string(period.date_start),
                    'rows': [],
                },
            )
            seat = session.seat_ids.filtered(lambda s: s.enrollment_id == enrollment)[:1]
            rooms = seat.room_id or session.room_ids
            group['rows'].append(
                {
                    'id': session.id,
                    'date': fields.Date.to_string(session.date),
                    'day': f'{WEEKDAYS[session.date.weekday()].capitalize()}, {session.date.strftime("%d/%m")}',
                    'hours': f'{hhmm(session.hour_from)}–{hhmm(session.hour_to)}',
                    'subject': session.subject_id.name,
                    'rooms': ', '.join(rooms.room_id.mapped('display_name')),
                    'supervisors': ', '.join(rooms.supervisor_ids.mapped('name')),
                    'done': session.state == 'done' or session.date < today,
                }
            )
        return sorted(periods.values(), key=lambda p: p['start'])

    # Faltas

    @api.model
    def absences(self, student, enrollment):
        """As faltas pela regra que conta (a mesma do relatório do director de turma): no técnico, o limite anual de
        faltas injustificadas, o triplo dos tempos semanais; no geral, 3, 4 ou 5 por trimestre (o corrente)."""
        data = {'subjects': [], 'total': 0, 'present': 0, 'regime': None, 'window': ''}
        if not enrollment:
            return data
        rows = self.env['edu.absence.summary'].sudo().search([('enrollment_id', '=', enrollment.id)])
        edu_class = enrollment.class_id
        regime = edu_class._edu_regime()
        trimesters = enrollment.academic_year_id.trimester_ids.sorted('number')
        window = trimesters.filtered('is_current')[:1] or rows.trimester_id.sorted('number')[-1:]
        data['regime'] = regime
        data['window'] = window.name or ''
        subjects = {}
        for row in rows:
            item = subjects.setdefault(
                row.subject_id.id,
                {
                    'name': row.subject_id.name,
                    'class': row.class_id,
                    'subject': row.subject_id,
                    'total': 0,
                    'present': 0,
                    'late': 0,
                    'absent': 0,
                    'excused': 0,
                    'window_absent': 0,
                },
            )
            item['total'] += row.lessons
            item['present'] += row.present + row.late
            item['late'] += row.late
            item['absent'] += row.absent
            item['excused'] += row.excused
            if row.trimester_id == window:
                item['window_absent'] += row.absent
        for item in subjects.values():
            subject_class = item.pop('class')
            limit = absence_limit(subject_class._edu_weekly_hours(item.pop('subject')), regime)
            counted = item['absent'] if regime == TECHNICAL else item['window_absent']
            status = absence_status(counted, limit, regime)
            item.update(
                {
                    'limit': limit,
                    'counted': counted,
                    'status': status,
                    'status_label': ABSENCE_STATUS[status],
                    'rate': round(100 * item['present'] / item['total']) if item['total'] else None,
                }
            )
        data['subjects'] = sorted(subjects.values(), key=lambda s: (s['name'] or '').lower())
        data['total'] = sum(s['total'] for s in data['subjects'])
        data['present'] = sum(s['present'] for s in data['subjects'])
        data['rate'] = round(100 * data['present'] / data['total']) if data['total'] else None
        data['absent'] = sum(s['absent'] for s in data['subjects'])
        data['excused'] = sum(s['excused'] for s in data['subjects'])
        data['late'] = sum(s['late'] for s in data['subjects'])
        data['failed'] = [s['name'] for s in data['subjects'] if s['status'] == 'failed']
        data['at_risk'] = [s['name'] for s in data['subjects'] if s['status'] == 'at_risk']
        return data

    # Propinas

    @api.model
    def fees(self, student):
        """As facturas escolares do aluno, só para ler (quem paga é o encarregado): por pagar, pagas e isentas ou
        anuladas. As multas por atraso (facturas à parte no Odoo) somam-se à factura que as originou."""
        moves = (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('edu_student_id', '=', student.id),
                    ('move_type', '=', 'out_invoice'),
                    ('state', 'in', ('posted', 'cancel')),
                ],
                order='invoice_date_due, id',
            )
        )
        late_fees = moves.filtered(lambda m: m.edu_category == 'late_fee' and m.edu_late_fee_origin_id in moves)
        today = fields.Date.context_today(self)
        currency = student.edu_currency_id

        def money(amount):
            return format_amount(self.env, amount, currency)

        rows = []
        for move in moves - late_fees:
            fines = late_fees.filtered(lambda m, o=move: m.edu_late_fee_origin_id == o and m.state == 'posted')
            fine = sum(fines.mapped('amount_residual'))
            due = move.amount_residual + fine if move.state == 'posted' else 0.0
            if move.state == 'cancel' or move.edu_exempt:
                tab, status, css = 'other', 'Isenta' if move.edu_exempt else 'Anulada', 'muted'
            elif due > 0.005:
                tab = 'due'
                overdue = move.invoice_date_due and move.invoice_date_due < today and move.amount_residual > 0.005
                if move.payment_state == 'partial':
                    status, css = 'Paga em parte', 'warn'
                elif overdue:
                    status, css = 'Em atraso', 'bad'
                else:
                    status, css = 'Por pagar', ''
            else:
                tab, status, css = 'paid', 'Paga', 'good'
            line = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')[:1]
            rows.append(
                {
                    'id': move.id,
                    'tab': tab,
                    'name': line.name or move.name,
                    'number': move.name,
                    'due_date': move.invoice_date_due and move.invoice_date_due.strftime('%d/%m/%Y'),
                    'amount': money(move.amount_total),
                    'fine': money(fine) if fine else '',
                    'due': money(due),
                    'due_value': due,
                    'fine_value': fine,
                    'status': status,
                    'css': css,
                }
            )
        due_rows = [r for r in rows if r['tab'] == 'due']
        overdue = [r for r in due_rows if r['css'] == 'bad']
        return {
            'rows': rows,
            'due': due_rows,
            'paid': [r for r in rows if r['tab'] == 'paid'],
            'other': [r for r in rows if r['tab'] == 'other'],
            'total_due': money(sum(r['due_value'] for r in due_rows)),
            'total_fines': money(sum(r['fine_value'] for r in due_rows)),
            'has_fines': any(r['fine_value'] for r in due_rows),
            'overdue': len(overdue),
        }

    # Perfil

    @api.model
    def profile(self, student, enrollment):
        """A matrícula, os dados pessoais (com os que faltam para os certificados) e os encarregados."""
        missing = [
            label
            for label, filled in (
                ('a data de nascimento', student.birth_date),
                ('o n.º do BI', student.id_number),
                ('a naturalidade', student.birthplace),
                ('o nome do pai', student.father_name),
                ('o nome da mãe', student.mother_name),
            )
            if not filled
        ]
        if len(missing) > 1:
            missing_text = f'{", ".join(missing[:-1])} e {missing[-1]}'
        else:
            missing_text = missing[0] if missing else ''
        guardians = [
            {
                'name': link.guardian_id.name,
                'relationship': RELATIONSHIPS.get(link.relationship, 'Familiar'),
                'primary': link.is_primary,
                'phone': link.guardian_id.phone or '',
                'email': link.guardian_id.email or '',
            }
            for link in student.guardian_link_ids.sorted(lambda g: (not g.is_primary, g.guardian_id.name or ''))
        ]
        edu_class = enrollment.class_id
        return {
            'enrollment': {
                'course': edu_class.course_id.name or '',
                'class': edu_class._editor_label(),
                'year': enrollment.academic_year_id.name,
                'level': edu_class.level_id.name or '',
                'state': ENROLLMENT_STATES.get(enrollment.state, ''),
                'irregular': enrollment.state == 'irregular',
                'subjects': sorted(enrollment.subject_ids.mapped('name'), key=str.lower),
            }
            if enrollment
            else None,
            'name': student.name,
            'email': student.email or '',
            'phone': student.phone or '',
            'matricula': student.matricula_number or '',
            'id_number': student.id_number or '',
            'birth_date': long_date(student.birth_date),
            'gender': dict(student._fields['gender'].selection).get(student.gender, ''),
            'birthplace': ', '.join(p for p in [student.birthplace, student.birth_state_id.name] if p),
            'address': ', '.join(p for p in [student.street, student.city] if p),
            'filiation': ' e '.join(p for p in [student.father_name, student.mother_name] if p),
            'missing': missing_text,
            'guardians': guardians,
        }
