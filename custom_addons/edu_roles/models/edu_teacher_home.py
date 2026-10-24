import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.edu_timetable.models.hr_employee import _current_year, teacher_lessons
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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
            .search([('room_ids.supervisor_ids', 'in', employee.ids), ('date', '>=', today)], limit=5)
        )
        data['supervisions'] = [
            {
                'date': s.date.strftime('%d/%m/%Y'),
                'hours': f'{_hour(s.hour_from)}–{_hour(s.hour_to)}',
                'subject': s.subject_id.name,
                'rooms': ', '.join(r.room_id.name for r in s.room_ids.filtered(lambda r: employee in r.supervisor_ids)),
            }
            for s in sessions
        ]
        return data

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
        Lesson = self.env['edu.lesson'].sudo()
        for offset in range(15):
            day = today + timedelta(days=offset)
            slots = schedules.filtered(lambda s, d=day: s._occurs_on(d) and s._teacher_on(d) == employee).sorted(
                'hour_from'
            )
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
        """A aula do horário nesse dia (criada se ainda não existe), aberta para a chamada e o sumário."""
        employee = self._employee()
        schedule = self.env['edu.schedule'].sudo().browse(schedule_id).exists()
        day = fields.Date.to_date(date)
        if not schedule or not day or schedule._teacher_on(day) != employee:
            raise UserError(self.env._('Este tempo não é seu.'))
        if not schedule._occurs_on(day):
            raise UserError(self.env._('Este tempo não tem aula nesse dia.'))
        Lesson = self.env['edu.lesson'].sudo()
        lesson = Lesson.search([('schedule_id', '=', schedule.id), ('date', '=', day)], limit=1) or Lesson.create(
            {
                'class_id': schedule.class_id.id,
                'subject_id': schedule.subject_id.id,
                'schedule_id': schedule.id,
                'date': day,
            }
        )
        if lesson.state == 'scheduled' and not lesson.attendance_ids and day <= fields.Date.context_today(self):
            # Um toque abre a chamada (todos presentes), como no secPed; num trimestre fechado fica só a aula.
            try:
                with self.env.cr.savepoint():
                    lesson.with_user(self.env.user).action_open_roll_call()
            except UserError as error:
                _logger.info('Chamada não aberta para %s: %s', lesson.display_name, error)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.lesson',
            'res_id': lesson.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    # O meu horário

    @api.model
    def schedule_data(self):
        """«O meu horário» (acção cliente ``edu_roles.teacher_schedule``), como no secPed: as aulas da semana (as do ano
        inteiro e as do trimestre em curso, as mesmas do PDF), a carga face ao máximo de tempos e as reduções."""
        employee = self.env.user.employee_id
        year = _current_year(self.env, employee.company_id) if employee else False
        data = {'has_employee': bool(employee), 'year': year.name if year else '', 'lessons': [], 'load': None}
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
        if not period or not period.session_ids.room_ids.filtered(lambda r: employee in r.supervisor_ids):
            raise UserError(self.env._('Não está escalado para vigiar provas nesta época.'))
        document = (
            self.env['edu.exam.calendar.print'].sudo().create({'period_id': period.id, 'teacher_id': employee.id})
        )
        return self.env.ref('edu_documents.action_report_exam_calendar').preview_action(document.with_env(self.env))

    # A conta do professor (os módulos de RH, quando instalados)

    @api.model
    def action_my_profile(self):
        employee = self._employee()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('O meu perfil'),
            'res_model': 'hr.employee.public',
            'res_id': employee.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    @api.model
    def action_my_payslips(self):
        if 'l10n_ao_payroll.payslip' not in self.env:
            raise UserError(self.env._('O processamento salarial não está instalado.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Os meus recibos'),
            'res_model': 'l10n_ao_payroll.payslip',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('employee_id.user_id', '=', self.env.uid), ('state', '=', 'done')],
            'context': {'create': False, 'edit': False, 'delete': False},
        }

    @api.model
    def action_my_time_off(self):
        if 'hr.leave' not in self.env:
            raise UserError(self.env._('As férias e ausências não estão instaladas.'))
        group = self.env.ref('hr_holidays.group_hr_holidays_employee', raise_if_not_found=False)
        if group and group not in self.env.user.all_group_ids:
            raise UserError(self.env._('Ainda não tem acesso às férias e ausências: peça-o aos Recursos Humanos.'))
        return self.env['ir.actions.act_window']._for_xml_id('hr_holidays.hr_leave_action_new_request')
