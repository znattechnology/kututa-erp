from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from .edu_class import CELL_BORDER, GRID_STYLE, HEAD_STYLE, schedule_grid

MAX_WEEKLY_LOAD = 24
COORDINATOR_REDUCTION = 4
DIRECTOR_REDUCTION = 2

FIRST = 'border-left: 1px solid #c8c8c8; '


def _current_year(env, company):
    return env['edu.academic.year'].sudo().search([('is_current', '=', True), ('company_id', '=', company.id)], limit=1)


def teacher_lessons(env, employee, year=None):
    """Aulas do professor no ano: as do ano inteiro e as do trimestre em curso (o horário que está a dar)."""
    year = year or _current_year(env, employee.company_id)
    if not year:
        return env['edu.schedule']
    current = year.trimester_ids.filtered('is_current')[:1]
    return (
        env['edu.schedule']
        .sudo()
        .search(
            [
                ('teacher_id', '=', employee.id),
                ('academic_year_id', '=', year.id),
                ('trimester_id', 'in', [False, *current.ids]),
            ]
        )
    )


def _director_labels(employees):
    """«Nome · dá Matemática» para quem dá aulas na turma do contexto (escolha do director de turma)."""
    class_id = employees.env.context.get('edu_director_class_id')
    if not class_id:
        return
    teaching = employees.env['edu.teaching.assignment'].sudo().search([('class_id', '=', class_id)])
    for employee in employees:
        employee_id = employee.employee_id.id if employee._name == 'hr.employee.public' else employee.id
        subjects = teaching.filtered(lambda a, e=employee_id: a.teacher_id.id == e).subject_id
        if subjects:
            employee.display_name = employees.env._(
                '%(name)s · dá %(subjects)s', name=employee.name, subjects=', '.join(subjects.mapped('name'))
            )


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    edu_weekly_load = fields.Integer(
        string='Tempos semanais', compute='_compute_edu_weekly_load', groups='hr.group_hr_user,edu_core.group_edu_user'
    )
    edu_weekly_load_max = fields.Integer(
        string='Máximo de tempos semanais',
        compute='_compute_edu_weekly_load',
        groups='hr.group_hr_user,edu_core.group_edu_user',
        help='24 tempos; menos 4 a quem coordena um curso e menos 2 ao director de turma (regra do secPed-Express, '
        'não da lei).',
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
            # As aulas do ano inteiro e as do trimestre em curso (o horário que o professor está a dar).
            trimester = self.env['edu.trimester'].sudo().search([('is_current', '=', True), *current], limit=1)
            employee.edu_weekly_load = Schedule.search_count(
                [('teacher_id', '=', employee.id), ('trimester_id', 'in', [False, *trimester.ids]), *current]
            )
            maximum = MAX_WEEKLY_LOAD
            if Coordination.search_count([('head_id', '=', employee.id), ('coordination_type', '=', 'course')]):
                maximum -= COORDINATOR_REDUCTION
            if Class.search_count([('director_id', '=', employee.id), *current]):
                maximum -= DIRECTOR_REDUCTION
            employee.edu_weekly_load_max = maximum

    def _edu_load_notes(self):
        """Porque o máximo de tempos é menor do que 24: as reduções do coordenador e do director de turma."""
        self.ensure_one()
        notes = []
        year = _current_year(self.env, self.company_id)
        directed = (
            self.env['edu.class']
            .sudo()
            .search([('director_id', '=', self.id), ('academic_year_id', '=', year.id)], limit=1)
        )
        if directed:
            notes.append(self.env._('menos 2 por ser director(a) de turma da %s', directed._editor_label()))
        coordination = (
            self.env['edu.coordination']
            .sudo()
            .search([('head_id', '=', self.id), ('coordination_type', '=', 'course')], limit=1)
        )
        if coordination:
            notes.append(self.env._('menos 4 por coordenar %s', coordination.name))
        return notes

    @api.depends_context('edu_director_class_id')
    def _compute_display_name(self):
        """Ao escolher o director de uma turma, os professores dizem o que dão nessa turma («· dá Matemática»)."""
        result = super()._compute_display_name()
        _director_labels(self)
        return result

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """Na escolha do director de turma, primeiro quem dá aulas na turma, depois os outros professores."""
        class_id = self.env.context.get('edu_director_class_id')
        if not class_id:
            return super().name_search(name, domain, operator, limit)
        teachers = self.env['edu.teaching.assignment'].sudo().search([('class_id', '=', class_id)]).teacher_id
        first = super().name_search(name, Domain.AND([domain or [], [('id', 'in', teachers.ids)]]), operator, limit)
        rest = super().name_search(
            name, Domain.AND([domain or [], [('id', 'not in', teachers.ids)]]), operator, (limit or 100) - len(first)
        )
        return first + rest


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # A ficha e a lista de docentes da secretaria (que lê o perfil público): o que o professor dá, em que turmas,
    # com que carga e o horário da semana, no ano lectivo em curso.
    edu_subjects_label = fields.Char(string='Disciplinas', compute='_compute_edu_teaching')
    edu_subjects_full = fields.Char(string='Todas as disciplinas', compute='_compute_edu_teaching')
    edu_class_count = fields.Integer(string='Turmas', compute='_compute_edu_teaching')
    edu_load = fields.Integer(string='Tempos por semana', compute='_compute_edu_teaching')
    edu_load_max = fields.Integer(string='Máximo de tempos', compute='_compute_edu_teaching')
    edu_load_label = fields.Char(string='Tempos/semana', compute='_compute_edu_teaching')
    edu_load_notes = fields.Char(string='Reduções', compute='_compute_edu_teaching')
    edu_load_over = fields.Boolean(string='Acima do limite', compute='_compute_edu_teaching')
    edu_directed_class = fields.Char(string='Director(a) de turma', compute='_compute_edu_teaching')
    edu_teaching_html = fields.Html(string='Disciplinas e turmas', compute='_compute_edu_teaching', sanitize=False)
    edu_schedule_html = fields.Html(string='Horário', compute='_compute_edu_teaching', sanitize=False)

    @api.depends_context('edu_director_class_id')
    def _compute_display_name(self):
        result = super()._compute_display_name()
        _director_labels(self)
        return result

    def _compute_edu_teaching(self):
        Assignment = self.env['edu.teaching.assignment'].sudo()
        Class = self.env['edu.class'].sudo()
        for public in self:
            employee = public.employee_id.sudo()
            year = _current_year(self.env, employee.company_id)
            assignments = Assignment.search([('teacher_id', '=', employee.id), ('academic_year_id', '=', year.id)])
            subjects = assignments.subject_id.sorted('name')
            names = subjects.mapped('name')
            public.edu_subjects_full = ', '.join(names) or False
            public.edu_subjects_label = ', '.join(names[:2]) + (
                self.env._(' e mais %s', len(names) - 2) if len(names) > 2 else ''
            )
            public.edu_class_count = len(assignments.class_id)
            public.edu_load = employee.edu_weekly_load
            public.edu_load_max = employee.edu_weekly_load_max
            public.edu_load_label = (
                self.env._('%(load)s de %(max)s', load=employee.edu_weekly_load, max=employee.edu_weekly_load_max)
                if employee.edu_is_teacher
                else False
            )
            public.edu_load_over = employee.edu_weekly_load > employee.edu_weekly_load_max
            public.edu_load_notes = '; '.join(employee._edu_load_notes()) if employee.edu_is_teacher else False
            directed = Class.search([('director_id', '=', employee.id), ('academic_year_id', '=', year.id)], limit=1)
            public.edu_directed_class = directed._editor_label() if directed else False
            public.edu_teaching_html = public._edu_teaching_table(assignments)
            public.edu_schedule_html = schedule_grid(
                self.env,
                teacher_lessons(self.env, employee, year),
                lambda s: [s.class_id._editor_label(), s.room_id.name],
            )

    def _edu_teaching_table(self, assignments):
        """Disciplina → turmas, como no secPed, com o período quando não é o ano todo e os tempos do plano."""
        if not assignments:
            return False
        html = Markup('<table class="o_edu_teaching" style="%s"><thead><tr>') % Markup(GRID_STYLE)
        for index, label in enumerate((self.env._('Disciplina'), self.env._('Turmas'), self.env._('Tempos'))):
            html += Markup('<th style="%s%s text-align: %s;%s">%s</th>') % (
                Markup(FIRST.replace('#c8c8c8', '#969696') if index == 0 else ''),
                Markup(HEAD_STYLE),
                'left' if index < 2 else 'center',
                Markup(' width: 6rem;' if index == 2 else ''),
                label,
            )
        html += Markup('</tr></thead><tbody>')
        for subject in assignments.subject_id.sorted('name'):
            rows = assignments.filtered(lambda a, s=subject: a.subject_id == s).sorted(
                lambda a: a.class_id._editor_label()
            )
            classes = ', '.join(
                a.class_id._editor_label() + (f' (só o {a.trimester_id.name})' if a.trimester_id else '') for a in rows
            )
            html += Markup(
                '<tr><td style="%s%s padding: 5px 8px;">%s</td><td style="%s padding: 5px 8px;">%s</td>'
                '<td style="%s padding: 5px 8px; text-align: center;">%s</td></tr>'
            ) % (
                Markup(FIRST),
                Markup(CELL_BORDER),
                subject.name,
                Markup(CELL_BORDER),
                classes,
                Markup(CELL_BORDER),
                sum(rows.mapped('weekly_hours')),
            )
        return html + Markup('</tbody></table>')


class EduTeachingAssignment(models.Model):
    _inherit = 'edu.teaching.assignment'

    teacher_load_label = fields.Char(string='Tempos do professor', compute='_compute_teacher_load')
    teacher_load_over = fields.Boolean(compute='_compute_teacher_load')

    @api.depends('teacher_id')
    def _compute_teacher_load(self):
        for assignment in self:
            teacher = assignment.teacher_id.sudo()
            assignment.teacher_load_label = (
                self.env._('%(load)s de %(max)s', load=teacher.edu_weekly_load, max=teacher.edu_weekly_load_max)
                if teacher
                else False
            )
            assignment.teacher_load_over = bool(teacher) and teacher.edu_weekly_load > teacher.edu_weekly_load_max

    @api.onchange('teacher_id', 'class_id', 'subject_id', 'trimester_id')
    def _onchange_teacher_warning(self):
        """Avisa antes de gravar, como o secPed: quem já dá a disciplina, falta de habilitação e carga acima do
        limite. Os dois últimos não bloqueiam (a escola decide); o primeiro é recusado ao gravar."""
        if not (self.teacher_id and self.class_id and self.subject_id):
            return None
        messages = []
        domain = [('class_id', '=', self.class_id.id), ('subject_id', '=', self.subject_id.id)]
        if self._origin.id:
            domain.append(('id', '!=', self._origin.id))
        if self.trimester_id:
            domain.append(('trimester_id', 'in', [False, self.trimester_id.id]))
        other = self.search(domain, limit=1)
        if other:
            messages.append(
                self.env._(
                    '%(subject)s já é dada por %(teacher)s nesta turma. Para a passar a outro professor, mude o '
                    'professor nessa linha.',
                    subject=self.subject_id.name,
                    teacher=other.teacher_id.name,
                )
            )
        teacher = self.teacher_id.sudo()
        if teacher.edu_subject_ids and self.subject_id not in teacher.edu_subject_ids:
            messages.append(self.env._('%s não tem habilitação registada para esta disciplina.', teacher.name))
        hours = sum(
            self.class_id.subject_line_ids.filtered(lambda line: line.subject_id == self.subject_id).mapped(
                'weekly_hours'
            )
        )
        if teacher.edu_weekly_load + hours > teacher.edu_weekly_load_max:
            messages.append(
                self.env._(
                    '%(teacher)s fica com cerca de %(load)s tempos semanais (máximo %(max)s).',
                    teacher=teacher.name,
                    load=teacher.edu_weekly_load + hours,
                    max=teacher.edu_weekly_load_max,
                )
            )
        if messages:
            return {'warning': {'title': self.env._('Atenção'), 'message': '\n\n'.join(messages)}}
        return None

    @api.constrains('teacher_id')
    def _check_teacher_active(self):
        for assignment in self:
            teacher = assignment.teacher_id.sudo()
            if not teacher.active or not teacher.edu_is_teacher:
                raise ValidationError(self.env._('%s não é um professor activo da escola.', assignment.teacher_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        assignments = super().create(vals_list)
        assignments._sync_schedule()
        return assignments

    def write(self, vals):
        result = super().write(vals)
        if {'teacher_id', 'trimester_id', 'class_id', 'subject_id'} & set(vals):
            self._sync_schedule()
        return result

    def _sync_schedule(self):
        """Trocar o professor passa para as aulas do horário dessa turma e disciplina (no período da colocação); os
        choques com outras aulas do novo professor são recusados pelo horário."""
        if self.env.context.get('edu_schedule_import'):
            return
        Schedule = self.env['edu.schedule']
        for assignment in self:
            domain = [('class_id', '=', assignment.class_id.id), ('subject_id', '=', assignment.subject_id.id)]
            domain.append(('trimester_id', '=', assignment.trimester_id.id or False))
            lessons = Schedule.search(domain).filtered(lambda s, t=assignment.teacher_id: s.teacher_id != t)
            if lessons:
                lessons.write({'teacher_id': assignment.teacher_id.id})
