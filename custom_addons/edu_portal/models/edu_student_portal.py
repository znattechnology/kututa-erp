from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytz

from odoo import api, fields, models
from odoo.addons.edu_attendance.models.absence_rules import TECHNICAL, absence_limit, absence_status
from odoo.addons.edu_evaluation.tools import grading
from odoo.addons.edu_exam.models.edu_exam import SPECIAL
from odoo.exceptions import UserError
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
# As novidades (Notificações): o que mudou nos últimos dias (as notas lançadas, as faltas, as provas marcadas, as
# facturas e os pagamentos e os relatórios da Iniciação completos).
FEED_DAYS = 30
FEED_LIMIT = 100
ABSENCE_KINDS = {'absent': 'falta injustificada', 'excused': 'falta justificada', 'late': 'atraso'}
# As bandas da escala de 0 a 20 que o secPed usa na «Situação» da pauta do aluno (a sua GradeScale).
SCALE_BANDS = [(0, 9.99, 'Insuficiente'), (10, 13.99, 'Suficiente'), (14, 16.99, 'Bom'), (17, 20, 'Excelente')]
# Os nomes da regra que conta: no técnico reprova-se ao passar o limite (em risco quando o atinge); no geral, ao
# atingi-lo (em risco a uma falta).
ABSENCE_STATUS = {
    TECHNICAL: {'ok': 'Dentro do limite', 'at_risk': 'No limite', 'failed': 'Limite ultrapassado'},
    'general': {'ok': 'Dentro do limite', 'at_risk': 'A uma falta do limite', 'failed': 'Limite atingido'},
}


def hhmm(value):
    """8.5 → «08:30»."""
    minutes = round(value * 60)
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def long_date(day):
    """«22 de outubro de 2026»."""
    return f'{day.day} de {MONTHS[day.month - 1]} de {day.year}' if day else ''


def day_label(day):
    """«Quarta-feira, 9 de Dezembro», como no calendário de provas do secPed."""
    return f'{WEEKDAYS[day.weekday()].capitalize()}, {day.day} de {MONTHS[day.month - 1].capitalize()}'


def one_decimal(value):
    """Uma casa decimal, com vírgula e arredondada para cima a partir de 5 (12,25 → «12,3»)."""
    return str(Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)).replace('.', ',')


def grade_text(value):
    """As notas como no secPed: no máximo uma casa decimal, com vírgula (13,5; 14)."""
    if value is None:
        return '—'
    text = one_decimal(value)
    return text[:-2] if text.endswith(',0') else text


def first_name(name):
    return (name or '').split(' ')[0]


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
        cutoff = self._now(student).date() - timedelta(days=student.company_id.edu_gate_grace_days or 0)
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
        utilizador: ``home``, ``grades`` (com ``{'trimester_id'}``), ``schedule``, ``exams``, ``absences``, ``fees``,
        ``profile``, ``internship``, ``project``, ``history`` e ``notifications``."""
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
            exams = [row for row in self.exams(student, enrollment)['rows'] if not row['done']]
            data.update(
                {
                    'today': self.today(student, enrollment, lessons),
                    'has_schedule': bool(lessons),
                    'grades': self.grades(student, enrollment),
                    'absences': self.absences(student, enrollment),
                    'next_exams': exams[:3],
                    'exams_left': len(exams),
                }
            )
            fees = self.fees(student)
            data['fees_summary'] = {
                'count': len(fees['due']),
                'total': fees['total_due'],
                'overdue': fees['overdue'],
                'overdue_total': fees['overdue_total'],
                'invoiced': bool(fees['rows']),
            }
            data['feed'] = self._feed(student)[:5]
        elif page == 'grades':
            data['grades'] = self._grades_page(student, enrollment, options)
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
            data['exams'] = self.exams(student, enrollment)
        elif page == 'absences':
            data['absences'] = self.absences(student, enrollment)
            data['absence_months'] = self._absence_months(student, enrollment)
            data['recent'] = self._recent_absences(enrollment)
        elif page == 'fees':
            data['fees'] = self.fees(student)
            data['months'] = self._tuition_months(student, enrollment)
        elif page == 'profile':
            data['profile'] = self.profile(student, enrollment)
        elif page == 'internship':
            data['internships'] = self.internships(student)
        elif page == 'project':
            data['projects'] = self.projects(student)
        elif page == 'history':
            data['history'] = self._history(student)
        elif page == 'notifications':
            data['feed'] = self._feed(student)
        return data

    @api.model
    def _grades_page(self, student, enrollment, options):
        """A página das notas (a do aluno e a do encarregado): o ano escolhido (por omissão o corrente) e os anos com
        matrícula, para escolher."""
        enrollments = self._enrollments(student)
        chosen = enrollments.filtered(lambda e: e.id == options.get('enrollment_id'))[:1]
        # O encarregado que muda de educando fica no mesmo ano lectivo, se o outro educando tiver matrícula nele.
        year_id = options.get('academic_year_id')
        if not chosen and year_id:
            chosen = enrollments.filtered(lambda e: e.academic_year_id.id == year_id)[:1]
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
        grades['academic_year_id'] = chosen.academic_year_id.id
        # O ano pedido em que o aluno não tem matrícula (a página diz que mostra outro).
        missing = (
            year_id and year_id != chosen.academic_year_id.id and self.env['edu.academic.year'].sudo().browse(year_id)
        )
        grades['year_missing'] = missing.name if missing and missing.exists() else ''
        return grades

    @api.model
    def schedule_report(self, preview=True):
        """O horário da turma em folha A4 horizontal, como o do professor: na aplicação (Visualizar) ou em PDF
        (Exportar PDF)."""
        student = self._student()
        enrollment = self._enrollment(student) if student else None
        if not enrollment:
            raise UserError(self.env._('Não tens matrícula neste ano lectivo, por isso não há horário.'))
        report = self.env.ref('edu_documents.action_report_class_schedule')
        edu_class = enrollment.class_id
        return report.preview_action(edu_class) if preview else report.report_action(edu_class)

    @api.model
    def change_password(self):
        """O assistente do Odoo para mudar a palavra-passe do próprio utilizador."""
        return self.env.user.preference_change_password()

    # Notas

    @api.private
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
        # As disciplinas anuladas não contam (nem nas médias), como na grelha e na decisão do ano.
        dropped = enrollment._dropped_subjects()
        subjects = (enrollment.subject_ids | results.subject_id) - dropped
        subjects = subjects.sorted(lambda s: (s.name or '').lower())

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
                    # A que conta na decisão do ano (a CFD no ano terminal de uma disciplina plurianual) e se aprova.
                    'transition': result.transition_grade if complete else None,
                    'passed': result.passed if complete else None,
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
        summary = self._grades_summary(data, rows, active, round_fn)
        data['summary'] = summary['text']
        data['summary_parts'] = summary
        # A situação, como no secPed: no último trimestre, a banda da escala da nota com que o aluno fecha a disciplina
        # (a final, ou a do último trimestre enquanto não há final).
        last_id = data['trimesters'][-1]['id'] if data['trimesters'] else None
        data['show_situation'] = False
        for row in rows:
            row['situation'] = None
            last_ct = row['by_trimester'][last_id]['ct'] if last_id else None
            if active != last_id or last_ct is None:
                continue
            # Fechada a disciplina, conta o que conta na decisão do ano: a nota para a transição e se aprova.
            value = row['transition'] if row['transition'] is not None else last_ct
            rounded = round_fn(value)
            positive = row['passed'] if row['passed'] is not None else rounded >= policy.pass_grade
            label = 'Positiva' if positive else 'Negativa'
            if policy.scale_max == 20:
                label = next((band for low, high, band in SCALE_BANDS if low <= rounded <= high), label)
            row['situation'] = {'label': label, 'pos': positive}
            data['show_situation'] = True
        data['year_result'] = self._year_result(enrollment)

        # Para o browser: cada nota já escrita como no secPed e marcada positiva ou negativa (pela regra de
        # arredondamento da escola: 9,5 é positiva onde se arredonda).
        # Para o painel: a média de cada trimestre (das disciplinas com nota) e a média do ano até agora (todas as
        # classificações dos trimestres, como no secPed).
        data['trend'] = []
        every = []
        for trimester in data['trimesters']:
            values = [r['by_trimester'][trimester['id']]['ct'] for r in rows]
            values = [v for v in values if v is not None]
            every += values
            mean = sum(values) / len(values) if values else None
            data['trend'].append(
                {
                    'id': trimester['id'],
                    'name': trimester['name'],
                    'value': round(mean, 2) if mean is not None else None,
                    'text': one_decimal(mean) if mean is not None else '',
                    'pos': mean is not None and round_fn(mean) >= policy.pass_grade,
                    'count': len(values),
                }
            )
        year_average = sum(every) / len(every) if every else None
        data['year_average'] = (
            {
                'text': one_decimal(year_average),
                'pos': round_fn(year_average) >= policy.pass_grade,
            }
            if year_average is not None
            else None
        )
        data['scale_max'] = policy.scale_max

        def cell(v):
            if v is None:
                return None
            return {'text': grade_text(v), 'pos': round_fn(v) >= policy.pass_grade, 'value': round(v, 2)}

        for row in rows:
            for item in row['by_trimester'].values():
                for key in ('mac', 'npt', 'ct'):
                    item[key] = cell(item[key])
                for component in item['components']:
                    component['value'] = cell(component['value'])
            for key in ('cf', 'pg', 'national', 'annual', 'final', 'cfd'):
                row[key] = cell(row[key])
            del row['transition'], row['passed']
        return data

    @api.model
    def _grades_summary(self, data, rows, active, round_fn):
        """A frase de cima, como no secPed: a média do trimestre (com uma casa decimal), se subiu ou desceu face ao
        anterior (só quando os dois têm nota nas mesmas disciplinas) e quantas negativas há."""
        if not active:
            return {'text': '', 'empty': True}
        name = data['active']['name'].replace('Trimestre', 'trimestre')
        graded = [r for r in rows if r['by_trimester'][active]['ct'] is not None]
        if not graded:
            text = (
                f'Não há notas do {name} neste ano lectivo.' if data.get('past') else f'Ainda não há notas do {name}.'
            )
            return {'text': text, 'empty': True}

        def mean(trimester_id):
            values = [r['by_trimester'][trimester_id]['ct'] for r in rows]
            values = [v for v in values if v is not None]
            return sum(values) / len(values) if values else None

        average = mean(active)
        negatives = [r for r in graded if round_fn(r['by_trimester'][active]['ct']) < data['pass_grade']]
        ids = [t['id'] for t in data['trimesters']]
        index = ids.index(active)
        previous = None
        if index > 0:
            before = data['trimesters'][index - 1]
            comparable = all(
                (r['by_trimester'][active]['ct'] is None) == (r['by_trimester'][before['id']]['ct'] is None)
                for r in rows
            )
            if comparable:
                now, then = one_decimal(average), one_decimal(mean(before['id']))
                now, then = float(now.replace(',', '.')), float(then.replace(',', '.'))
                previous = {
                    'trend': 'subiu face aos' if now > then else ('desceu face aos' if now < then else 'igual ao'),
                    'average': one_decimal(mean(before['id'])),
                    'name': before['name'].replace('Trimestre', 'trimestre'),
                }
        n = len(graded)
        if not negatives:
            tail = f'com positiva a {"uma disciplina" if n == 1 else f"todas as {n} disciplinas"}'
        else:
            k = len(negatives)
            subjects = 'disciplina' if n == 1 else 'disciplinas'
            tail = f'com {"uma negativa" if k == 1 else f"{k} negativas"} em {n} {subjects}'
        parts = {
            'empty': False,
            'trimester': name,
            'average': one_decimal(average),
            # Positiva pela regra de arredondamento da escola, como as notas de cada disciplina.
            'average_pos': round_fn(average) >= data['pass_grade'],
            'previous': previous,
            'tail': tail,
        }
        trend = f' ({previous["trend"]} {previous["average"]} do {previous["name"]})' if previous else ''
        parts['text'] = f'No {name} a média é {parts["average"]}{trend}, {tail}.'
        return parts

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

    @api.private
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

    @api.private
    @api.model
    def schedule_summary(self, lessons):
        """«28 aulas por semana, de segunda a sexta, em 11 disciplinas.»"""
        days = sorted({lesson['weekday'] for lesson in lessons})
        names = [WEEKDAYS[d] for d in days]
        consecutive = all(i == 0 or d == days[i - 1] + 1 for i, d in enumerate(days))
        if len(names) > 2 and consecutive:
            span = f'de {names[0]} a {names[-1]}'
        elif len(names) == 1:
            span = f'{"ao" if days[0] >= 5 else "à"} {names[0]}'
        else:
            span = f'{", ".join(names[:-1])} e {names[-1]}'
        subjects = len({lesson['subject'] for lesson in lessons})
        return (
            f'{plural(len(lessons), "Uma aula", "aulas")} por semana, {span}, '
            f'em {plural(subjects, "uma disciplina", "disciplinas")}.'
        ).capitalize()

    @api.private
    @api.model
    def schedule_grid(self, lessons):
        """A semana em colunas (os dias com aulas), com cada aula na linha do seu tempo (início e fim)."""
        days = sorted({lesson['weekday'] for lesson in lessons} | {0, 1, 2, 3, 4})
        starts = sorted({(lesson['start'], lesson['end']) for lesson in lessons})
        rows = []
        for start, end in starts:
            cells = {
                d: [
                    lesson
                    for lesson in lessons
                    if lesson['weekday'] == d and lesson['start'] == start and lesson['end'] == end
                ]
                for d in days
            }
            rows.append({'hours': f'{hhmm(start)}–{hhmm(end)}', 'cells': cells})
        return {'days': [{'number': d, 'name': WEEKDAYS[d]} for d in days], 'rows': rows}

    @api.private
    @api.model
    def today(self, student, enrollment, lessons):
        """«Hoje»: a aula a decorrer ou a seguinte, e o resto das de hoje; sem aulas por dar, a primeira do próximo dia
        de aulas (os feriados e as pausas do calendário escolar não têm aulas)."""
        now = self._now(student)
        today = now.date()
        minute = now.hour + now.minute / 60
        edu_class = enrollment.class_id
        # Como no painel do professor: os feriados e as pausas do calendário escolar, as aulas sem realização, os
        # limites do trimestre e do ano, e o professor substituto nesse dia.
        holidays = (
            self.env['edu.calendar.event']
            .sudo()
            ._days_without_lessons(edu_class.company_id, edu_class.level_id, today, today + timedelta(days=14))
            if edu_class
            else set()
        )
        entries = {entry.id: entry for entry in self.env['edu.schedule'].sudo().browse([x['id'] for x in lessons])}

        def lessons_on(day):
            if day in holidays:
                return []
            found = []
            for lesson in lessons:
                entry = entries[lesson['id']]
                if lesson['weekday'] != day.weekday() or not entry._occurs_on(day):
                    continue
                teacher = entry._teacher_on(day)
                found.append({**lesson, 'teacher': teacher.name or '', 'replacement': teacher != entry.teacher_id})
            return found

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
                    data['next_day'] = {'when': when, 'lesson': found[0], 'lessons': found}
                    break
        return data

    # Provas

    @api.private
    @api.model
    def exams(self, student, enrollment):
        """As provas da turma (e as que o aluno tem marcadas noutras sessões, como os exames especiais), como no
        secPed: uma tabela por época, com o dia (só na primeira prova desse dia), a hora, a disciplina, a sala e quem
        vigia; e a frase de cima com quantas provas há, em quantos dias, e a próxima."""
        data = {'periods': [], 'rows': [], 'count': 0, 'days': 0, 'next': None}
        if not enrollment:
            return data
        # As provas da turma nas disciplinas que o aluno faz nela (sem as anuladas e as feitas numa turma da classe
        # anterior, que contam nessa turma); os recursos, os extraordinários, as melhorias e a época de conclusão só
        # para quem foi convocado (o lugar pode estar numa matrícula de um ano anterior, nas disciplinas em atraso).
        own = enrollment.subject_ids - enrollment._dropped_subjects() - enrollment.lower_subject_ids.subject_id
        pairs = {(enrollment.class_id.id, subject.id) for subject in own} | {
            (lower.class_id.id, lower.subject_id.id)
            for lower in enrollment.lower_subject_ids
            if lower.subject_id not in enrollment._dropped_subjects()
        }
        sessions = (
            self.env['edu.exam.session']
            .sudo()
            .search(
                [
                    '|',
                    '&',
                    ('class_ids', 'in', [class_id for class_id, _subject in pairs]),
                    ('kind', 'not in', SPECIAL),
                    ('seat_ids.student_id', '=', student.id),
                    ('state', '!=', 'cancelled'),
                    ('academic_year_id', '=', enrollment.academic_year_id.id),
                ]
            )
            .filtered(
                lambda s: (
                    s.seat_ids.filtered(lambda seat: seat.student_id == student)
                    or any((c.id, s.subject_id.id) in pairs for c in s.class_ids)
                )
            )
            .sorted(lambda s: (s.date, s.hour_from, s.id))
        )
        now = self._now(student)
        today, minute = now.date(), now.hour + now.minute / 60
        periods = {}
        for session in sessions:
            period = session.period_id
            group = periods.setdefault(
                period.id,
                {
                    'id': period.id,
                    'name': period.name,
                    'span': f'{period.date_start.strftime("%d/%m")} a {period.date_end.strftime("%d/%m/%Y")}',
                    'start': fields.Date.to_string(period.date_start),
                    'rows': [],
                },
            )
            seat = session.seat_ids.filtered(lambda s: s.student_id == student)[:1]
            rooms = seat.room_id or session.room_ids
            row = {
                'id': session.id,
                'date': fields.Date.to_string(session.date),
                'day': day_label(session.date),
                'first_of_day': not group['rows'] or group['rows'][-1]['date'] != fields.Date.to_string(session.date),
                'start': hhmm(session.hour_from),
                'hours': f'{hhmm(session.hour_from)}–{hhmm(session.hour_to)}',
                'subject': session.subject_id.name,
                'rooms': ', '.join(rooms.room_id.mapped('display_name')),
                'supervisors': ', '.join(rooms.supervisor_ids.mapped('name')),
                'today': session.date == today,
                'done': session.state == 'done'
                or session.date < today
                or (session.date == today and session.hour_to <= minute),
            }
            group['rows'].append(row)
            data['rows'].append(row)
        data['periods'] = sorted(periods.values(), key=lambda p: p['start'])
        data['count'] = len(data['rows'])
        data['days'] = len({row['date'] for row in data['rows']})
        data['next'] = next((row for row in data['rows'] if not row['done']), None)
        return data

    @api.model
    def exams_report(self):
        """«Imprimir»: o calendário de provas da turma (o documento da secretaria, uma folha por época), visualizado na
        aplicação, como a escala de vigilância do professor."""
        student = self._student()
        enrollment = self._enrollment(student) if student else None
        periods = self.exams(student, enrollment)['periods'] if enrollment else []
        if not periods:
            raise UserError(self.env._('Ainda não há provas marcadas para a tua turma.'))
        Print = self.env['edu.exam.calendar.print'].sudo()
        documents = Print.browse()
        for period in periods:
            documents |= Print.create({'period_id': period['id'], 'class_id': enrollment.class_id.id})
        return self.env.ref('edu_documents.action_report_exam_calendar').preview_action(documents.with_env(self.env))

    # Faltas

    @api.private
    @api.model
    def absences(self, student, enrollment):
        """As faltas pela regra que conta, como no secPed: no técnico, o limite anual de faltas injustificadas, o triplo
        dos tempos semanais; no geral, 3, 4 ou 5 por trimestre, contadas no pior trimestre de cada disciplina."""
        data = {'subjects': [], 'total': 0, 'present': 0, 'regime': None, 'preschool': False}
        if not enrollment:
            return data
        rows = (
            self.env['edu.absence.summary']
            .sudo()
            .search(
                [('enrollment_id', '=', enrollment.id), ('subject_id', 'not in', enrollment._dropped_subjects().ids)]
            )
        )
        edu_class = enrollment.class_id
        regime = edu_class._edu_regime()
        data['regime'] = regime
        data['preschool'] = edu_class.level_id.code == 'INICIACAO'
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
                    'by_trimester': {},
                },
            )
            item['total'] += row.lessons
            item['present'] += row.present + row.late
            item['late'] += row.late
            item['absent'] += row.absent
            item['excused'] += row.excused
            trimester = row.trimester_id
            item['by_trimester'][trimester] = item['by_trimester'].get(trimester, 0) + row.absent
        for item in subjects.values():
            subject_class = item.pop('class')
            limit = absence_limit(subject_class._edu_weekly_hours(item.pop('subject')), regime)
            by_trimester = item.pop('by_trimester')
            window = ''
            if regime == TECHNICAL:
                counted = item['absent']
            else:
                worst = max(by_trimester, key=lambda t: (by_trimester[t], -t.number), default=None)
                counted = by_trimester[worst] if worst else 0
                window = worst.name.replace('Trimestre', 'trimestre') if worst and counted else ''
            status = absence_status(counted, limit, regime)
            item.update(
                {
                    'window': window,
                    'limit': limit,
                    'counted': counted,
                    'status': status,
                    'status_label': ABSENCE_STATUS.get(regime, ABSENCE_STATUS['general'])[status]
                    if limit
                    else 'Sem limite',
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

    @api.model
    def _absence_months(self, student, enrollment):
        """As faltas e os atrasos de cada mês do ano lectivo, até ao mês corrente (nas aulas dadas, como as contas da
        regra): injustificadas, justificadas e atrasos."""
        year = enrollment.academic_year_id
        if not year or not year.date_start:
            return []
        today = self._now(student).date()
        end = min(year.date_end or today, today)
        groups = (
            self.env['edu.lesson.attendance']
            .sudo()
            ._read_group(
                [
                    ('enrollment_id', '=', enrollment.id),
                    ('lesson_state', '!=', 'cancelled'),
                    ('state', 'in', ('absent', 'excused', 'late')),
                ],
                ['date:month', 'state'],
                ['__count'],
            )
        )
        counts = {(month.year, month.month, state): count for month, state, count in groups if month}
        months = []
        day = year.date_start.replace(day=1)
        while day <= end:
            months.append(
                {
                    'key': f'{day.year}-{day.month:02d}',
                    'label': MONTHS[day.month - 1][:3].capitalize(),
                    'name': f'{MONTHS[day.month - 1]} de {day.year}',
                    'absent': counts.get((day.year, day.month, 'absent'), 0),
                    'excused': counts.get((day.year, day.month, 'excused'), 0),
                    'late': counts.get((day.year, day.month, 'late'), 0),
                }
            )
            day = (day + timedelta(days=32)).replace(day=1)
        return months

    @api.model
    def _recent_absences(self, enrollment, limit=10):
        """As últimas faltas e atrasos, com o dia e a disciplina, como no secPed."""
        if not enrollment:
            return []
        attendances = (
            self.env['edu.lesson.attendance']
            .sudo()
            .search(
                [
                    ('enrollment_id', '=', enrollment.id),
                    ('state', 'in', tuple(ABSENCE_KINDS)),
                    ('lesson_state', '!=', 'cancelled'),
                ],
                order='date desc, id desc',
                limit=limit,
            )
        )
        return [
            {
                'id': attendance.id,
                'day': day_label(attendance.date),
                'subject': attendance.subject_id.name,
                'kind': ABSENCE_KINDS[attendance.state].capitalize(),
                'state': attendance.state,
            }
            for attendance in attendances
        ]

    # O calendário

    @api.model
    def calendar_data(self):
        """O «Calendário» do encarregado: o calendário académico da escola (o mesmo do professor) e as provas de cada
        educando, com o nome dele, para se poder ver um de cada vez."""
        Portal = self.env['edu.student.portal']
        data = self.env['edu.teacher.home'].calendar_data()
        data['children'] = []
        for student in self._children():
            name = first_name(student.name)
            data['children'].append({'id': student.id, 'name': name})
            enrollment = Portal._enrollment(student)
            for row in Portal.exams(student, enrollment)['rows']:
                data['events'].append(
                    {
                        'id': f'x{student.id}-{row["id"]}',
                        'name': f'{row["subject"]} ({name})',
                        'type': 'child_exam',
                        'type_label': f'Prova de {name}',
                        'start': row['date'],
                        'end': row['date'],
                        'description': f'{row["hours"]}' + (f', {row["rooms"]}' if row['rooms'] else ''),
                        'commemorative': False,
                        'child_id': student.id,
                    }
                )
        data['events'].sort(key=lambda e: (e['start'], e['end']))
        return data

    # Propinas

    @api.private
    @api.model
    def fees(self, student):
        """As facturas escolares do aluno, só para ler (quem paga é o encarregado), como no secPed: por pagar, pagas e
        isentas ou anuladas, com o vencimento (e há quantos dias está em atraso), o valor já com a bolsa, a multa, o
        que falta pagar e a situação. As multas por atraso (facturas à parte no Odoo) somam-se à factura que as
        originou; as facturas isentas pela bolsa integral ficam em rascunho e aparecem com as anuladas."""
        moves = (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('edu_student_id', '=', student.id),
                    ('move_type', '=', 'out_invoice'),
                    '|',
                    ('state', 'in', ('posted', 'cancel')),
                    ('edu_exempt', '=', True),
                ],
                order='invoice_date_due, id',
            )
        )
        # A multa soma-se à factura que a originou enquanto essa factura conta (emitida e não anulada por nota de
        # crédito); a de uma factura anulada fica na sua própria linha, para não desaparecer o que falta pagar.
        live = moves.filtered(lambda m: m.state == 'posted' and m.payment_state != 'reversed' and not m.edu_exempt)
        late_fees = moves.filtered(lambda m: m.edu_category == 'late_fee' and m.edu_late_fee_origin_id in live)
        today = self._now(student).date()
        currency = student.edu_currency_id

        def money(amount):
            return format_amount(self.env, amount, currency)

        rows = []
        for move in moves - late_fees:
            fines = late_fees.filtered(lambda m, o=move: m.edu_late_fee_origin_id == o and m.state == 'posted')
            fine_total = sum(fines.mapped('amount_total'))
            posted = move.state == 'posted'
            due = move.amount_residual + sum(fines.mapped('amount_residual')) if posted else 0.0
            total = move.amount_total + fine_total
            paid = total - due if posted else 0.0
            late_days = 0
            if move.state == 'cancel' or move.edu_exempt or move.payment_state == 'reversed':
                tab, status, css = 'other', 'Isenta' if move.edu_exempt else 'Anulada', 'muted'
                due = paid = 0.0
            elif due > 0.005:
                tab = 'due'
                # O atraso conta desde o vencimento do que ainda está por pagar: a factura, ou a multa quando a factura
                # já foi paga.
                open_dues = [
                    m.invoice_date_due for m in move | fines if m.invoice_date_due and m.amount_residual > 0.005
                ]
                oldest = min(open_dues, default=False)
                if oldest and oldest < today:
                    late_days = (today - oldest).days
                if late_days:
                    status, css = 'Em atraso', 'bad'
                elif move.payment_state == 'partial':
                    status, css = 'Paga em parte', 'warn'
                else:
                    status, css = 'Por pagar', ''
            else:
                tab, status, css = 'paid', 'Paga', 'good'
            # A data do pagamento: a da última reconciliação da conta a receber.
            receivable = move.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')
            paid_on = max(receivable.matched_credit_ids.mapped('max_date'), default=False) if tab == 'paid' else False
            line = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')[:1]
            name = line.name or move.name or ''
            rows.append(
                {
                    'id': move.id,
                    'tab': tab,
                    'name': name[:1].upper() + name[1:],
                    'number': move.name if move.state != 'draft' else '',
                    'due_date': long_date(move.invoice_date_due),
                    'paid_date': long_date(paid_on),
                    'late_days': late_days,
                    'amount': money(move.amount_total),
                    'discount': money(move.edu_discount) if move.edu_discount else '',
                    'fine': money(fine_total) if fine_total else '',
                    'due': money(due),
                    'total': money(total),
                    'paid': money(paid) if tab == 'due' and paid > 0.005 else '',
                    'due_value': due,
                    'paid_value': paid if tab == 'due' else (total if tab == 'paid' else 0.0),
                    'fine_value': sum(fines.mapped('amount_residual')),
                    'status': status,
                    'css': css,
                }
            )
        due_rows = [r for r in rows if r['tab'] == 'due']
        # Em atraso desde o dia seguinte ao vencimento, como na tabela; as restrições (o aviso das propinas e o
        # bloqueio) só depois dos dias de tolerância da escola.
        grace = student.company_id.edu_gate_grace_days or 0
        overdue_rows = [r for r in due_rows if r['late_days']]
        return {
            'rows': rows,
            'due': due_rows,
            'paid': [r for r in rows if r['tab'] == 'paid'],
            'other': [r for r in rows if r['tab'] == 'other'],
            'total_due': money(sum(r['due_value'] for r in due_rows)),
            'total_fines': money(sum(r['fine_value'] for r in due_rows)),
            'has_fines': any(r['fine_value'] for r in due_rows),
            # A coluna da multa só aparece se a escola cobra multas a este aluno.
            'charges_fines': any(r['fine'] for r in rows),
            'overdue': len(overdue_rows),
            'overdue_total': money(sum(r['due_value'] for r in overdue_rows)),
            'restricted': len([r for r in overdue_rows if r['late_days'] > grace]),
            'grace_days': grace,
            'total_paid': money(sum(r['paid_value'] for r in rows)),
            # O próximo vencimento: a primeira factura por pagar ainda dentro do prazo.
            'next_due': next(
                (
                    {'date': r['due_date'], 'amount': r['due'], 'name': r['name']}
                    for r in due_rows
                    if not r['late_days']
                ),
                None,
            ),
        }

    @api.model
    def _feed(self, students):
        """As novidades (Notificações) dos alunos dados, o próprio aluno ou os educandos do encarregado, nos últimos
        dias e da mais recente para a mais antiga: as notas lançadas (sem a nota, que pode mudar, como nos avisos do
        secPed), as faltas e os atrasos, as provas marcadas, as facturas emitidas, os pagamentos e os relatórios da
        Iniciação completos."""
        if not students:
            return []
        today = self._now(students[:1]).date()
        since = today - timedelta(days=FEED_DAYS)
        names = {s.id: first_name(s.name) for s in students}
        items = []

        def add(key, day, student, text, page):
            items.append(
                {
                    'key': key,
                    'date': fields.Date.to_string(day),
                    'student_id': student.id,
                    'first_name': names[student.id],
                    'text': text,
                    'page': page,
                }
            )

        grades = (
            self.env['edu.grade']
            .sudo()
            .search([('student_id', 'in', students.ids), ('graded', '=', True), ('write_date', '>=', since)])
        )
        seen = set()
        for grade in grades.sorted('write_date', reverse=True):
            day = grade.write_date.date()
            key = (grade.student_id.id, grade.subject_id.id, day)
            if key not in seen:
                seen.add(key)
                add(f'g{grade.id}', day, grade.student_id, f'Notas novas de {grade.subject_id.name}.', 'grades')
        attendances = (
            self.env['edu.lesson.attendance']
            .sudo()
            .search(
                [
                    ('student_id', 'in', students.ids),
                    ('state', 'in', tuple(ABSENCE_KINDS)),
                    ('lesson_state', '!=', 'cancelled'),
                    ('date', '>=', since),
                ]
            )
        )
        for attendance in attendances:
            kind = ABSENCE_KINDS[attendance.state]
            add(
                f'a{attendance.id}',
                attendance.date,
                attendance.student_id,
                f'{kind.capitalize()} a {attendance.subject_id.name}, {day_label(attendance.date).lower()}.',
                'absences',
            )
        Session = self.env['edu.exam.session'].sudo()
        for student in students:
            enrollment = self._enrollment(student)
            rows = [row for row in self.exams(student, enrollment)['rows'] if not row['done']]
            for session in Session.browse([row['id'] for row in rows]):
                if session.create_date.date() >= since:
                    add(
                        f'e{session.id}',
                        session.create_date.date(),
                        student,
                        f'Prova de {session.subject_id.name} marcada: {day_label(session.date).lower()}, às '
                        f'{hhmm(session.hour_from)}.',
                        'exams',
                    )
        moves = (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('edu_student_id', 'in', students.ids),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    '|',
                    ('invoice_date', '>=', since),
                    ('write_date', '>=', since),
                ]
            )
        )
        for move in moves:
            student = move.edu_student_id
            line = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')[:1]
            label = line.name or move.name or ''
            amount = format_amount(self.env, move.amount_total, move.currency_id)
            if move.invoice_date and move.invoice_date >= since:
                add(f'i{move.id}', move.invoice_date, student, f'Nova factura: {label}, {amount}.', 'fees')
            if move.payment_state in ('paid', 'in_payment'):
                receivable = move.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')
                paid_on = max(receivable.matched_credit_ids.mapped('max_date'), default=False)
                if paid_on and paid_on >= since:
                    add(f'p{move.id}', paid_on, student, f'Pagamento confirmado: {label}.', 'fees')
        rdecs = (
            self.env['edu.rdec']
            .sudo()
            .search([('student_id', 'in', students.ids), ('state', '=', 'done'), ('write_date', '>=', since)])
        )
        for rdec in rdecs:
            add(
                f'r{rdec.id}',
                rdec.write_date.date(),
                rdec.student_id,
                f'O RDEC do {rdec.trimester_id.name.replace("Trimestre", "trimestre")} está completo.',
                'rdec',
            )
        items.sort(key=lambda item: (item['date'], item['key']), reverse=True)
        return items[:FEED_LIMIT]

    # Histórico

    @api.model
    def _history(self, student):
        """O percurso do aluno, ano a ano, como no secPed: a turma, a média final, a assiduidade e a decisão do ano. Um
        ano só entra quando a decisão está tomada (o ano em curso entra no fim). Com propinas em atraso e a escola em
        modo «bloquear», fica escondido como as notas."""
        if student._edu_gate('grades')[0]:
            return {'blocked': True, 'rows': []}
        results = (
            self.env['edu.year.result']
            .sudo()
            .search([('student_id', '=', student.id), ('status', '!=', 'pending')])
            .filtered(lambda r: r.enrollment_id.state not in ('draft', 'dropped'))
            .sorted(lambda r: (r.academic_year_id.date_start, r.id))
        )
        labels = dict(results._fields['status']._description_selection(self.env))
        rows = []
        for result in results:
            edu_class = result.class_id
            policy = self.env['edu.evaluation.policy']._get(result.company_id, edu_class.level_id)
            rows.append(
                {
                    'id': result.id,
                    'year': result.academic_year_id.name,
                    'class': edu_class._editor_label(),
                    'course': edu_class.course_id.name or '',
                    'average': {
                        'text': grade_text(result.average),
                        'pos': grading.rounder(policy.rounding)(result.average) >= policy.pass_grade,
                    }
                    if result.average
                    else None,
                    # A frequência dos anos migrados do secPed não veio: fica por mostrar.
                    'attendance': round(100 * result.attendance_rate) if result.attendance_rate else None,
                    'status': result.status,
                    'status_label': labels[result.status],
                }
            )
        return {'blocked': False, 'rows': rows}

    @api.model
    def _chat_contacts(self):
        """Os contactos da «Nova conversa» das Mensagens, como no secPed: o director de turma e os professores da
        turma, e a secretaria e a direcção. Só quem tem utilizador."""
        student = self._student()
        enrollment = self._enrollment(student) if student else self.env['edu.enrollment']
        edu_class = enrollment.class_id
        groups = []
        seen = set()
        director = edu_class.director_id.user_id
        if director:
            seen.add(director.id)
            groups.append(
                {
                    'key': 'director',
                    'label': 'Director(a) de turma',
                    'contacts': [{'partner_id': director.partner_id.id, 'name': director.name, 'detail': ''}],
                }
            )
        teachers = {}
        for assignment in edu_class.assignment_ids:
            user = assignment.teacher_id.user_id
            if user:
                teachers.setdefault(user, []).append(assignment.subject_id.name)
        contacts = [
            {'partner_id': user.partner_id.id, 'name': user.name, 'detail': ', '.join(subjects)}
            for user, subjects in sorted(teachers.items(), key=lambda item: item[0].name or '')
        ]
        seen.update(user.id for user in teachers)
        if contacts:
            groups.append({'key': 'teachers', 'label': 'Professores da turma', 'contacts': contacts})
        return groups + self._office_contacts(student.company_id or self.env.company, seen)

    @api.model
    def _office_contacts(self, companies, seen):
        """A secretaria e a direcção da escola, para as Mensagens do aluno e do encarregado."""
        clerks = (
            self.env['res.users']
            .sudo()
            .search([('share', '=', False), ('company_ids', 'in', companies.ids)], order='name')
            .filtered(lambda u: u.has_group('edu_core.group_edu_user') and u.id not in seen)
        )
        groups = []
        for key, label, members in (
            ('office', 'Secretaria', clerks.filtered(lambda u: not u.has_group('edu_core.group_edu_manager'))),
            ('direction', 'Direcção', clerks.filtered(lambda u: u.has_group('edu_core.group_edu_manager'))),
        ):
            contacts = [{'partner_id': u.partner_id.id, 'name': u.name, 'detail': ''} for u in members]
            if contacts:
                groups.append({'key': key, 'label': label, 'contacts': contacts})
        return groups

    @api.model
    def _tuition_months(self, student, enrollment):
        """As propinas do ano lectivo mês a mês, de Setembro a Julho: paga, por pagar, em atraso (depois do vencimento,
        como na tabela das facturas), isenta, ou ainda sem factura."""
        year = enrollment.academic_year_id
        if not year or not year.date_start or not year.date_end:
            return []
        moves = (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('edu_student_id', '=', student.id),
                    ('move_type', '=', 'out_invoice'),
                    ('edu_category', '=', 'tuition'),
                    '|',
                    ('state', '=', 'posted'),
                    ('edu_exempt', '=', True),
                ]
            )
        )
        today = self._now(student).date()
        by_month = {}
        for move in moves:
            day = move.edu_due_period or move.invoice_date_due or move.invoice_date
            if day and year.date_start <= day <= year.date_end:
                by_month.setdefault((day.year, day.month), self.env['account.move'])
                by_month[(day.year, day.month)] |= move
        months = []
        day = year.date_start.replace(day=1)
        while day <= year.date_end:
            found = by_month.get((day.year, day.month), self.env['account.move'])
            live = found.filtered(lambda m: m.state == 'posted' and m.payment_state != 'reversed' and not m.edu_exempt)
            due = sum(live.mapped('amount_residual'))
            if not found:
                state = 'none'
            elif not live:
                state = 'exempt'
            elif due <= 0.005:
                state = 'paid'
            elif any(m.invoice_date_due and m.invoice_date_due < today and m.amount_residual > 0.005 for m in live):
                state = 'overdue'
            else:
                state = 'due'
            months.append(
                {
                    'key': f'{day.year}-{day.month:02d}',
                    'label': MONTHS[day.month - 1][:3].capitalize(),
                    'name': f'{MONTHS[day.month - 1]} de {day.year}',
                    'state': state,
                    'due': format_amount(self.env, due, student.edu_currency_id) if due > 0.005 else '',
                }
            )
            day = (day + timedelta(days=32)).replace(day=1)
        return months

    # Formação técnica

    @api.model
    def _is_technical(self, student):
        """Aluno do ensino técnico (numa matrícula de qualquer ano) ou com estágio ou PAP registados."""
        if not student:
            return False
        enrollments = self._enrollments(student)
        if enrollments.filtered(lambda e: e.class_id.level_id.subsystem == 'technical'):
            return True
        return bool(
            self.env['edu.internship'].sudo().search_count([('student_id', '=', student.id)], limit=1)
            or self.env['edu.final.project'].sudo().search_count([('student_id', '=', student.id)], limit=1)
        )

    @api.model
    def _graded(self, record, final_states, blocked=False):
        """A nota de um estágio ou de uma PAP, quando já foi lançada e o resultado está fechado (a de um estágio
        reaberto não conta). Com as notas escondidas pelas propinas em atraso, também esta fica escondida."""
        if blocked or record.state not in final_states or not record.grade:
            return None
        return {'text': grade_text(record.grade), 'pos': record.grade >= 10}

    @api.private
    @api.model
    def internships(self, student):
        """O estágio curricular, só para ler, como no secPed: a entidade, quem o acompanha na escola e na entidade, o
        período, as horas, a nota, a apreciação e os relatórios entregues (registados pelo tutor ou pela secretaria)."""
        records = (
            self.env['edu.internship']
            .sudo()
            .search([('student_id', '=', student.id), ('state', '!=', 'cancelled')])
            .sorted(lambda i: (i.academic_year_id.date_start or fields.Date.today(), i.id), reverse=True)
        )
        states = dict(records._fields['state']._description_selection(self.env))
        blocked = student._edu_gate('grades')[0]
        today = self._now(student).date()
        rows = []
        for internship in records:
            start, end = long_date(internship.date_start), long_date(internship.date_end)
            hours = '1 hora' if internship.hours == 1 else f'{internship.hours} horas'
            # A entidade está no título do cartão: a frase não a repete (o artigo dependia do nome).
            grade = self._graded(internship, ('passed', 'failed'), blocked)
            if internship.state == 'planned':
                if not start:
                    sentence = 'O estágio está registado; a data de início ainda não foi marcada.'
                elif internship.date_start > today:
                    sentence = f'O estágio começa a {start}.'
                else:
                    sentence = (
                        f'O estágio estava marcado para começar a {start}; a secretaria ainda não o deu como iniciado.'
                    )
            elif internship.state == 'ongoing':
                sentence = f'Estás a estagiar{f" desde {start}" if start else ""}.'
                if internship.hours:
                    sentence += f' Já cumpriste {hours}.'
            elif internship.state == 'passed':
                if grade:
                    sentence = f'Concluíste o estágio com {grade["text"]} valores.'
                elif blocked:
                    sentence = 'Concluíste o estágio. A nota está escondida enquanto houver propinas em atraso.'
                else:
                    sentence = 'Concluíste o estágio. A nota ainda não foi lançada.'
            else:
                sentence = 'Não tiveste aprovação no estágio. Fala com o teu tutor ou com a secretaria.'
            rows.append(
                {
                    'id': internship.id,
                    'entity': internship.entity or '',
                    'year': internship.academic_year_id.name or '',
                    'state': internship.state,
                    'state_label': states.get(internship.state, ''),
                    'sentence': sentence,
                    'tutor': internship.tutor_id.name or '',
                    'supervisor': internship.supervisor or '',
                    'supervisor_contact': internship.supervisor_contact or '',
                    'period': f'{start or "?"} a {end or "?"}' if start or end else '',
                    'hours': internship.hours,
                    'grade': grade,
                    'appraisal': internship.appraisal or '',
                    'note': internship.note or '',
                    'reports': [
                        {'id': report.id, 'name': report.name, 'date': long_date(report.date)}
                        for report in internship.report_ids.sorted('date', reverse=True)
                    ],
                }
            )
        return rows

    @api.private
    @api.model
    def projects(self, student):
        """A Prova de Aptidão Profissional, só para ler, como no secPed: o tema, o orientador, o júri, a entrega, a
        defesa e a nota (registados pela secretaria)."""
        records = (
            self.env['edu.final.project']
            .sudo()
            .search([('student_id', '=', student.id)])
            .sorted(lambda p: (p.academic_year_id.date_start or fields.Date.today(), p.id), reverse=True)
        )
        states = dict(records._fields['state']._description_selection(self.env))
        blocked = student._edu_gate('grades')[0]
        rows = []
        for project in records:
            defense = long_date(project.defense_date)
            advisor = project.advisor_id.name or ''
            grade = self._graded(project, ('passed', 'failed'), blocked)
            if project.state in ('proposed', 'ongoing'):
                if not advisor:
                    sentence = 'O tema está registado; ainda não tens orientador atribuído.'
                elif defense:
                    sentence = f'Estás a trabalhar com {advisor}. A defesa está marcada para {defense}.'
                else:
                    sentence = f'Estás a trabalhar com {advisor}. A data da defesa ainda não foi marcada.'
            elif project.state == 'submitted':
                sentence = (
                    f'Entregaste o trabalho. A defesa está marcada para {defense}.'
                    if defense
                    else 'Entregaste o trabalho. A data da defesa ainda não foi marcada.'
                )
            elif project.state == 'defended':
                sentence = 'Já defendeste o trabalho. A nota ainda não foi lançada.'
            elif project.state == 'passed':
                if grade:
                    sentence = f'Tiveste aprovação na PAP com {grade["text"]} valores.'
                elif blocked:
                    sentence = 'Tiveste aprovação na PAP. A nota está escondida enquanto houver propinas em atraso.'
                else:
                    sentence = 'Tiveste aprovação na PAP. A nota ainda não foi lançada.'
            else:
                sentence = 'Não tiveste aprovação na PAP. Fala com o teu orientador ou com a secretaria.'
            rows.append(
                {
                    'id': project.id,
                    'title': project.name,
                    'context': ', '.join(
                        p
                        for p in [
                            project.course_id.name,
                            project.academic_year_id.name and f'ano lectivo {project.academic_year_id.name}',
                        ]
                        if p
                    ),
                    'state': project.state,
                    'state_label': states.get(project.state, ''),
                    'sentence': sentence,
                    'advisor': advisor,
                    'jury': ', '.join(project.jury_ids.mapped('name')),
                    'submitted': long_date(project.submitted_date),
                    'defense': defense,
                    'grade': grade,
                    'description': project.description or '',
                }
            )
        return rows

    # Perfil

    @api.private
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
                'subjects': sorted(
                    (enrollment.subject_ids - enrollment._dropped_subjects()).mapped('name'), key=str.lower
                ),
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
