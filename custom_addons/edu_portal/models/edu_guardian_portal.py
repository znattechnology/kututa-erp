from odoo import api, models
from odoo.addons.edu_evaluation.models.edu_rdec import RDEC_LEVELS, RDEC_STATES
from odoo.exceptions import UserError

from .edu_student_portal import RELATIONSHIPS, first_name


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
            data['feed'] = Portal._feed(children)[:5]
            return data
        if page == 'notifications':
            data['feed'] = Portal._feed(children)
            return data
        if page == 'profile':
            data['profile'] = self._profile(guardians, children)
            return data
        student = self._child(options.get('student_id'))
        if page == 'rdec':
            # O RDEC é da Iniciação: os separadores só com os educandos da Iniciação, e abre no primeiro deles quando o
            # pedido (o educando escolhido noutra página) não é da Iniciação.
            preschool = [c for c in data['children'] if c['preschool']]
            if preschool:
                data['children'] = preschool
                if student.id not in {c['id'] for c in preschool}:
                    student = student.browse(preschool[0]['id'])
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
            data['absence_months'] = Portal._absence_months(student, enrollment)
            data['recent'] = Portal._recent_absences(enrollment)
        elif page == 'exams':
            data['exams'] = Portal.exams(student, enrollment)
        elif page == 'fees':
            data['fees'] = Portal.fees(student)
            data['months'] = Portal._tuition_months(student, enrollment)
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
            # Os gráficos do cartão: a média de cada trimestre, as presenças e as faltas, as disciplinas mais perto do
            # limite de faltas, o RDEC (na Iniciação) e as propinas do ano, mês a mês.
            'trend': [] if grades['blocked'] else grades.get('trend', []),
            'scale_max': grades.get('scale_max') or 20,
            'pass_grade': grades.get('pass_grade') or 10,
            'pass_text': grades.get('pass_text') or '10',
            'lessons': {
                'present': absences.get('present', 0),
                'excused': absences.get('excused', 0),
                'absent': absences.get('absent', 0),
            },
            'meters': sorted(
                (
                    {'name': s['name'], 'counted': s['counted'], 'limit': s['limit'], 'status': s['status']}
                    for s in absences['subjects']
                    if s['limit'] and s['counted']
                ),
                key=lambda m: (-m['counted'] / m['limit'], m['name'].lower()),
            )[:3],
            'rdec': self._rdec(student, enrollment) if edu_class.level_id.code == 'INICIACAO' else None,
            'months': Portal._tuition_months(student, enrollment),
        }

    # Os educandos

    @api.model
    def _card(self, student, enrollment):
        """A ficha do educando, como no secPed: a turma deste ano e quem o acompanha (o director de turma e o
        professor de cada disciplina, com quem se pode abrir conversa nas Mensagens), e os números do painel e a
        próxima prova."""
        link = self._links().filtered(lambda link: link.student_id == student)[:1]
        edu_class = enrollment.class_id

        def person(employee):
            user = employee.user_id
            return {'name': employee.name, 'partner_id': user.partner_id.id if user else False}

        subjects = []
        if enrollment:
            assignments = edu_class.assignment_ids
            for subject in (enrollment.subject_ids - enrollment._dropped_subjects()).sorted(
                lambda s: (s.name or '').lower()
            ):
                teachers = assignments.filtered(lambda a, s=subject: a.subject_id == s).teacher_id
                subjects.append({'id': subject.id, 'name': subject.name, 'teachers': [person(t) for t in teachers]})
        Portal = self.env['edu.student.portal']
        next_exam = next((row for row in Portal.exams(student, enrollment)['rows'] if not row['done']), None)
        return {
            'name': student.name,
            'relationship': RELATIONSHIPS.get(link.relationship, 'Familiar'),
            'primary': link.is_primary,
            'matricula': student.matricula_number or '',
            'class': edu_class._editor_label() if edu_class else '',
            'course': edu_class.course_id.name or '',
            'level': edu_class.level_id.name or '',
            'year': enrollment.academic_year_id.name or '',
            'director': person(edu_class.director_id) if edu_class.director_id else None,
            'subjects': subjects,
            'summary': self._summary(student),
            'next_exam': next_exam,
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
        # Os trimestres anteriores, para a evolução de cada área (o nível que teve em cada um).
        earlier = Rdec.search(
            [
                ('enrollment_id', '=', enrollment.id),
                ('trimester_id', 'in', started.filtered(lambda t: t.number < trimester.number).ids),
            ]
        ).sorted(lambda r: r.trimester_id.number)
        history = {}
        for previous in earlier:
            for line in previous.line_ids.filtered('level'):
                history.setdefault(line.subject_id.id, []).append(
                    {
                        'trimester': previous.trimester_id.name,
                        'level': line.level,
                        'level_label': levels[line.level],
                    }
                )
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
                    # O degrau na escala de quatro níveis (0 por avaliar).
                    'step': [key for key, _label in RDEC_LEVELS].index(line.level) + 1 if line.level else 0,
                    'observations': line.observations or '',
                    'history': history.get(line.subject_id.id, []),
                }
                for line in record.line_ids
            ],
            'levels': [
                {
                    'key': key,
                    'label': label,
                    'count': len(record.line_ids.filtered(lambda line, k=key: line.level == k)),
                }
                for key, label in reversed(RDEC_LEVELS)
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

    # O perfil

    @api.model
    def _profile(self, guardians, children):
        """Os dados do encarregado na escola (só para ler: corrige-os a secretaria) e os educandos ligados."""
        guardian = guardians[:1]
        links = self._links().sorted(lambda link: (not link.is_primary, link.student_id.name or ''))
        Portal = self.env['edu.student.portal']
        # O que falta para as facturas e para a escola contactar o encarregado.
        missing = [
            label
            for label, filled in (
                ('o NIF (vai nas facturas das propinas)', guardian.vat),
                ('o telefone', guardian.phone),
                ('o BI ou passaporte', guardian.id_number),
            )
            if not filled
        ]
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
                    'class': Portal._enrollment(link.student_id).class_id._editor_label()
                    if Portal._enrollment(link.student_id)
                    else '',
                }
                for link in links
            ],
            'missing': missing,
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
        return groups + Portal._office_contacts(companies, seen)


class EduTeacherHome(models.AbstractModel):
    _inherit = 'edu.teacher.home'

    @api.model
    def chat_contacts(self):
        # O aluno escreve aos professores da turma e à escola; o encarregado, a quem acompanha os educandos e à escola.
        if self.env.user._edu_student_only():
            return self.env['edu.student.portal']._chat_contacts()
        if self.env.user._edu_guardian_only():
            return self.env['edu.guardian.portal']._chat_contacts()
        return super().chat_contacts()
