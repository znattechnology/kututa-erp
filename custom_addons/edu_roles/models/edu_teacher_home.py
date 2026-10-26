from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.edu_evaluation.tools import grading
from odoo.addons.edu_timetable.models.hr_employee import _current_year, teacher_lessons
from odoo.exceptions import UserError
from odoo.tools import format_amount

MONTHS = [
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]  # fmt: skip
WEEKDAYS = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']


def _day(day):
    """«Quinta-feira, 22/10/2026»."""
    return f'{WEEKDAYS[day.weekday()].capitalize()}, {day.strftime("%d/%m/%Y")}'


def _hour(value):
    hours = int(value)
    return f'{hours:02d}:{round((value - hours) * 60):02d}'


class EduTeacherHome(models.AbstractModel):
    """O Painel do Professor (acção cliente ``edu_roles.teacher_home``), como o do secPed-Express: o dia (as aulas de
    hoje pelo horário, ou as do próximo dia de aulas, com a chamada a um toque), as turmas deste ano com a direcção
    assinalada, as próximas vigilâncias e os atalhos da conta (perfil, recibos, férias)."""

    _name = 'edu.teacher.home'
    _description = 'Painel do Professor'

    @api.model
    def _employee(self):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(self.env._('O seu utilizador não está ligado a uma ficha de professor.'))
        return employee

    @api.model
    def home_data(self):
        employee = self.env.user.employee_id
        today = fields.Date.context_today(self)
        data = {
            'name': self.env.user.name,
            'today': _day(today),
            'has_employee': bool(employee),
            'lessons': [],
            'lessons_day': '',
            'classes': [],
            'supervisions': [],
        }
        if not employee:
            return data
        data['classes'] = self.env['edu.grade.grid'].grid_classes()['classes']
        day, lessons = self._next_lessons(employee, today)
        data['lessons'] = lessons
        if day and day != today:
            data['lessons_day'] = _day(day)
        sessions = (
            self.env['edu.exam.session']
            .sudo()
            .search(
                [('room_ids.supervisor_ids', 'in', employee.ids), ('date', '>=', today), ('state', '!=', 'cancelled')],
                limit=5,
            )
        )
        data['supervisions'] = [
            {
                'date': s.date.strftime('%d/%m/%Y'),
                'days': (s.date - today).days,
                'hours': f'{_hour(s.hour_from)}–{_hour(s.hour_to)}',
                'subject': s.subject_id.name,
                'rooms': ', '.join(r.room_id.name for r in s.room_ids.filtered(lambda r: employee in r.supervisor_ids)),
            }
            for s in sessions
        ]
        data['dashboard'] = self._dashboard(employee, today)
        return data

    @api.model
    def _dashboard(self, employee, today):
        """Os números e os gráficos do painel: a carga semanal, as aulas por registar, as notas do trimestre em cada
        turma e disciplina (positivas, negativas e sem nota, com a média), a assiduidade nas suas aulas e os alunos em
        risco por faltas. Tudo do ano corrente, lido em sudo e limitado às colocações do professor."""
        year = _current_year(self.env, employee.company_id)
        trimester = year.trimester_ids.filtered('is_current')[:1] if year else self.env['edu.trimester']
        teacher = employee.sudo()
        result = {
            'trimester': trimester.name or '',
            # Os dias até ao fim do trimestre em curso, para o aviso das notas em falta.
            'trimester_days': (trimester.date_end - today).days if trimester else None,
            'load': {'count': teacher.edu_weekly_load, 'limit': teacher.edu_weekly_load_max},
            'pending_lessons': 0,
            'grades': [],
            'attendance': [],
            'graded': 0,
            'expected': 0,
            'rdec': [],
            'rdec_done': 0,
            'rdec_total': 0,
            'at_risk': 0,
            'failed': 0,
        }
        if not year:
            return result
        # As aulas já passadas (ou de hoje) ainda por registar: chamada e sumário.
        result['pending_lessons'] = (
            self.env['edu.lesson']
            .sudo()
            .search_count(
                [
                    ('teacher_id', '=', employee.id),
                    ('academic_year_id', '=', year.id),
                    ('state', '=', 'scheduled'),
                    ('date', '<=', today),
                ]
            )
        )
        assignments = (
            self.env['edu.teaching.assignment']
            .sudo()
            .search([('teacher_id', '=', employee.id), ('academic_year_id', '=', year.id)])
            .filtered(lambda a: not a.trimester_id or a.trimester_id == trimester)
            .sorted(lambda a: (a.class_id.class_number, a.class_id.name or '', a.subject_id.name or ''))
        )
        trimesters = year.trimester_ids.sorted('number')
        index = list(trimesters).index(trimester) if trimester else None
        Result = self.env['edu.subject.result'].sudo()
        Summary = self.env['edu.absence.summary'].sudo()
        for assignment in assignments:
            edu_class, subject = assignment.class_id, assignment.subject_id
            label = f'{edu_class._editor_label()}, {subject.name}'
            enrollments = edu_class.enrollment_ids.filtered(lambda e: e.state in ('active', 'irregular'))
            # Na iniciação não há notas: conta o RDEC da turma (abaixo).
            if index is not None and enrollments and edu_class.level_id.code != 'INICIACAO':
                policy = self.env['edu.evaluation.policy']._get(edu_class.company_id, edu_class.level_id)
                round_fn = grading.rounder(policy.rounding)
                results = Result.search([('enrollment_id', 'in', enrollments.ids), ('subject_id', '=', subject.id)])
                values = []
                for subject_result in results:
                    value = subject_result._trimester_classifications()[index]
                    if value is not None:
                        values.append(value)
                # No técnico o CT não se arredonda (só a CA e a CFD); no geral, pela regra da escola.
                technical = policy.regime == grading.TECHNICAL
                positives = sum(1 for v in values if (v if technical else round_fn(v)) >= policy.pass_grade)
                total = len(enrollments)
                average = sum(values) / len(values) if values else None
                result['grades'].append(
                    {
                        'id': assignment.id,
                        'class_id': edu_class.id,
                        'label': label,
                        'total': total,
                        'positives': positives,
                        'negatives': len(values) - positives,
                        'missing': max(0, total - len(values)),
                        'average': f'{average:.1f}'.replace('.', ',') if average is not None else '',
                        'average_pos': average is not None and round(average * 10) / 10 >= policy.pass_grade,
                    }
                )
                result['graded'] += len(values)
                result['expected'] += total
            rows = Summary.search([('class_id', '=', edu_class.id), ('subject_id', '=', subject.id)])
            lessons = sum(rows.mapped('lessons'))
            if lessons:
                present = sum(rows.mapped('present')) + sum(rows.mapped('late'))
                result['attendance'].append(
                    {'id': assignment.id, 'label': label, 'rate': round(100 * present / lessons), 'lessons': lessons}
                )
        # Iniciação: o RDEC do trimestre em cada turma do(a) educador(a) (completos, em curso, por avaliar).
        preschool = assignments.class_id | self.env['edu.class'].sudo().search([('director_id', '=', employee.id)])
        preschool = preschool.filtered(lambda c: c.level_id.code == 'INICIACAO' and c.academic_year_id == year)
        if trimester and preschool:
            Rdec = self.env['edu.rdec'].sudo()
            Rdec._prepare(preschool, trimester)
            for edu_class in preschool.sorted(lambda c: c.name or ''):
                states = Rdec.search([('class_id', '=', edu_class.id), ('trimester_id', '=', trimester.id)]).mapped(
                    'state'
                )
                row = {
                    'class_id': edu_class.id,
                    'label': edu_class._editor_label(),
                    'total': len(states),
                    'done': states.count('done'),
                    'progress': states.count('progress'),
                    'todo': states.count('todo'),
                }
                result['rdec'].append(row)
                result['rdec_done'] += row['done']
                result['rdec_total'] += row['total']
        # Os alunos a uma falta do limite ou que já o passaram, nas disciplinas do professor (o relatório de faltas).
        if trimester:
            mine = self.env['edu.attendance.page'].absence_report(trimester.id)['mine']
            result['failed'] = sum(1 for g in mine if g['worst'] == 'failed')
            result['at_risk'] = len(mine) - result['failed']
        return result

    @api.model
    def _no_lessons_on(self, edu_class, day):
        """Dia de feriado ou pausa no calendário escolar, para o nível da turma: não há aulas."""
        Calendar = self.env['edu.calendar.event'].sudo()
        return day in Calendar._days_without_lessons(edu_class.company_id, edu_class.level_id, day, day)

    @api.model
    def _next_lessons(self, employee, today):
        """As aulas de hoje pelo horário; sem nenhuma, as do próximo dia de aulas (até duas semanas)."""
        # Os tempos do professor e os que substitui; em cada dia conta quem dá a aula (o substituto, se houver).
        replaced = (
            self.env['edu.schedule.replacement']
            .sudo()
            .search([('replacement_teacher_id', '=', employee.id), ('date', '>=', today)])
        )
        schedules = (
            self.env['edu.schedule']
            .sudo()
            .search([('teacher_id', '=', employee.id), ('academic_year_id.is_current', '=', True)])
        ) | replaced.schedule_id
        if not schedules:
            return False, []
        # Os feriados e as pausas das duas semanas, lidos uma vez por escola e nível.
        Calendar = self.env['edu.calendar.event'].sudo()
        cache = {}

        def holidays(edu_class):
            key = (edu_class.company_id, edu_class.level_id)
            if key not in cache:
                cache[key] = Calendar._days_without_lessons(*key, today, today + timedelta(days=14))
            return cache[key]

        Lesson = self.env['edu.lesson'].sudo()
        for offset in range(15):
            day = today + timedelta(days=offset)
            # Sem os feriados e as pausas do calendário escolar (como a geração das aulas).
            slots = schedules.filtered(
                lambda s, d=day: s._occurs_on(d) and s._teacher_on(d) == employee and d not in holidays(s.class_id)
            ).sorted('hour_from')
            if not slots:
                continue
            lessons = Lesson.search([('schedule_id', 'in', slots.ids), ('date', '=', day)])
            by_schedule = {lesson.schedule_id.id: lesson for lesson in lessons}
            rows = []
            for slot in slots:
                lesson = by_schedule.get(slot.id)
                rows.append(
                    {
                        'schedule_id': slot.id,
                        'date': fields.Date.to_string(day),
                        'hours': f'{_hour(slot.hour_from)}–{_hour(slot.hour_to)}',
                        'class': slot.class_id._editor_label(),
                        'subject': slot.subject_id.name,
                        'room': slot.room_id.display_name or '',
                        'lesson_id': lesson.id if lesson else False,
                        'state': lesson.state if lesson else 'scheduled',
                        'today': day == today,
                    }
                )
            return day, rows
        return False, []

    @api.model
    def open_lesson(self, schedule_id, date):
        """A aula do horário nesse dia (criada se ainda não existe), aberta em «Presenças» para a chamada e o
        sumário."""
        employee = self._employee()
        schedule = self.env['edu.schedule'].sudo().browse(schedule_id).exists()
        day = fields.Date.to_date(date)
        if not schedule or not day or schedule._teacher_on(day) != employee:
            raise UserError(self.env._('Este tempo não é seu.'))
        if not schedule._occurs_on(day):
            raise UserError(self.env._('Este tempo não tem aula nesse dia.'))
        if day > fields.Date.context_today(self):
            raise UserError(self.env._('A aula ainda não aconteceu: a chamada faz-se no próprio dia.'))
        if self._no_lessons_on(schedule.class_id, day):
            raise UserError(self.env._('Nesse dia é feriado ou pausa no calendário escolar: não há aulas.'))
        Lesson = self.env['edu.lesson'].sudo()
        lesson = Lesson.search([('schedule_id', '=', schedule.id), ('date', '=', day)], limit=1) or Lesson.create(
            {
                'class_id': schedule.class_id.id,
                'subject_id': schedule.subject_id.id,
                'schedule_id': schedule.id,
                'date': day,
            }
        )
        # A chamada faz-se em «Presenças», como no secPed: só fica registada quando se guarda.
        return {
            'type': 'ir.actions.client',
            'tag': 'edu_roles.attendance',
            'name': self.env._('Presenças'),
            'context': {'attendance_lesson_id': lesson.id},
        }

    # O meu horário

    @api.model
    def schedule_data(self):
        """«O meu horário» (acção cliente ``edu_roles.teacher_schedule``), como no secPed: as aulas da semana (as do ano
        inteiro e as do trimestre em curso, as mesmas do PDF), a carga face ao máximo de tempos e as reduções."""
        employee = self.env.user.employee_id
        year = _current_year(self.env, employee.company_id) if employee else False
        data = {
            'has_employee': bool(employee),
            'year': year.name if year else '',
            'today': fields.Date.to_string(fields.Date.context_today(self)),
            'lessons': [],
            'load': None,
        }
        if not employee:
            return data
        lessons = teacher_lessons(self.env, employee, year).sorted(lambda s: (s.weekday, s.hour_from))
        data['lessons'] = [
            {
                'id': lesson.id,
                'weekday': int(lesson.weekday),  # 0 = segunda-feira
                'start': round(lesson.hour_from * 60),
                'end': round(lesson.hour_to * 60),
                'subject': lesson.subject_id.name,
                'class': lesson.class_id._editor_label(),
                'class_id': lesson.class_id.id,
                'subject_id': lesson.subject_id.id,
                'room': lesson.room_id.display_name or '',
                'trimester': lesson.trimester_id.name or '',
            }
            for lesson in lessons
        ]
        teacher = employee.sudo()
        data['load'] = {
            'count': teacher.edu_weekly_load,
            'limit': teacher.edu_weekly_load_max,
            'notes': teacher._edu_load_notes(),
        }
        return data

    @api.model
    def schedule_report(self, preview=True):
        """O horário do professor em folha A4 horizontal: na aplicação (Visualizar) ou em PDF (Exportar)."""
        employee = self._employee()
        public = self.env['hr.employee.public'].browse(employee.id)
        report = self.env.ref('edu_documents.action_report_teacher_schedule')
        return report.preview_action(public) if preview else report.report_action(public)

    # Mensagens: a «Nova conversa» do secPed

    @api.model
    def chat_contacts(self):
        """Os contactos da «Nova conversa» das Mensagens, por grupos, como no secPed: os directores das turmas onde
        dou aulas, os professores das minhas turmas, a secretaria e a direcção. Só quem tem utilizador (os alunos e
        os encarregados entram com o portal)."""
        me = self.env.user
        if me.share:
            # Os utilizadores do portal não vêem a lista das pessoas da escola.
            return []
        employee = me.employee_id
        company = employee.company_id or self.env.company
        year = _current_year(self.env, company)
        Users = self.env['res.users'].sudo()
        groups = []
        seen = set()

        def contact(user, detail):
            seen.add(user.id)
            return {'partner_id': user.partner_id.id, 'name': user.name, 'detail': detail}

        if employee and year:
            Assignment = self.env['edu.teaching.assignment'].sudo()
            mine = Assignment.search([('teacher_id', '=', employee.id), ('academic_year_id', '=', year.id)])
            directed = (
                self.env['edu.class']
                .sudo()
                .search([('director_id', '=', employee.id), ('academic_year_id', '=', year.id)])
            )
            classes = (mine.class_id | directed).sorted(lambda c: (c.class_number, c.name or ''))
            directors = [
                contact(c.director_id.user_id, self.env._('Director(a) de turma da %s', c._editor_label()))
                for c in mine.class_id.sorted(lambda c: (c.class_number, c.name or ''))
                if c.director_id.user_id and c.director_id != employee and c.director_id.user_id.id not in seen
            ]
            if directors:
                groups.append({'key': 'directors', 'label': self.env._('Director de turma'), 'contacts': directors})
            colleagues = {}
            for assignment in Assignment.search([('class_id', 'in', classes.ids), ('teacher_id', '!=', employee.id)]):
                user = assignment.teacher_id.user_id
                if not user or user.id in seen:
                    continue
                colleagues.setdefault(user, []).append(
                    f'{assignment.subject_id.name} na {assignment.class_id._editor_label()}'
                )
            teachers = [
                contact(user, ', '.join(details[:2]) + ('…' if len(details) > 2 else ''))
                for user, details in sorted(colleagues.items(), key=lambda item: item[0].name or '')
            ]
            if teachers:
                groups.append(
                    {'key': 'teachers', 'label': self.env._('Professores das suas turmas'), 'contacts': teachers}
                )
        clerks = Users.search(
            [('share', '=', False), ('company_ids', 'in', company.ids), ('id', '!=', me.id)], order='name'
        ).filtered(lambda u: u.has_group('edu_core.group_edu_user'))
        for key, label, members in (
            (
                'office',
                self.env._('Secretaria'),
                clerks.filtered(lambda u: not u.has_group('edu_core.group_edu_manager')),
            ),
            ('direction', self.env._('Direcção'), clerks.filtered(lambda u: u.has_group('edu_core.group_edu_manager'))),
        ):
            contacts = [contact(user, '') for user in members if user.id not in seen]
            if contacts:
                groups.append({'key': key, 'label': label, 'contacts': contacts})
        return groups

    # Calendário académico

    @api.model
    def calendar_data(self):
        """«Calendário académico» (acção cliente ``edu_roles.academic_calendar``), como no secPed: os eventos do ano
        lectivo da escola (feriados e pausas, provas, reuniões, actividades e as datas comemorativas do calendário
        nacional, em que há aulas) e o início e o fim de cada trimestre."""
        company = self.env.user.employee_id.company_id or self.env.company
        year = _current_year(self.env, company)
        data = {'year': year.name if year else '', 'year_id': year.id if year else False, 'events': []}
        if not year:
            return data
        events = self.env['edu.calendar.event'].sudo().search([('academic_year_id', '=', year.id)])
        for event in events.sorted(lambda e: (e.date_start, e.id)):
            data['events'].append(
                {
                    'id': f'e{event.id}',
                    'name': event.name,
                    'type': event.event_type,
                    'start': fields.Date.to_string(event.date_start),
                    'end': fields.Date.to_string(event.date_end or event.date_start),
                    'description': event.description or '',
                    # As datas comemorativas do calendário nacional: há aulas normalmente.
                    'commemorative': event.is_national and event.event_type == 'other',
                }
            )
        for trimester in year.trimester_ids.sorted('number'):
            for kind, day, label in (
                ('trimester_start', trimester.date_start, self.env._('Início do %s', trimester.name)),
                ('trimester_end', trimester.date_end, self.env._('Fim do %s', trimester.name)),
            ):
                data['events'].append(
                    {
                        'id': f'{kind}{trimester.id}',
                        'name': label,
                        'type': kind,
                        'start': fields.Date.to_string(day),
                        'end': fields.Date.to_string(day),
                        'description': '',
                        'commemorative': False,
                    }
                )
        data['events'].sort(key=lambda e: (e['start'], e['end']))
        return data

    # As minhas vigilâncias

    @api.model
    def supervisions_data(self):
        """«Vigilâncias» (acção cliente ``edu_roles.teacher_supervisions``), como as «Provas» do professor no secPed: as
        provas do ano lectivo em que está escalado, por época, com a hora, a disciplina, a turma e as salas que vigia
        (e quem vigia com ele)."""
        employee = self.env.user.employee_id
        data = {'has_employee': bool(employee), 'periods': []}
        if not employee:
            return data
        sessions = (
            self.env['edu.exam.session']
            .sudo()
            .search(
                [
                    ('room_ids.supervisor_ids', 'in', employee.ids),
                    ('state', '!=', 'cancelled'),
                    ('academic_year_id.is_current', '=', True),
                ]
            )
            .sorted(lambda s: (s.date, s.hour_from, s.id))
        )
        periods = {}
        for session in sessions:
            period = session.period_id
            if period.id not in periods:
                periods[period.id] = {
                    'id': period.id,
                    'name': period.name,
                    'span': f'{period.date_start.strftime("%d/%m")} a {period.date_end.strftime("%d/%m/%Y")}',
                    'start': fields.Date.to_string(period.date_start),
                    'rows': [],
                }
            rooms = session.room_ids.filtered(lambda r: employee in r.supervisor_ids)
            periods[period.id]['rows'].append(
                {
                    'id': session.id,
                    'date': fields.Date.to_string(session.date),
                    'day': _day(session.date),
                    'start': round(session.hour_from * 60),
                    'end': round(session.hour_to * 60),
                    'subject': session.subject_id.name,
                    'classes': ', '.join(c._editor_label() for c in session.class_ids),
                    'rooms': ', '.join(rooms.room_id.mapped('display_name')),
                    'partners': ', '.join((rooms.supervisor_ids - employee).mapped('name')),
                }
            )
        data['periods'] = sorted(periods.values(), key=lambda p: p['start'])
        return data

    @api.model
    def supervisions_report(self, period_id):
        """A escala de vigilância da época (a folha do secPed), visualizada na aplicação."""
        employee = self._employee()
        period = self.env['edu.exam.period'].sudo().browse(period_id).exists()
        sessions = period.session_ids.filtered(lambda session: session.state != 'cancelled')
        if not period or not sessions.room_ids.filtered(lambda r: employee in r.supervisor_ids):
            raise UserError(self.env._('Não está escalado para vigiar provas nesta época.'))
        document = (
            self.env['edu.exam.calendar.print'].sudo().create({'period_id': period.id, 'teacher_id': employee.id})
        )
        return self.env.ref('edu_documents.action_report_exam_calendar').preview_action(document.with_env(self.env))

    # O meu perfil e os meus recibos (como as páginas do secPed)

    @api.model
    def profile_data(self):
        """«Meu perfil» (acção cliente ``edu_roles.teacher_profile``), como no secPed: o trabalho deste ano
        (disciplinas, turmas, direcção de turma, carga, departamento e cargo) e os dados da ficha. Os dados
        corrigem-se na secretaria; aqui só se muda a palavra-passe."""
        employee = self.env.user.employee_id
        data = {'has_employee': bool(employee), 'name': self.env.user.name}
        if not employee:
            return data
        teacher = employee.sudo()
        year = _current_year(self.env, teacher.company_id)
        assignments = (
            self.env['edu.teaching.assignment']
            .sudo()
            .search([('teacher_id', '=', teacher.id), ('academic_year_id', '=', year.id)])
            if year
            else self.env['edu.teaching.assignment']
        )
        subjects = assignments.subject_id.sorted(lambda s: s.name or '')
        classes = assignments.class_id.sorted(lambda c: (c.class_number, c.name or ''))
        directed = (
            self.env['edu.class'].sudo().search([('director_id', '=', teacher.id), ('academic_year_id', '=', year.id)])
            if year
            else self.env['edu.class']
        )

        def field(name):
            return teacher[name] if name in teacher._fields else False

        since = field('l10n_ao_admission_date') or field('first_contract_date')
        data.update(
            {
                'year': year.name if year else '',
                'subjects': subjects.mapped('name'),
                'classes': [c._editor_label() for c in classes],
                'directs': [c._editor_label() for c in directed],
                'load': {
                    'count': teacher.edu_weekly_load,
                    'limit': teacher.edu_weekly_load_max,
                    'notes': teacher._edu_load_notes(),
                },
                'department': teacher.department_id.name or '',
                'job': teacher.job_title or teacher.job_id.name or '',
                'coordination': field('edu_coordination_id').name if field('edu_coordination_id') else '',
                'email': teacher.work_email or self.env.user.email or '',
                'phone': teacher.mobile_phone or teacher.work_phone or '',
                'id_number': field('identification_id') or '',
                'inss': field('l10n_ao_inss_number') or '',
                'since': f'{MONTHS[since.month - 1]} de {since.year}' if since else '',
            }
        )
        return data

    @api.model
    def change_password(self):
        """O assistente do Odoo para mudar a palavra-passe do próprio utilizador."""
        return self.env.user.preference_change_password()

    @api.model
    def payslips_data(self):
        """«Recibos e férias» (acção cliente ``edu_roles.teacher_payslips``), como no secPed: os recibos fechados e,
        para quem tem acesso às ausências, as férias e as faltas pedidas este ano."""
        employee = self.env.user.employee_id
        data = {
            'has_employee': bool(employee),
            'has_payroll': 'l10n_ao_payroll.payslip' in self.env,
            'payslips': [],
            'year_totals': None,
            'time_off': None,
        }
        if not employee:
            return data
        if data['has_payroll']:
            # A procura é a do próprio (só os seus recibos fechados); a folha do mês lê-se em sudo.
            payslips = (
                self.env['l10n_ao_payroll.payslip']
                .search([('employee_id', '=', employee.id), ('state', '=', 'done')])
                .sudo()
                .sorted(lambda slip: (slip.run_id.year, int(slip.run_id.month or 0), slip.id), reverse=True)
            )
            data['payslips'] = [
                {
                    'id': slip.id,
                    'period': slip.run_id.name,
                    'number': slip.number or '',
                    'final': slip.kind == 'final',
                    'gross': format_amount(self.env, slip.gross, slip.currency_id),
                    'deductions': format_amount(self.env, slip.deductions, slip.currency_id),
                    'net': format_amount(self.env, slip.net, slip.currency_id),
                    # Os números, para o gráfico do líquido e a parte dos descontos em cada recibo.
                    'year': slip.run_id.year,
                    'month': int(slip.run_id.month or 0),
                    'net_value': slip.net,
                    'gross_value': slip.gross,
                    'deductions_value': slip.deductions,
                }
                for slip in payslips
            ]
            # O ano do último recibo: o bruto, os descontos e o líquido somados.
            if payslips:
                last_year = payslips[0].run_id.year
                of_year = payslips.filtered(lambda slip: slip.run_id.year == last_year)
                currency = payslips[0].currency_id
                data['year_totals'] = {
                    'year': last_year,
                    'count': len(of_year),
                    'gross': format_amount(self.env, sum(of_year.mapped('gross')), currency),
                    'deductions': format_amount(self.env, sum(of_year.mapped('deductions')), currency),
                    'net': format_amount(self.env, sum(of_year.mapped('net')), currency),
                }
        group = self.env.ref('hr_holidays.group_hr_holidays_employee', raise_if_not_found=False)
        if 'hr.leave' in self.env and group and group in self.env.user.all_group_ids:
            today = fields.Date.context_today(self)
            leaves = (
                self.env['hr.leave']
                .sudo()
                .search(
                    [('employee_id', '=', employee.id), ('request_date_from', '>=', today.replace(month=1, day=1))],
                    order='request_date_from desc',
                )
            )
            states = dict(self.env['hr.leave']._fields['state']._description_selection(self.env))
            data['time_off'] = [
                {
                    'id': leave.id,
                    'type': leave.holiday_status_id.name,
                    'from': leave.request_date_from.strftime('%d/%m/%Y'),
                    'to': leave.request_date_to.strftime('%d/%m/%Y'),
                    'days': leave.number_of_days,
                    'state': leave.state,
                    'state_label': states.get(leave.state, leave.state),
                }
                for leave in leaves
            ]
        return data

    @api.model
    def payslip_report(self, payslip_id, preview=True):
        """O recibo de vencimento em folha A4: na aplicação (Ver) ou em PDF (Descarregar)."""
        payslip = self.env['l10n_ao_payroll.payslip'].browse(payslip_id).exists()
        if not payslip or payslip.employee_id.user_id != self.env.user or payslip.state != 'done':
            raise UserError(self.env._('Este recibo não é seu.'))
        report = self.env.ref('l10n_ao_payroll.action_report_payslip')
        return report.preview_action(payslip) if preview else report.report_action(payslip)

    @api.model
    def action_my_time_off(self):
        if 'hr.leave' not in self.env:
            raise UserError(self.env._('As férias e ausências não estão instaladas.'))
        group = self.env.ref('hr_holidays.group_hr_holidays_employee', raise_if_not_found=False)
        if group and group not in self.env.user.all_group_ids:
            raise UserError(self.env._('Ainda não tem acesso às férias e ausências: peça-o aos Recursos Humanos.'))
        return self.env['ir.actions.act_window']._for_xml_id('hr_holidays.hr_leave_action_new_request')
