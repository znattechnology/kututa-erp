from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .edu_schedule import WEEKDAYS
from .edu_time_slot import format_hour

# Horário semanal no estilo da pauta: grelha a preto e cinzento, sem as cores da escola.
GRID_STYLE = (
    'width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; font-size: 12px; color: #000;'
)
CELL_BORDER = 'border-right: 1px solid #c8c8c8; border-bottom: 1px solid #c8c8c8;'
HEAD_STYLE = (
    'border-right: 1px solid #969696; border-bottom: 1px solid #969696; border-top: 1px solid #969696; '
    'font-weight: bold; text-align: center; padding: 6px 4px;'
)
HOUR_STYLE = 'font-weight: bold; text-align: center; white-space: nowrap; padding: 4px;'
LESSON_STYLE = 'text-align: center; vertical-align: middle; padding: 4px 6px; line-height: 1.3;'


def schedule_grid(env, schedules, detail):
    """Grelha semanal no estilo da pauta (tempos × dias). ``detail(aula)`` dá as linhas por baixo da disciplina:
    o professor e a sala no horário da turma, a turma e a sala no horário do professor."""
    if not schedules:
        return False
    days = [
        (code, name) for code, name in WEEKDAYS if code < '5' or schedules.filtered(lambda s, c=code: s.weekday == c)
    ]
    rows = sorted({(s.hour_from, s.hour_to) for s in schedules})
    cells = {(s.weekday, s.hour_from, s.hour_to): s for s in schedules}
    first = Markup('border-left: 1px solid #c8c8c8; ')
    html = Markup('<table class="o_edu_schedule_grid" style="%s"><colgroup><col style="width: 9rem;"/>') % Markup(
        GRID_STYLE
    )
    html += Markup('<col/>') * len(days)
    html += Markup('</colgroup><thead><tr><th style="%s%s">%s</th>') % (
        Markup('border-left: 1px solid #969696; '),
        Markup(HEAD_STYLE),
        env._('Hora'),
    )
    for _code, name in days:
        html += Markup('<th style="%s">%s</th>') % (Markup(HEAD_STYLE), name)
    html += Markup('</tr></thead><tbody>')
    for hour_from, hour_to in rows:
        html += Markup('<tr><td style="%s%s%s">%s – %s</td>') % (
            first,
            Markup(CELL_BORDER),
            Markup(HOUR_STYLE),
            format_hour(hour_from),
            format_hour(hour_to),
        )
        for code, _name in days:
            schedule = cells.get((code, hour_from, hour_to))
            if schedule:
                html += Markup('<td style="%s%s"><strong>%s</strong><br/>%s</td>') % (
                    Markup(CELL_BORDER),
                    Markup(LESSON_STYLE),
                    schedule.subject_id.name,
                    ', '.join(p for p in detail(schedule) if p),
                )
            else:
                html += Markup('<td style="%s"></td>') % Markup(CELL_BORDER)
        html += Markup('</tr>')
    return html + Markup('</tbody></table>')


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

    @api.depends('schedule_ids.subject_id', 'schedule_ids.trimester_id', 'subject_line_ids.weekly_hours')
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

    @api.depends(
        'schedule_ids.weekday',
        'schedule_ids.hour_from',
        'schedule_ids.hour_to',
        'schedule_ids.subject_id',
        'schedule_ids.teacher_id',
        'schedule_ids.room_id',
    )
    def _compute_schedule_grid(self):
        """A semana toda de uma vez, como o horário impresso: os tempos na vertical, os dias na horizontal e, em cada
        aula, a disciplina, o professor e a sala."""
        for edu_class in self:
            schedules = edu_class.schedule_ids.filtered(lambda s: not s.trimester_id)
            if not schedules:
                edu_class.schedule_grid = False
                continue
            edu_class.schedule_grid = schedule_grid(
                self.env,
                schedules,
                lambda s: [s.teacher_id.name or self.env._('Sem professor'), s.room_id.name],
            )

    def _editor_label(self):
        """«10ª A · EST»: a turma sem o ano lectivo, que o editor de horários já mostra no topo."""
        self.ensure_one()
        return ' · '.join(p for p in [f'{self.class_number}ª {self.name}', self.course_id.code] if p)

    def action_edit_schedule(self):
        """Abre o editor de horários nesta turma."""
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('edu_timetable.action_edu_schedule_editor')
        action['context'] = {'default_class_id': self.id}
        return action

    teacher_summary = fields.Char(string='Professores', compute='_compute_teacher_summary')
    missing_teacher_subjects = fields.Char(
        string='Sem professor', compute='_compute_teacher_summary', search='_search_missing_teacher_subjects'
    )
    director_teaches = fields.Boolean(string='Lecciona na turma', compute='_compute_teacher_summary')

    @api.depends('assignment_ids.teacher_id', 'subject_line_ids', 'director_id')
    def _compute_teacher_summary(self):
        for edu_class in self:
            planned = edu_class.subject_line_ids.filtered('weekly_hours').subject_id
            covered = edu_class.assignment_ids.filtered(lambda a: not a.trimester_id).subject_id
            missing = (planned - covered).sorted('name')
            edu_class.teacher_summary = (
                self.env._('%(covered)s de %(total)s com professor', covered=len(planned & covered), total=len(planned))
                if planned
                else False
            )
            edu_class.missing_teacher_subjects = ', '.join(missing.mapped('name')) or False
            edu_class.director_teaches = edu_class.director_id in edu_class.assignment_ids.teacher_id

    def _search_missing_teacher_subjects(self, operator, value):
        if operator not in ('!=', '=') or value is not False:
            return NotImplemented
        classes = self.search([('academic_year_id.is_current', '=', True)]).filtered('missing_teacher_subjects')
        return [('id', 'in' if operator == '!=' else 'not in', classes.ids)]

    @api.onchange('director_id')
    def _onchange_director_warning(self):
        if self.director_id and self.director_id not in self.assignment_ids.teacher_id:
            return {
                'warning': {
                    'title': self.env._('Atenção'),
                    'message': self.env._(
                        '%s não dá aulas nesta turma. O director de turma costuma ser um dos professores da turma.',
                        self.director_id.name,
                    ),
                }
            }
        return None
