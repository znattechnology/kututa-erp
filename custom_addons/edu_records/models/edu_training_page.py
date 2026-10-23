from odoo import api, fields, models
from odoo.exceptions import UserError

MODELS = {'internship': 'edu.internship', 'project': 'edu.final.project'}
# O que se grava da ficha; o tutor ou orientador só regista as horas e o parecer.
FIELDS = {
    'internship': [
        'entity',
        'supervisor',
        'supervisor_contact',
        'tutor_id',
        'date_start',
        'date_end',
        'hours',
        'appraisal',
        'note',
    ],
    'project': ['name', 'description', 'advisor_id', 'jury_ids', 'defense_date', 'note'],
}
TEACHER_FIELDS = {'internship': ['hours', 'appraisal'], 'project': ['note']}
ACTIONS = {
    'internship': {'start', 'evaluate', 'cancel', 'reopen'},
    'project': {'start', 'submit', 'evaluate', 'reopen'},
}


def _fmt(day):
    return day.strftime('%d/%m/%Y') if day else ''


def _iso(day):
    return fields.Date.to_string(day) if day else ''


class EduTrainingPage(models.AbstractModel):
    """Páginas «Estágios» e «Trabalho de fim de curso» (acções cliente ``edu_records.internships`` e
    ``edu_records.final_projects``), como as do secPed-Express: a lista com o resumo, os separadores por estado e a
    pesquisa; o «Novo» pela turma da classe final (o estágio a vários alunos de uma vez, na mesma entidade) e a ficha de
    acompanhamento. A secretaria gere; o professor vê os estágios de que é tutor e as PAP que orienta, e regista as
    horas, o parecer e os relatórios entregues."""

    _name = 'edu.training.page'
    _description = 'Estágios e PAP'

    @api.model
    def _model(self, kind):
        if kind not in MODELS:
            raise UserError(self.env._('Página desconhecida.'))
        return self.env[MODELS[kind]]

    @api.model
    def _is_staff(self):
        return self.env.user.has_group('edu_core.group_edu_user')

    @api.model
    def _record(self, kind, record_id):
        record = self._model(kind).browse(record_id).exists()
        if not record:
            raise UserError(self.env._('Este registo já não existe.'))
        return record

    @api.model
    def _state_label(self, record):
        return dict(record._fields['state']._description_selection(self.env))[record.state]

    @api.model
    def _teachers(self):
        teachers = (
            self.env['hr.employee']
            .sudo()
            .search([('edu_is_teacher', '=', True), ('company_id', 'in', self.env.companies.ids)], order='name')
        )
        return [{'id': t.id, 'name': t.name} for t in teachers]

    @api.model
    def _row(self, kind, record):
        staff = record.sudo()
        closed = record.state in ('passed', 'failed')
        # Só os nomes, em sudo: o tutor de um estágio pode não ter acesso à turma do aluno.
        row = {
            'id': record.id,
            'student': staff.student_id.name,
            'class': staff.enrollment_id.class_id._editor_label() if staff.enrollment_id else '',
            'year_id': staff.academic_year_id.id or False,
            'state': record.state,
            'state_label': self._state_label(record),
            'grade': record.grade if closed or record.grade else None,
        }
        if kind == 'internship':
            row.update(
                {
                    'entity': record.entity or '',
                    'supervisor': record.supervisor or '',
                    'tutor': staff.tutor_id.name or '',
                    'start': _fmt(record.date_start),
                    'end': _fmt(record.date_end),
                    'hours': record.hours,
                }
            )
        else:
            row.update(
                {
                    'title': record.name,
                    'course': staff.course_id.name or '',
                    'advisor': staff.advisor_id.name or '',
                    'defense': _fmt(record.defense_date),
                }
            )
        return row

    @api.model
    def listing(self, kind):
        Model = self._model(kind)
        records = Model.search([('company_id', 'in', self.env.companies.ids)]).sorted(
            lambda r: (r.sudo().student_id.name or '').lower()
        )
        years = records.sudo().academic_year_id.sorted('date_start', reverse=True)
        current = self.env['edu.academic.year'].search(
            [('is_current', '=', True), ('company_id', 'in', self.env.companies.ids)], limit=1
        )
        return {
            'rows': [self._row(kind, r) for r in records],
            'years': [{'id': y.id, 'name': y.name} for y in years],
            'year_id': current.id if current.id in years.ids else False,
            'is_staff': self._is_staff(),
            'is_manager': self.env.user.has_group('edu_core.group_edu_manager'),
        }

    # Novo

    @api.model
    def new_options(self, kind):
        year = self.env['edu.academic.year'].search(
            [('is_current', '=', True), ('company_id', 'in', self.env.companies.ids)], limit=1
        )
        flag = self._model(kind)._course_flag
        classes = self.env['edu.class'].search([('academic_year_id', '=', year.id)]) if year else self.env['edu.class']
        # Os finalistas: a classe final do curso (a 13.ª no técnico), num curso que prevê o estágio ou a PAP.
        finals = classes.filtered(
            lambda c: c.course_id[flag] and c.class_number == (c.curriculum_id.class_to or c.level_id.class_to)
        )
        return {
            'year': year.name or '',
            'classes': [{'id': c.id, 'label': c._editor_label()} for c in finals],
            'teachers': self._teachers(),
            'today': _iso(fields.Date.context_today(self)),
        }

    @api.model
    def class_students(self, kind, class_id):
        Model = self._model(kind)
        edu_class = self.env['edu.class'].browse(class_id).exists()
        if not edu_class:
            raise UserError(self.env._('A turma já não existe.'))
        enrollments = edu_class.enrollment_ids.filtered(lambda e: e.state in ('active', 'irregular'))
        taken = set(
            Model.search(
                [
                    ('student_id', 'in', enrollments.student_id.ids),
                    ('academic_year_id', '=', edu_class.academic_year_id.id),
                    ('state', 'not in', Model._repeat_states),
                ]
            ).student_id.ids
        )
        students = [
            {
                'enrollment_id': e.id,
                'name': e.student_id.name,
                'number': e.order_number or '',
                'taken': e.student_id.id in taken,
            }
            for e in enrollments
        ]
        return sorted(students, key=lambda s: s['name'].lower())

    @api.model
    def create_records(self, kind, vals):
        """O estágio a vários alunos da mesma turma, de uma vez; a PAP a um aluno."""
        Model = self._model(kind)
        enrollments = self.env['edu.enrollment'].browse(vals.get('enrollment_ids') or []).exists()
        if not enrollments:
            raise UserError(self.env._('Escolha pelo menos um aluno.'))
        common = {k: vals.get(k) or False for k in FIELDS[kind] if k in vals}
        if kind == 'project':
            if len(enrollments) != 1:
                raise UserError(self.env._('A PAP regista-se a um aluno de cada vez.'))
            if not (vals.get('name') or '').strip():
                raise UserError(self.env._('Escreva o tema do trabalho.'))
        elif not (vals.get('entity') or '').strip():
            raise UserError(self.env._('Indique a entidade onde decorre o estágio.'))
        records = Model.create([{**common, 'student_id': e.student_id.id, 'enrollment_id': e.id} for e in enrollments])
        return records.ids

    # Ficha

    @api.model
    def detail(self, kind, record_id):
        record = self._record(kind, record_id)
        staff = record.sudo()
        data = {
            **self._row(kind, record),
            'year': staff.academic_year_id.name or '',
            'course': staff.course_id.name or '',
            'note': record.note or '',
            'grade_value': record.grade,
            'is_staff': self._is_staff(),
            'is_manager': self.env.user.has_group('edu_core.group_edu_manager'),
            'teachers': self._teachers() if self._is_staff() else [],
        }
        if kind == 'internship':
            data.update(
                {
                    'supervisor_contact': record.supervisor_contact or '',
                    'tutor_id': staff.tutor_id.id or False,
                    'date_start': _iso(record.date_start),
                    'date_end': _iso(record.date_end),
                    'appraisal': record.appraisal or '',
                    'reports': [
                        {
                            'id': r.id,
                            'name': r.name,
                            'date': _fmt(r.date),
                            'has_file': bool(r.file_name),
                            'file_name': r.file_name or '',
                        }
                        for r in record.report_ids
                    ],
                }
            )
        else:
            data.update(
                {
                    'description': record.description or '',
                    'advisor_id': staff.advisor_id.id or False,
                    'jury_ids': staff.jury_ids.ids,
                    'jury': ', '.join(staff.jury_ids.mapped('name')),
                    'defense_date': _iso(record.defense_date),
                    'submitted': _fmt(record.submitted_date),
                }
            )
        return data

    @api.model
    def save(self, kind, record_id, vals):
        record = self._record(kind, record_id)
        allowed = FIELDS[kind] if self._is_staff() else TEACHER_FIELDS[kind]
        values = {k: v for k, v in vals.items() if k in allowed}
        for key, value in values.items():
            if value == '':
                values[key] = False
        jury = values.pop('jury_ids', None)
        for key in ('tutor_id', 'advisor_id'):
            if values.get(key) and values[key] not in {t['id'] for t in self._teachers()}:
                raise UserError(self.env._('O tutor ou orientador tem de ser um professor da escola.'))
        if kind == 'internship' and 'entity' in values and not values['entity']:
            raise UserError(self.env._('Indique a entidade onde decorre o estágio.'))
        if kind == 'project' and 'name' in values and not values['name']:
            raise UserError(self.env._('Escreva o tema do trabalho.'))
        if values:
            record.write(values)
        if jury is not None and set(jury or []) != set(record.sudo().jury_ids.ids):
            # O júri liga a fichas de funcionários, que a secretaria não lê: grava-se em sudo, depois de verificar o
            # acesso ao trabalho, e só com professores da escola.
            record.check_access('write')
            teachers = {t['id'] for t in self._teachers()}
            if not set(jury) <= teachers:
                raise UserError(self.env._('O júri é formado por professores da escola.'))
            record.sudo().jury_ids = [(6, 0, list(jury))]
        return self.detail(kind, record.id)

    @api.model
    def run_action(self, kind, record_id, action, value=None):
        if action not in ACTIONS[kind]:
            raise UserError(self.env._('Acção desconhecida.'))
        if not self._is_staff():
            raise UserError(self.env._('Só a secretaria e a direcção mudam o estado.'))
        record = self._record(kind, record_id)
        if action == 'evaluate':
            if value in (None, ''):
                raise UserError(self.env._('Indique a nota, de 0 a 20.'))
            record.action_evaluate(grade=float(value))
        elif action == 'submit':
            record.action_submit(day=value or None)
        else:
            getattr(record, f'action_{action}')()
        return self.detail(kind, record.id)

    @api.model
    def remove(self, kind, record_id):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('Só a direcção remove um estágio ou uma PAP.'))
        record = self._record(kind, record_id)
        record._check_not_in_graduation()
        record.unlink()
        return True

    # Relatórios entregues (estágio)

    @api.model
    def add_report(self, record_id, name, day, file=None):
        record = self._record('internship', record_id)
        if not (name or '').strip():
            raise UserError(self.env._('Escreva o nome do relatório.'))
        vals = {'internship_id': record.id, 'name': name.strip(), 'date': day or fields.Date.context_today(self)}
        if file:
            vals.update({'file': file['datas'], 'file_name': file['name']})
        self.env['edu.internship.report'].create(vals)
        return self.detail('internship', record.id)

    @api.model
    def remove_report(self, report_id):
        report = self.env['edu.internship.report'].browse(report_id).exists()
        if not report:
            raise UserError(self.env._('O relatório já não existe.'))
        internship = report.internship_id
        report.unlink()
        return self.detail('internship', internship.id)
