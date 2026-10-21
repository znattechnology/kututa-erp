from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .edu_schedule import WEEKDAYS
from .edu_time_slot import format_hour

MAX_WEEKLY_LOAD = 24
COORDINATOR_REDUCTION = 4
DIRECTOR_REDUCTION = 2


class EduClass(models.Model):
    _inherit = 'edu.class'

    director_id = fields.Many2one(
        'hr.employee',
        string='Director(a) de turma',
        tracking=True,
        check_company=True,
        domain="[('edu_is_teacher', '=', True)]",
    )
    assignment_ids = fields.One2many('edu.teaching.assignment', 'class_id', string='Professores')
    schedule_ids = fields.One2many('edu.schedule', 'class_id', string='Horário')
    schedule_check = fields.Text(string='Horário face ao plano', compute='_compute_schedule_check')
    schedule_grid = fields.Html(string='Grelha', compute='_compute_schedule_grid', sanitize=False)

    @api.constrains('director_id', 'academic_year_id')
    def _check_director(self):
        """Um professor dirige no máximo uma turma por ano lectivo."""
        for edu_class in self.filtered('director_id'):
            other = self.search(
                [
                    ('id', '!=', edu_class.id),
                    ('director_id', '=', edu_class.director_id.id),
                    ('academic_year_id', '=', edu_class.academic_year_id.id),
                ],
                limit=1,
            )
            if other:
                raise ValidationError(
                    self.env._(
                        '%(teacher)s já é director(a) da turma %(other)s neste ano lectivo.',
                        teacher=edu_class.director_id.name,
                        other=other.display_name,
                    )
                )

    @api.depends('schedule_ids.subject_id', 'subject_line_ids.weekly_hours')
    def _compute_schedule_check(self):
        """Tempos semanais no horário (todo o ano) face à carga do plano curricular, por disciplina."""
        for edu_class in self:
            notes = []
            yearly = edu_class.schedule_ids.filtered(lambda s: not s.trimester_id)
            for line in edu_class.subject_line_ids:
                planned = line.weekly_hours
                scheduled = len(yearly.filtered(lambda s, line=line: s.subject_id == line.subject_id))
                if scheduled != planned:
                    notes.append(
                        self.env._(
                            '%(subject)s: %(scheduled)s de %(planned)s tempos',
                            subject=line.subject_id.name,
                            scheduled=scheduled,
                            planned=planned,
                        )
                    )
            edu_class.schedule_check = '\n'.join(notes) or False

    @api.depends('schedule_ids.weekday', 'schedule_ids.hour_from', 'schedule_ids.subject_id', 'schedule_ids.teacher_id')
    def _compute_schedule_grid(self):
        """Grelha semanal (tempos × dias) dos tempos do ano inteiro."""
        for edu_class in self:
            schedules = edu_class.schedule_ids.filtered(lambda s: not s.trimester_id)
            if not schedules:
                edu_class.schedule_grid = False
                continue
            days = [
                (code, name)
                for code, name in WEEKDAYS
                if code < '5' or schedules.filtered(lambda s, c=code: s.weekday == c)
            ]
            rows = sorted({(s.hour_from, s.hour_to) for s in schedules})
            cells = {(s.weekday, s.hour_from): s for s in schedules}
            html = Markup(
                '<table class="table table-sm table-bordered text-center o_edu_schedule_grid"><thead><tr><th/>'
            )
            for _code, name in days:
                html += Markup('<th>%s</th>') % name
            html += Markup('</tr></thead><tbody>')
            for hour_from, hour_to in rows:
                html += Markup('<tr><th class="text-nowrap">%s-%s</th>') % (
                    format_hour(hour_from),
                    format_hour(hour_to),
                )
                for code, _name in days:
                    schedule = cells.get((code, hour_from))
                    if schedule:
                        html += Markup('<td><strong>%s</strong><br/><small>%s</small></td>') % (
                            schedule.subject_id.code or schedule.subject_id.name,
                            escape(schedule.teacher_id.name or ''),
                        )
                    else:
                        html += Markup('<td/>')
                html += Markup('</tr>')
            edu_class.schedule_grid = html + Markup('</tbody></table>')

    def action_view_schedule(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Horário da %s', self.display_name),
            'res_model': 'edu.schedule',
            'view_mode': 'list,form',
            'domain': [('class_id', '=', self.id)],
            'context': {'default_class_id': self.id},
        }


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    edu_weekly_load = fields.Integer(
        string='Tempos semanais', compute='_compute_edu_weekly_load', groups='hr.group_hr_user,edu_core.group_edu_user'
    )
    edu_weekly_load_max = fields.Integer(
        string='Máximo de tempos semanais',
        compute='_compute_edu_weekly_load',
        groups='hr.group_hr_user,edu_core.group_edu_user',
        help='24 tempos; menos 4 a quem coordena um curso e menos 2 ao director de turma (regra do secPed-Express).',
    )

    def _compute_edu_weekly_load(self):
        Schedule = self.env['edu.schedule'].sudo()
        Class = self.env['edu.class'].sudo()
        Coordination = self.env['edu.coordination'].sudo()
        for employee in self:
            current = [
                ('academic_year_id.is_current', '=', True),
                ('academic_year_id.company_id', '=', employee.company_id.id),
            ]
            employee.edu_weekly_load = Schedule.search_count(
                [('teacher_id', '=', employee.id), ('trimester_id', '=', False), *current]
            )
            maximum = MAX_WEEKLY_LOAD
            if Coordination.search_count([('head_id', '=', employee.id), ('coordination_type', '=', 'course')]):
                maximum -= COORDINATOR_REDUCTION
            if Class.search_count([('director_id', '=', employee.id), *current]):
                maximum -= DIRECTOR_REDUCTION
            employee.edu_weekly_load_max = maximum
