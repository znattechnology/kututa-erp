from odoo import api, models
from odoo.exceptions import UserError

from .edu_schedule import WEEKDAYS
from .edu_time_slot import format_hour


class EduSchedule(models.Model):
    """Editor de horários (acção cliente ``edu_timetable.schedule_editor``), como o do secPed-Express: as disciplinas
    da turma à esquerda, com os tempos colocados face ao plano, e a grelha da semana à direita. Cada célula livre diz
    se o professor ou a sala já estão ocupados noutra turma, para os choques se verem antes de colocar a aula."""

    _inherit = 'edu.schedule'

    @api.model
    def editor_options(self):
        """Turmas e professores do ano lectivo em curso, para as listas do topo."""
        year = self.env['edu.academic.year'].search(
            [('is_current', '=', True), ('company_id', 'in', self.env.companies.ids)], limit=1
        )
        classes = self.env['edu.class'].search([('academic_year_id', '=', year.id)]) if year else []
        teachers = (
            self.env['hr.employee']
            .sudo()
            .search([('edu_is_teacher', '=', True), ('company_id', 'in', self.env.companies.ids)], order='name')
        )
        return {
            'year': year.name if year else False,
            'classes': [{'id': c.id, 'name': c._editor_label()} for c in classes],
            'teachers': [{'id': t.id, 'name': t.name} for t in teachers],
            'trimesters': [{'id': t.id, 'name': t.name} for t in year.trimester_ids] if year else [],
        }

    @api.model
    def editor_class_data(self, class_id, trimester_id=False):
        edu_class = self.env['edu.class'].browse(class_id).exists()
        if not edu_class:
            raise UserError(self.env._('A turma já não existe.'))
        lessons = self._editor_scope(self.search([('class_id', '=', edu_class.id)]), trimester_id)
        Assignment = self.env['edu.teaching.assignment']
        counts = {}
        for lesson in lessons:
            counts[lesson.subject_id.id] = counts.get(lesson.subject_id.id, 0) + 1
        subjects = []
        for line in edu_class.subject_line_ids.sorted(lambda line: line.subject_id.name or ''):
            subject = line.subject_id
            if not line.weekly_hours and not counts.get(subject.id):
                continue  # disciplina sem tempos nesta classe e sem aulas na grelha
            teacher = Assignment._teacher_for(edu_class, subject).sudo()
            subjects.append(
                {
                    'id': subject.id,
                    'name': subject.name,
                    'planned': line.weekly_hours,
                    'placed': counts.get(subject.id, 0),
                    'teacher_id': teacher.id,
                    'teacher': teacher.name or False,
                }
            )
        teachers = lessons.teacher_id | self.env['hr.employee'].browse(
            [s['teacher_id'] for s in subjects if s['teacher_id']]
        )
        return {
            'class': {
                'id': edu_class.id,
                'name': edu_class._editor_label(),
                'room_id': edu_class.room_id.id,
                'room': edu_class.room_id.name or False,
                'shift': edu_class.shift_id.name or False,
                'course': edu_class.course_id.name or False,
            },
            'days': self._editor_days(lessons),
            'periods': self._editor_periods(edu_class, lessons),
            'lessons': [lesson._editor_lesson() for lesson in lessons],
            'subjects': subjects,
            # Onde os professores da turma e a sala já estão ocupados noutras turmas: as células ficam bloqueadas.
            'teacher_busy': {
                str(teacher.id): self._editor_busy('teacher_id', teacher, edu_class, trimester_id)
                for teacher in teachers
            },
            'room_busy': self._editor_busy('room_id', edu_class.room_id, edu_class, trimester_id)
            if edu_class.room_id
            else [],
        }

    @api.model
    def editor_teacher_data(self, teacher_id, trimester_id=False):
        teacher = self.env['hr.employee'].sudo().browse(teacher_id).exists()
        if not teacher:
            raise UserError(self.env._('O professor já não existe.'))
        lessons = self._editor_scope(
            self.search([('teacher_id', '=', teacher.id), ('academic_year_id.is_current', '=', True)]), trimester_id
        )
        return {
            'teacher': {
                'id': teacher.id,
                'name': teacher.name,
                'load': teacher.edu_weekly_load,
                'load_max': teacher.edu_weekly_load_max,
            },
            'days': self._editor_days(lessons),
            'periods': self._editor_periods(self.env['edu.class'], lessons),
            'lessons': [lesson._editor_lesson() for lesson in lessons],
        }

    @api.model
    def editor_place(self, class_id, subject_id, weekday, hour_from, hour_to, *, trimester_id=False):
        """Coloca uma aula numa célula livre; o professor vem da colocação e a sala da turma."""
        lesson = self.create(
            {
                'class_id': class_id,
                'subject_id': subject_id,
                'weekday': str(weekday),
                'hour_from': hour_from,
                'hour_to': hour_to,
                'trimester_id': trimester_id or False,
            }
        )
        return {'id': lesson.id, 'warning': lesson._editor_load_warning()}

    def editor_move(self, weekday, hour_from, hour_to):
        """Arrasta a aula para outra célula; as verificações de choques são as mesmas da criação."""
        self.ensure_one()
        self.write({'weekday': str(weekday), 'hour_from': hour_from, 'hour_to': hour_to, 'time_slot_id': False})
        return {'id': self.id, 'warning': self._editor_load_warning()}

    # Auxiliares

    @api.model
    def _editor_scope(self, lessons, trimester_id):
        """O ano todo: só as aulas sem trimestre. Um trimestre: as do ano e as desse trimestre."""
        if trimester_id:
            return lessons.filtered(lambda s: s.trimester_id.id in (False, trimester_id))
        return lessons.filtered(lambda s: not s.trimester_id)

    @api.model
    def _editor_days(self, lessons):
        days = [code for code, _name in WEEKDAYS[:5]]
        if lessons.filtered(lambda s: s.weekday == '5'):
            days.append('5')
        names = dict(WEEKDAYS)
        return [{'code': int(code), 'name': names[code]} for code in days]

    @api.model
    def _editor_periods(self, edu_class, lessons):
        """As linhas da grelha: as horas das aulas que já existem e os tempos do turno da turma que não as cruzem."""
        periods = {(s.hour_from, s.hour_to) for s in lessons}
        taken = list(periods)
        if edu_class.shift_id:
            slots = self.env['edu.time.slot'].search(
                [('shift_id', '=', edu_class.shift_id.id), ('is_break', '=', False)]
            )
            for slot in slots:
                if not any(slot.hour_from < end and start < slot.hour_to for start, end in taken):
                    periods.add((slot.hour_from, slot.hour_to))
        return [
            {'from': start, 'to': end, 'label': f'{format_hour(start)} – {format_hour(end)}'}
            for start, end in sorted(periods)
        ]

    @api.model
    def _editor_busy(self, field_name, record, edu_class, trimester_id):
        """Tempos em que o professor (ou a sala) dá aula noutra turma do mesmo ano."""
        if not record:
            return []
        domain = [
            (field_name, '=', record.id),
            ('class_id', '!=', edu_class.id),
            ('academic_year_id', '=', edu_class.academic_year_id.id),
        ]
        if trimester_id:
            domain.append(('trimester_id', 'in', [False, trimester_id]))
        return [
            {
                'day': int(s.weekday),
                'from': s.hour_from,
                'to': s.hour_to,
                'label': f'{s.class_id._editor_label()} · {s.subject_id.name}',
            }
            for s in self.sudo().search(domain)
        ]

    def _editor_lesson(self):
        self.ensure_one()
        return {
            'id': self.id,
            'day': int(self.weekday),
            'from': self.hour_from,
            'to': self.hour_to,
            'subject_id': self.subject_id.id,
            'subject': self.subject_id.name,
            'teacher_id': self.teacher_id.id,
            'teacher': self.teacher_id.sudo().name or False,
            'room': self.room_id.name or False,
            'class_id': self.class_id.id,
            'class': self.class_id._editor_label(),
            'trimester': self.trimester_id.name or False,
        }

    def _editor_load_warning(self):
        """Aviso (não bloqueia) quando o professor passa o máximo de tempos semanais."""
        teacher = self.teacher_id.sudo()
        if teacher and teacher.edu_weekly_load > teacher.edu_weekly_load_max:
            return self.env._(
                '%(teacher)s fica com %(load)s tempos semanais (máximo %(max)s).',
                teacher=teacher.name,
                load=teacher.edu_weekly_load,
                max=teacher.edu_weekly_load_max,
            )
        return False
