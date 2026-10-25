from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.edu_evaluation.models.edu_rdec import RDEC_LEVELS, RDEC_STATES
from odoo.exceptions import UserError
from odoo.tools import format_amount

from .edu_student_portal import RELATIONSHIPS, day_label, hhmm

# As novidades: o que mudou nos educandos nos últimos dias (as notas lançadas, as faltas, as provas marcadas, as
# facturas e os pagamentos e os relatórios da Iniciação completos).
FEED_DAYS = 30
FEED_LIMIT = 100
ABSENCE_KINDS = {'absent': 'falta injustificada', 'excused': 'falta justificada', 'late': 'atraso'}


def first_name(name):
    return (name or '').split(' ')[0]


class EduGuardianPortal(models.AbstractModel):
    """A área do encarregado (menu «Área do Encarregado»), como a do secPed-Express: o painel com os educandos e o que
    pede atenção, a ficha de cada educando com quem o acompanha, as notas, o RDEC, as faltas, as provas, o calendário
    da escola, as propinas, as novidades, as mensagens e o perfil.

    Os dados de cada educando são os da área do estudante (``edu.student.portal``), lidos em sudo. O educando que o
    browser pede só se aceita se for um dos que a escola ligou a este encarregado com acesso ao portal; senão fica o
    primeiro."""

    _name = 'edu.guardian.portal'
    _description = 'Área do encarregado'

    # O encarregado e os educandos

    @api.model
    def _guardians(self, user=None):
        user = user or self.env.user
        return self.env['edu.guardian'].sudo().search([('partner_id', '=', user.partner_id.id)])

    @api.model
    def _links(self, user=None):
        """As ligações aos educandos com acesso ao portal, como no secPed (``canAccessPortal``)."""
        return self._guardians(user).student_link_ids.filtered(lambda link: link.can_access_portal)

    @api.model
    def _children(self, user=None):
        return self._links(user).student_id.sorted(lambda s: (s.name or '').lower())

    @api.model
    def _has_preschool(self):
        Portal = self.env['edu.student.portal']
        return any(Portal._enrollment(s).class_id.level_id.code == 'INICIACAO' for s in self._children())

    @api.model
    def _child(self, student_id):
        """O educando pedido, se for deste encarregado; senão o primeiro."""
        children = self._children()
        return children.filtered(lambda s: s.id == student_id)[:1] or children[:1]

    @api.model
    def page_data(self, page, options=None):
        """Os dados de uma página da área do encarregado (as acções cliente ``edu_portal.guardian_*``): ``home``,
        ``notifications`` e ``profile`` falam de todos os educandos; ``children``, ``grades``, ``rdec``, ``absences``,
        ``exams`` e ``fees`` de um, o de ``{'student_id'}``."""
        options = options or {}
        Portal = self.env['edu.student.portal']
        guardians = self._guardians()
        children = self._children()
        name = guardians[:1].name or self.env.user.name
        data = {
            'page': page,
            'has_guardian': bool(guardians),
            'name': name,
            'first_name': first_name(name),
            'children': [],
        }
        for student in children:
            enrollment = Portal._enrollment(student)
            data['children'].append(
                {
                    'id': student.id,
                    'name': student.name,
                    'first_name': first_name(student.name),
                    'class': enrollment.class_id._editor_label() if enrollment else '',
                    'preschool': enrollment.class_id.level_id.code == 'INICIACAO',
                }
            )
        if page == 'home':
            data['summaries'] = [self._summary(student) for student in children]
            data['feed'] = self._feed(children)[:5]
            return data
        if page == 'notifications':
            data['feed'] = self._feed(children)
            return data
        if page == 'profile':
            data['profile'] = self._profile(guardians, children)
            return data
        student = self._child(options.get('student_id'))
        if not student:
            return data
        enrollment = Portal._enrollment(student)
        edu_class = enrollment.class_id
        data.update(
            {
                'child_id': student.id,
                'child': {
                    'name': student.name,
                    'first_name': first_name(student.name),
                    'has_enrollment': bool(enrollment),
                    'class': edu_class._editor_label() if edu_class else '',
                    'level': edu_class.level_id.name or '',
                    'year': enrollment.academic_year_id.name or '',
                    'preschool': edu_class.level_id.code == 'INICIACAO',
                },
                'debt': Portal._debt(student) if page != 'fees' else None,
            }
        )
        if page == 'children':
            data['card'] = self._card(student, enrollment)
        elif page == 'grades':
            data['grades'] = Portal._grades_page(student, enrollment, options)
        elif page == 'rdec':
            data['rdec'] = self._rdec(student, enrollment, options.get('trimester_id'))
        elif page == 'absences':
            data['absences'] = Portal.absences(student, enrollment)
            data['recent'] = self._recent_absences(enrollment)
        elif page == 'exams':
            data['exams'] = Portal.exams(student, enrollment)
        elif page == 'fees':
            data['fees'] = Portal.fees(student)
        return data

    # O painel

    @api.model
    def _summary(self, student):
        """O cartão do educando no painel, como no secPed: a turma, a média do ano, a assiduidade, as propinas e as
        disciplinas no limite de faltas."""
        Portal = self.env['edu.student.portal']
        enrollment = Portal._enrollment(student)
        edu_class = enrollment.class_id
        grades = Portal.grades(student, enrollment)
        absences = Portal.absences(student, enrollment)
        fees = Portal.fees(student)
        return {
            'id': student.id,
            'name': student.name,
            'first_name': first_name(student.name),
            'matricula': student.matricula_number or '',
            'has_enrollment': bool(enrollment),
            'class': edu_class._editor_label() if edu_class else '',
            'level': edu_class.level_id.name or '',
            'preschool': edu_class.level_id.code == 'INICIACAO',
            'blocked': grades['blocked'],
            'average': grades.get('year_average'),
            'attendance': {
                'total': absences['total'],
                'present': absences['present'],
                'rate': absences.get('rate'),
            },
            'failed': absences.get('failed', []),
            'at_risk': absences.get('at_risk', []),
            'regime': absences['regime'],
            'overdue': fees['overdue'],
            'overdue_total': fees['overdue_total'],
        }

    @api.model
    def _feed(self, children):
        """As novidades dos educandos nos últimos dias, da mais recente para a mais antiga: as notas lançadas (sem a
        nota, que pode mudar, como nos avisos do secPed), as faltas e os atrasos, as provas marcadas, as facturas
        emitidas, os pagamentos e os relatórios da Iniciação completos."""
        if not children:
            return []
        Portal = self.env['edu.student.portal']
        today = Portal._now(children[:1]).date()
        since = today - timedelta(days=FEED_DAYS)
        names = {s.id: first_name(s.name) for s in children}
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
            .search([('student_id', 'in', children.ids), ('graded', '=', True), ('write_date', '>=', since)])
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
                    ('student_id', 'in', children.ids),
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
        for student in children:
            enrollment = Portal._enrollment(student)
            rows = [row for row in Portal.exams(student, enrollment)['rows'] if not row['done']]
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
                    ('edu_student_id', 'in', children.ids),
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
            .search([('student_id', 'in', children.ids), ('state', '=', 'done'), ('write_date', '>=', since)])
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

    # Os educandos

    @api.model
    def _card(self, student, enrollment):
        """A ficha do educando, como no secPed: a turma deste ano e quem o acompanha (o director de turma e o
        professor de cada disciplina)."""
        link = self._links().filtered(lambda link: link.student_id == student)[:1]
        edu_class = enrollment.class_id
        subjects = []
        if enrollment:
            assignments = edu_class.assignment_ids
            for subject in (enrollment.subject_ids - enrollment._dropped_subjects()).sorted(
                lambda s: (s.name or '').lower()
            ):
                teachers = assignments.filtered(lambda a, s=subject: a.subject_id == s).teacher_id
                subjects.append({'id': subject.id, 'name': subject.name, 'teachers': teachers.mapped('name')})
        return {
            'name': student.name,
            'relationship': RELATIONSHIPS.get(link.relationship, 'Familiar'),
            'primary': link.is_primary,
            'matricula': student.matricula_number or '',
            'class': edu_class._editor_label() if edu_class else '',
            'course': edu_class.course_id.name or '',
            'level': edu_class.level_id.name or '',
            'year': enrollment.academic_year_id.name or '',
            'director': edu_class.director_id.name or '',
            'subjects': subjects,
        }

    # RDEC

    @api.model
    def _rdec(self, student, enrollment, trimester_id=None):
        """O RDEC do educando da Iniciação, só para ler, como no secPed: um trimestre (por omissão o corrente), as
        áreas com o nível e as observações, a apreciação global e as faltas. Com propinas em atraso e a escola em
        modo «bloquear», fica escondido como as notas."""
        edu_class = enrollment.class_id
        if not enrollment or edu_class.level_id.code != 'INICIACAO':
            return {'applicable': False}
        blocked, _message = student._edu_gate('grades')
        if blocked:
            return {'applicable': True, 'blocked': True}
        Rdec = self.env['edu.rdec'].sudo()
        started, current = Rdec._trimesters(enrollment.academic_year_id)
        trimester = started.filtered(lambda t: t.id == trimester_id)[:1] or current
        record = Rdec.search([('enrollment_id', '=', enrollment.id), ('trimester_id', '=', trimester.id)], limit=1)
        levels = dict(RDEC_LEVELS)
        return {
            'applicable': True,
            'blocked': False,
            'trimesters': [{'id': t.id, 'name': t.name} for t in started],
            'trimester_id': trimester.id,
            'trimester': (trimester.name or '').replace('Trimestre', 'trimestre'),
            'director': edu_class.director_id.name or '',
            'rdec_id': record.id,
            'state': record.state or 'todo',
            'state_label': dict(RDEC_STATES).get(record.state or 'todo'),
            'done': record.areas_done,
            'total': record.areas_total,
            'areas': [
                {
                    'id': line.id,
                    'name': line.subject_id.name,
                    'level': line.level or '',
                    'level_label': levels.get(line.level, ''),
                    'observations': line.observations or '',
                }
                for line in record.line_ids
            ],
            'appreciation': record.appreciation or '',
            'absences_justified': record.absences_justified,
            'absences_unjustified': record.absences_unjustified,
        }

    @api.model
    def rdec_report(self, student_id, trimester_id):
        """«Ver RDEC»: o documento da escola (o mesmo da secretaria), visualizado na aplicação."""
        student = self._child(student_id)
        enrollment = self.env['edu.student.portal']._enrollment(student) if student else None
        data = self._rdec(student, enrollment, trimester_id) if enrollment else {}
        if not data.get('rdec_id') or data.get('blocked'):
            raise UserError(self.env._('O RDEC deste trimestre ainda não está disponível.'))
        rdec = self.env['edu.rdec'].browse(data['rdec_id'])
        return self.env.ref('edu_documents.action_report_rdec_html').preview_action(rdec)

    # As faltas

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

    # O perfil

    @api.model
    def _profile(self, guardians, children):
        """Os dados do encarregado na escola (só para ler: corrige-os a secretaria) e os educandos ligados."""
        guardian = guardians[:1]
        links = self._links().sorted(lambda link: (not link.is_primary, link.student_id.name or ''))
        return {
            'name': guardian.name or self.env.user.name,
            'email': guardian.email or self.env.user.email or '',
            'phone': guardian.phone or '',
            'address': ', '.join(p for p in [guardian.street, guardian.city] if p),
            'id_number': guardian.id_number or '',
            'vat': guardian.vat or '',
            'occupation': guardian.occupation or '',
            'children': [
                {
                    'id': link.student_id.id,
                    'name': link.student_id.name,
                    'matricula': link.student_id.matricula_number or '',
                    'relationship': RELATIONSHIPS.get(link.relationship, 'Familiar'),
                    'primary': link.is_primary,
                }
                for link in links
            ],
        }

    # As mensagens

    @api.model
    def _chat_contacts(self):
        """Os contactos da «Nova conversa» das Mensagens, como no secPed: por educando, o director de turma (na
        Iniciação, o educador) e os professores da turma; depois a secretaria e a direcção. Só quem tem utilizador."""
        Portal = self.env['edu.student.portal']
        groups = []
        seen = set()
        for student in self._children():
            enrollment = Portal._enrollment(student)
            edu_class = enrollment.class_id
            if not enrollment:
                continue
            contacts = []
            director = edu_class.director_id.user_id
            if director:
                seen.add(director.id)
                role = 'Educador(a)' if edu_class.level_id.code == 'INICIACAO' else 'Director(a) de turma'
                contacts.append({'partner_id': director.partner_id.id, 'name': director.name, 'detail': role})
            teachers = {}
            for assignment in edu_class.assignment_ids:
                user = assignment.teacher_id.user_id
                if user and user != director:
                    teachers.setdefault(user, []).append(assignment.subject_id.name)
            for user, subjects in sorted(teachers.items(), key=lambda item: item[0].name or ''):
                seen.add(user.id)
                contacts.append({'partner_id': user.partner_id.id, 'name': user.name, 'detail': ', '.join(subjects)})
            if contacts:
                groups.append(
                    {
                        'key': f'child{student.id}',
                        'label': f'{first_name(student.name)}, {edu_class._editor_label()}',
                        'contacts': contacts,
                    }
                )
        companies = self._guardians().company_id or self.env.company
        clerks = (
            self.env['res.users']
            .sudo()
            .search([('share', '=', False), ('company_ids', 'in', companies.ids)], order='name')
            .filtered(lambda u: u.has_group('edu_core.group_edu_user') and u.id not in seen)
        )
        for key, label, members in (
            ('office', 'Secretaria', clerks.filtered(lambda u: not u.has_group('edu_core.group_edu_manager'))),
            ('direction', 'Direcção', clerks.filtered(lambda u: u.has_group('edu_core.group_edu_manager'))),
        ):
            contacts = [{'partner_id': u.partner_id.id, 'name': u.name, 'detail': ''} for u in members]
            if contacts:
                groups.append({'key': key, 'label': label, 'contacts': contacts})
        return groups


class EduTeacherHome(models.AbstractModel):
    _inherit = 'edu.teacher.home'

    @api.model
    def chat_contacts(self):
        # O encarregado escreve a quem acompanha os educandos e à escola.
        if self.env.user._edu_guardian_only():
            return self.env['edu.guardian.portal']._chat_contacts()
        return super().chat_contacts()
