from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

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
        schedules = (
            self.env['edu.schedule']
            .sudo()
            .search([('teacher_id', '=', employee.id), ('academic_year_id.is_current', '=', True)])
        )
        if not schedules:
            return False, []
        Lesson = self.env['edu.lesson'].sudo()
        for offset in range(15):
            day = today + timedelta(days=offset)
            slots = schedules.filtered(lambda s, d=day: s._occurs_on(d)).sorted('hour_from')
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
                        'room': slot.room_id.name or '',
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
        if not schedule or schedule.teacher_id != employee:
            raise UserError(self.env._('Este tempo não é seu.'))
        day = fields.Date.to_date(date)
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
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.lesson',
            'res_id': lesson.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

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
        return self.env['ir.actions.act_window']._for_xml_id('hr_holidays.hr_leave_action_new_request')
