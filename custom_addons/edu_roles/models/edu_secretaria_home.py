from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.edu_timetable.models.hr_employee import _current_year
from odoo.exceptions import AccessError
from odoo.tools.misc import format_amount

ENROLLED = ('active', 'irregular')
MONTHS = ['jan.', 'fev.', 'mar.', 'abr.', 'mai.', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.']


def _plural(n, one, many):
    return one if n == 1 else many


class EduSecretariaHome(models.AbstractModel):
    """O Painel da secretaria (acção cliente ``edu_roles.secretaria_home``), como o dos Serviços Académicos do
    secPed: o que está à espera de tratamento (cada linha com a contagem e a lista onde se resolve), os números do
    ano, os alunos por classe, as turmas (ocupação, director, horário e notas lançadas, as que têm alguma coisa por
    resolver primeiro) e os eventos das próximas duas semanas. Da escola aberta e do ano lectivo corrente."""

    _name = 'edu.secretaria.home'
    _description = 'Painel da secretaria'

    @api.model
    def _check_access(self):
        if not self.env.user.has_group('edu_core.group_edu_user'):
            raise AccessError(self.env._('O painel da secretaria é dos Serviços Académicos.'))

    @api.model
    def _year(self):
        return _current_year(self.env, self.env.company)

    @api.model
    def _classes(self, year):
        return (
            self.env['edu.class']
            .sudo()
            .search([('academic_year_id', '=', year.id), ('company_id', '=', self.env.company.id)])
            .sorted(lambda c: (c.class_number, c.name or '', c.course_id.code or ''))
        )

    @api.model
    def home_data(self):
        self._check_access()
        company = self.env.company
        today = fields.Date.context_today(self)
        year = self._year()
        data = {'company': company.name, 'year': year.name or '', 'has_year': bool(year)}
        if not year:
            return data
        trimester = year.trimester_ids.filtered('is_current')[:1]
        classes = self._classes(year)
        Enrollment = self.env['edu.enrollment'].sudo()
        enrollments = Enrollment.search([('class_id', 'in', classes.ids), ('state', 'in', ENROLLED)])
        by_class = {}
        for enrollment in enrollments:
            by_class.setdefault(enrollment.class_id.id, Enrollment.browse())
            by_class[enrollment.class_id.id] |= enrollment
        # As notas do trimestre: as classificações lançadas face às esperadas (cada aluno em cada disciplina).
        launched = {}
        if trimester:
            groups = (
                self.env['edu.term.result']
                .sudo()
                ._read_group(
                    [
                        ('enrollment_id', 'in', enrollments.ids),
                        ('trimester_id', '=', trimester.id),
                        ('has_mt', '=', True),
                    ],
                    ['class_id'],
                    ['__count'],
                )
            )
            launched = {edu_class.id: count for edu_class, count in groups}
        rows = []
        for edu_class in classes:
            students = by_class.get(edu_class.id, Enrollment.browse())
            schedules = edu_class._edu_current_schedules()
            # O ano de estágio não tem grelha semanal (como no secPed: curso com estágio obrigatório e última classe do
            # plano curricular), nem um ano sem tempos no plano: não contam como turmas sem horário.
            internship_year = (
                edu_class.course_id.requires_internship and edu_class.class_number == edu_class.curriculum_id.class_to
            )
            no_lessons_planned = internship_year or not edu_class.curriculum_year_id.weekly_hours
            expected = sum(len(e.subject_ids) for e in students)
            rows.append(
                {
                    'id': edu_class.id,
                    'name': edu_class._editor_label(),
                    'course': edu_class.course_id.name or '',
                    'students': len(students),
                    'capacity': edu_class.capacity,
                    'over': bool(edu_class.capacity) and len(students) > edu_class.capacity,
                    'director': edu_class.director_id.name or '',
                    'lessons': len(schedules),
                    'no_teacher': len(schedules.filtered(lambda s: not s.teacher_id)),
                    'no_schedule': not schedules and not no_lessons_planned,
                    'expected': expected,
                    'launched': min(launched.get(edu_class.id, 0), expected),
                }
            )
        for row in rows:
            row['occupancy'] = round(100 * row['students'] / row['capacity']) if row['capacity'] else None
            row['occupancy_width'] = min(100, row['occupancy'] or 0)
            row['grades'] = round(100 * row['launched'] / row['expected']) if row['expected'] else None
            # As que têm alguma coisa por resolver primeiro (sem horário pesa mais do que sem director), como no secPed.
            row['weight'] = (
                (4 if row['no_schedule'] else 0)
                + (3 if row['over'] else 0)
                + (2 if row['no_teacher'] else 0)
                + (0 if row['director'] else 1)
            )
        rows.sort(key=lambda r: -r['weight'])
        data['classes'] = rows
        data['trimester'] = trimester.name or ''
        # Os números do ano.
        expected = sum(r['expected'] for r in rows)
        data['kpis'] = {
            'students': len(enrollments),
            'classes': len(classes),
            'capacity': sum(r['capacity'] for r in rows),
            'grades': round(100 * sum(r['launched'] for r in rows) / expected) if expected else None,
            'launched': sum(r['launched'] for r in rows),
            'expected': expected,
            'irregular': len(enrollments.filtered(lambda e: e.state == 'irregular')),
        }
        # Os alunos por classe (a classe nacional, de todos os cursos).
        students = {row['id']: row['students'] for row in rows}
        per_number = {}
        for edu_class in classes:
            per_number[edu_class.class_number] = per_number.get(edu_class.class_number, 0) + students[edu_class.id]
        data['per_class'] = [
            {'label': f'{number}ª classe' if number else 'Iniciação', 'count': count}
            for number, count in sorted(per_number.items())
        ]
        # Os alunos por curso (os mais numerosos primeiro).
        per_course = {}
        for row in rows:
            if row['course']:
                per_course[row['course']] = per_course.get(row['course'], 0) + row['students']
        data['per_course'] = [
            {'label': name, 'count': count} for name, count in sorted(per_course.items(), key=lambda item: -item[1])
        ]
        data['today'] = self._today(classes, today)
        data['fees'] = self._overdue_fees(today)
        data['pending'] = self._pending(year, rows, trimester)
        # Os eventos das próximas duas semanas no calendário escolar.
        events = (
            self.env['edu.calendar.event']
            .sudo()
            .search(
                [
                    ('company_id', '=', company.id),
                    ('date_start', '<=', today + timedelta(days=14)),
                    '|',
                    ('date_end', '>=', today),
                    '&',
                    ('date_end', '=', False),
                    ('date_start', '>=', today),
                ],
                order='date_start',
                limit=6,
            )
        )
        types = dict(self.env['edu.calendar.event']._fields['event_type']._description_selection(self.env))
        data['events'] = [
            {
                'id': event.id,
                'name': event.name,
                'start': fields.Date.to_string(event.date_start),
                'end': fields.Date.to_string(event.date_end or event.date_start),
                'day': str(event.date_start.day),
                'month': MONTHS[event.date_start.month - 1],
                'type': types.get(event.event_type, ''),
                'until': event.date_end and event.date_end != event.date_start and event.date_end.strftime('%d/%m'),
            }
            for event in events
        ]
        return data

    @api.model
    def _today(self, classes, today):
        """Hoje na escola: as aulas do horário de hoje (sem as turmas em feriado ou pausa), quantas já têm a chamada, e
        as faltas e os atrasos marcados hoje."""
        Home = self.env['edu.teacher.home']
        planned = 0
        for edu_class in classes:
            if Home._no_lessons_on(edu_class, today):
                continue
            planned += len(edu_class._edu_current_schedules().filtered(lambda s: s._occurs_on(today)))
        lessons = self.env['edu.lesson'].sudo().search([('class_id', 'in', classes.ids), ('date', '=', today)])
        marks = (
            self.env['edu.lesson.attendance']
            .sudo()
            ._read_group([('lesson_id', 'in', lessons.ids)], ['state'], ['__count'])
        )
        counts = dict(marks)
        return {
            'planned': planned,
            'rolled': len(lessons.filtered('attendance_ids')),
            'absent': counts.get('absent', 0),
            'late': counts.get('late', 0),
            'excused': counts.get('excused', 0),
        }

    @api.model
    def _overdue_fees(self, today):
        """As propinas e as outras facturas escolares vencidas e por pagar: quantas, de quantos alunos e o valor."""
        if 'edu_student_id' not in self.env['account.move']._fields:
            return None
        company = self.env.company
        moves = (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('company_id', '=', company.id),
                    ('edu_student_id', '!=', False),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                    ('invoice_date_due', '<', today),
                ]
            )
        )
        return {
            'count': len(moves),
            'students': len(moves.edu_student_id),
            'amount': format_amount(self.env, sum(moves.mapped('amount_residual')), company.currency_id),
        }

    @api.model
    def _pending(self, year, rows, trimester):
        """«Por tratar», como no secPed: só o que tem trabalho, cada linha com a lista onde se resolve."""
        company = self.env.company
        applications = (
            self.env['edu.application']
            .sudo()
            .search_count([('company_id', '=', company.id), ('state', 'in', ('submitted', 'review'))])
        )
        pending_enrollments = (
            self.env['edu.enrollment']
            .sudo()
            .search_count(
                [('academic_year_id', '=', year.id), ('company_id', '=', company.id), ('state', '=', 'draft')]
            )
        )
        documents = (
            self.env['edu.document'].sudo().search_count([('company_id', '=', company.id), ('state', '=', 'draft')])
        )
        no_director = sum(1 for r in rows if not r['director'])
        no_schedule = sum(1 for r in rows if r['no_schedule'])
        no_teacher = sum(r['no_teacher'] for r in rows)
        over = sum(1 for r in rows if r['over'])
        schedule_detail = f'no {trimester.name}' if trimester else ''
        items = [
            ('applications', applications, 'candidatura por analisar', 'candidaturas por analisar', '', False),
            ('enrollments', pending_enrollments, 'matrícula pendente', 'matrículas pendentes', '', False),
            ('documents', documents, 'documento por emitir', 'documentos por emitir', '', False),
            ('directors', no_director, 'turma sem director de turma', 'turmas sem director de turma', '', False),
            ('schedules', no_schedule, 'turma sem horário', 'turmas sem horário', schedule_detail, False),
            ('teachers', no_teacher, 'aula no horário sem professor', 'aulas no horário sem professor', '', False),
            ('capacity', over, 'turma acima da capacidade', 'turmas acima da capacidade', '', True),
        ]
        return [
            {'key': key, 'count': count, 'text': _plural(count, one, many), 'detail': detail, 'urgent': urgent}
            for key, count, one, many, detail, urgent in items
            if count
        ]

    @api.model
    def open(self, key, res_id=False):
        """A lista onde se resolve cada linha do painel (já filtrada), ou a ficha da turma."""
        self._check_access()
        company = self.env.company
        year = self._year()
        if key == 'class':
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'edu.class',
                'res_id': res_id,
                'views': [(False, 'form')],
                'target': 'current',
            }
        if key in ('schedules', 'teachers'):
            return self.env['ir.actions.actions']._for_xml_id('edu_timetable.action_edu_schedule_editor')
        if key == 'calendar':
            return self.env['ir.actions.actions']._for_xml_id('edu_roles.action_edu_school_calendar')
        if key == 'directors':
            return self.env['ir.actions.actions']._for_xml_id('edu_roles.action_edu_class_directors')
        mine = [('company_id', '=', company.id)]
        this_year = [*mine, ('academic_year_id', '=', year.id)]
        xmlid, domain = {
            'applications': (
                'edu_enrollment.action_edu_application',
                [*mine, ('state', 'in', ('submitted', 'review'))],
            ),
            'enrollments': ('edu_enrollment.action_edu_enrollment', [*this_year, ('state', '=', 'draft')]),
            'students': ('edu_enrollment.action_edu_enrollment', [*this_year, ('state', 'in', ENROLLED)]),
            'documents': ('edu_documents.action_edu_document', [*mine, ('state', '=', 'draft')]),
            'fees': (
                'edu_fees.action_edu_invoices',
                [
                    *mine,
                    ('edu_student_id', '!=', False),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                    ('invoice_date_due', '<', fields.Date.context_today(self)),
                ],
            ),
            'lessons': ('edu_attendance.action_edu_lesson', [*mine, ('date', '=', fields.Date.context_today(self))]),
            'capacity': ('edu_core.action_edu_class', this_year),
        }[key]
        action = self.env['ir.actions.actions']._for_xml_id(xmlid)
        action['domain'] = domain
        action['context'] = {}
        return action
