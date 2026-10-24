from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..tools import grading
from .edu_assessment import check_grade_entry

# Nos anos passados as matrículas já estão concluídas ou retidas: contam como alunos da pauta.
ENROLLED = ('active', 'irregular', 'completed', 'retained')
EXIT_CODES = {'dropped': 'c)', 'transferred': 'd)'}
COLUMN_TYPES = {
    'npt': 'trimester_test',
    'npp': 'continuous',
    'pg': 'global_exam',
    'en': 'national_exam',
}
COLUMN_NAMES = {'npt': 'NPT', 'npp': 'NPP', 'pg': 'Prova global', 'en': 'Exame nacional'}


class _RollbackGrid(Exception):
    """Desfaz o lote quando uma das notas não se grava (tudo ou nada)."""


class EduGradeGrid(models.AbstractModel):
    """«Notas da turma» (acção cliente ``edu_evaluation.grade_grid``), como a pauta por disciplina do secPed-Express:
    uma grelha por turma e disciplina, com os alunos nas linhas e, por trimestre, MAC/NPP, NPT, MT/CT e as faltas,
    seguidos da classificação do ano. Edita-se no lugar: o servidor cria as avaliações NPT, NPP, PG e EN quando faltam
    e verifica cada nota com as regras de sempre (janela de lançamento, trimestre fechado, escala)."""

    _name = 'edu.grade.grid'
    _description = 'Notas da turma'

    # Turmas e disciplinas

    @api.model
    def _employee(self):
        return self.env.user.employee_id

    @api.model
    def _is_staff(self):
        return self.env.su or self.env.user.has_group('edu_core.group_edu_user')

    @api.model
    def grid_classes(self, year_id=False):
        """Os anos lectivos e as turmas do ano escolhido (por omissão, o corrente): o professor, as que lecciona ou
        dirige; a secretaria, todas. Os anos passados abrem-se para consulta."""
        Year = self.env['edu.academic.year']
        company_domain = [('company_id', 'in', self.env.companies.ids)]
        years = Year.search(company_domain, order='date_start desc')
        year = years.filtered(lambda y: y.id == year_id)[:1] or years.filtered('is_current')[:1] or years[:1]
        year_rows = [{'id': y.id, 'name': y.name, 'is_current': y.is_current} for y in years]
        if not year:
            return {'year': False, 'year_id': False, 'years': year_rows, 'classes': []}
        classes = self.env['edu.class'].sudo().search([('academic_year_id', '=', year.id)])
        employee = self._employee()
        staff = self._is_staff()
        rows = []
        for edu_class in classes.sorted(lambda c: (c.class_number, c.course_id.code or '', c.name or '')):
            mine = edu_class.assignment_ids.filtered(lambda a: a.teacher_id == employee).subject_id
            directs = bool(employee) and edu_class.director_id == employee
            if not (staff or mine or directs):
                continue
            rows.append(
                {
                    'id': edu_class.id,
                    'name': edu_class._editor_label(),
                    'course': edu_class.course_id.name or '',
                    'directs': directs,
                    'mine': mine.ids,
                    'students': len(edu_class.enrollment_ids.filtered(lambda e: e.state in ENROLLED)),
                    'links': self._class_links(edu_class, directs or staff),
                }
            )
        return {'year': year.name, 'year_id': year.id, 'years': year_rows, 'classes': rows, 'staff': staff}

    # O que se abre a partir da turma (como os botões da página da turma no secPed: o menu do professor não os repete)

    @api.model
    def _class_links(self, edu_class, directs):
        """Os botões da turma escolhida, por ordem: ``key`` (para ``class_link_action``), ``label`` e ``icon``. Cada
        módulo acrescenta os seus; ``directs`` é o director de turma (ou a secretaria)."""
        links = [{'key': 'council', 'label': self.env._('Conselho de turma'), 'icon': 'forum'}]
        if edu_class.level_id.code == 'INICIACAO':
            links.append({'key': 'rdec', 'label': self.env._('RDEC'), 'icon': 'description'})
        return links

    @api.model
    def class_link_action(self, class_id, key):
        edu_class = self._class(class_id)
        employee = self._employee()
        directs = bool(employee) and edu_class.sudo().director_id == employee
        teaches = bool(employee) and employee in edu_class.sudo().assignment_ids.teacher_id
        if not (self._is_staff() or directs or teaches):
            raise AccessError(self.env._('Esta turma não é sua.'))
        if key not in {link['key'] for link in self._class_links(edu_class, directs or self._is_staff())}:
            raise UserError(self.env._('Esta opção não existe para a turma.'))
        return self._class_link_action(edu_class, key)

    @api.model
    def _class_link_action(self, edu_class, key):
        if key == 'council':
            action = self.env['ir.actions.actions']._for_xml_id('edu_evaluation.action_edu_council_board')
            action['context'] = {'default_class_id': edu_class.id}
            return action
        if key == 'rdec':
            action = self.env['ir.actions.actions']._for_xml_id('edu_evaluation.action_edu_rdec')
            action['domain'] = [('class_id', '=', edu_class.id)]
            action['name'] = self.env._('RDEC · %s', edu_class._editor_label())
            return action
        return False

    @api.model
    def grid_subjects(self, class_id):
        edu_class = self._class(class_id)
        employee = self._employee()
        staff = self._is_staff()
        mine = edu_class.sudo().assignment_ids.filtered(lambda a: a.teacher_id == employee).subject_id
        directs = bool(employee) and edu_class.sudo().director_id == employee
        lines = edu_class.sudo().subject_line_ids.filtered('weekly_hours').sorted(lambda li: li.subject_id.name or '')
        subjects = []
        for line in lines:
            subject = line.subject_id
            if not (staff or directs or subject in mine):
                continue
            subjects.append(
                {
                    'id': subject.id,
                    'name': subject.name,
                    'code': subject.code or '',
                    # A pauta só a edita o professor que lecciona a disciplina; a secretaria e o director consultam.
                    'editable': subject in mine,
                }
            )
        return subjects

    @api.model
    def _class(self, class_id):
        edu_class = self.env['edu.class'].browse(class_id).exists()
        if not edu_class:
            raise UserError(self.env._('A turma já não existe.'))
        return edu_class

    @api.model
    def _teaches(self, edu_class, subject):
        employee = self._employee()
        return (
            bool(employee)
            and subject in edu_class.sudo().assignment_ids.filtered(lambda a: a.teacher_id == employee).subject_id
        )

    @api.model
    def _check_read(self, edu_class, subject):
        """Lê a pauta da disciplina quem a lecciona, quem dirige a turma, e a secretaria."""
        if self._is_staff():
            return
        employee = self._employee()
        directs = bool(employee) and edu_class.sudo().director_id == employee
        teaches = subject in edu_class.sudo().assignment_ids.filtered(lambda a: a.teacher_id == employee).subject_id
        if not (directs or teaches):
            raise AccessError(self.env._('Só o professor da disciplina e o director de turma vêem esta pauta.'))

    # Dados da pauta da disciplina

    @api.model
    def grid_data(self, class_id, subject_id):
        edu_class = self._class(class_id)
        subject = self.env['edu.subject'].browse(subject_id)
        self._check_read(edu_class, subject)
        policy = self.env['edu.evaluation.policy']._get(edu_class.company_id, edu_class.level_id)
        technical = policy.regime == 'technical'
        year = edu_class.academic_year_id
        trimesters = year.trimester_ids.sorted('number')
        last = trimesters[-1:]
        exam_class = not technical and policy._is_exam_class(edu_class.class_number)
        line = edu_class.sudo().subject_line_ids.filtered(lambda li: li.subject_id == subject)[:1]
        has_pg = technical and bool(line.has_global_exam)
        has_en = exam_class and bool(line.is_national_exam or subject.is_national_exam)
        Assessment = self.env['edu.assessment'].sudo()
        assessments = Assessment.search([('class_id', '=', edu_class.id), ('subject_id', '=', subject.id)])

        enrollments = self.env['edu.enrollment'].sudo()._for_class_subject(edu_class, subject)
        # Quem saiu (c, d) e, nos anos passados, quem concluiu ou ficou retido.
        others = edu_class.sudo().enrollment_ids.filtered(
            lambda e: (
                e.state in (*EXIT_CODES, 'completed', 'retained')
                and subject in e.subject_ids
                and subject not in e.subject_drop_ids.subject_id
            )
        )
        enrollments = (enrollments | others).sorted(lambda e: (e.class_id != edu_class, e.order_number or 9999, e.id))
        terms = (
            self.env['edu.term.result']
            .sudo()
            .search([('enrollment_id', 'in', enrollments.ids), ('subject_id', '=', subject.id)])
        )
        term_by_key = {(t.enrollment_id.id, t.trimester_id.id): t for t in terms}
        results = (
            self.env['edu.subject.result']
            .sudo()
            .search([('enrollment_id', 'in', enrollments.ids), ('subject_id', '=', subject.id)])
        )
        result_by_enrollment = {r.enrollment_id.id: r for r in results}
        grades = (
            self.env['edu.grade']
            .sudo()
            .search([('enrollment_id', 'in', enrollments.ids), ('assessment_id', 'in', assessments.ids)])
        )
        grade_by_key = {(g.enrollment_id.id, g.assessment_id.id): g for g in grades}
        absences = self._absences(enrollments, subject)

        teaches = self._teaches(edu_class, subject)
        trimester_rows = []
        for trimester in trimesters:
            continuous = assessments.filtered(
                lambda a, t=trimester: a.trimester_id == t and a.assessment_type == 'continuous'
            )
            # Técnico: a NPP é uma só avaliação contínua por trimestre (não há MAC); a de anos migrados com várias
            # fica só para consulta (a média delas).
            npp_only = len(continuous) <= 1
            if teaches:
                editable, reason = self._editable(edu_class, subject, trimester)
            else:
                editable = False
                reason = self.env._('Só o professor que lecciona a disciplina lança as notas, no Painel do Professor.')
            permission = False
            employee = self._employee()
            if employee and not self._is_staff():
                permission = (
                    self.env['edu.grade.edit.permission']
                    .sudo()
                    .search(
                        [
                            ('teacher_id', '=', employee.id),
                            ('class_id', '=', edu_class.id),
                            ('subject_id', '=', subject.id),
                            ('trimester_id', '=', trimester.id),
                            ('revoked', '=', False),
                            ('date_expiry', '>', fields.Datetime.now()),
                        ],
                        limit=1,
                    )
                )
            trimester_rows.append(
                {
                    'id': trimester.id,
                    'number': trimester.number,
                    'name': trimester.name,
                    'is_current': trimester.is_current and year.is_current,
                    'closed': trimester.state == 'closed',
                    'editable': editable,
                    'reason': reason,
                    'permission_until': bool(permission)
                    and fields.Datetime.context_timestamp(self, permission.date_expiry).strftime('%d/%m/%Y'),
                    # Técnico: a NPP escreve-se na grelha (uma avaliação «NPP»); com várias contínuas, é a média delas.
                    'npp_editable': technical and npp_only,
                    'has_npt': not (exam_class and trimester == last),
                    'continuous_count': len(continuous),
                }
            )

        def value(record, field, flag):
            return record[field] if record and record[flag] else None

        students = []
        summary = {'positives': 0, 'negatives': 0, 'without_final': 0, 'total': 0.0}
        # Durante o ano: as positivas e as negativas de cada trimestre (a classificação do trimestre).
        by_term = {trimester.id: [0, 0] for trimester in trimesters}
        round_fn = grading.rounder(policy.rounding)
        for enrollment in enrollments:
            terms_row = {}
            running = None  # CT do técnico: engloba os trimestres anteriores
            for trimester in trimesters:
                term = term_by_key.get((enrollment.id, trimester.id))
                test = assessments.filtered(
                    lambda a, t=trimester: a.trimester_id == t and a.assessment_type == 'trimester_test'
                )[:1]
                npp = assessments.filtered(
                    lambda a, t=trimester: a.trimester_id == t and a.assessment_type == 'continuous'
                )
                npp = npp if len(npp) == 1 else npp.browse()
                npt_grade = grade_by_key.get((enrollment.id, test.id)) if test else None
                npp_grade = grade_by_key.get((enrollment.id, npp.id)) if npp else None
                excused, absent = absences.get((enrollment.id, trimester.id), (0, 0))
                mt = value(term, 'mt', 'has_mt')
                if mt is not None and technical:
                    running = round_fn(mt) if running is None else round_fn((running + mt) / 2)
                classification = (running if technical else mt) if mt is not None else None
                if classification is not None and enrollment.state in ENROLLED:
                    by_term[trimester.id][0 if classification >= policy.pass_grade else 1] += 1
                terms_row[str(trimester.id)] = {
                    'mac': value(term, 'mac', 'has_mac'),
                    'npt': value(term, 'npt', 'has_npt'),
                    'mt': value(term, 'mt', 'has_mt'),
                    'imported': bool(term and term.imported),
                    'npt_grade': npt_grade.score if npt_grade and npt_grade.graded else None,
                    'npt_absent': bool(npt_grade and npt_grade.absent),
                    'npp_grade': npp_grade.score if npp_grade and npp_grade.graded else None,
                    'npp_absent': bool(npp_grade and npp_grade.absent),
                    'fj': excused,
                    'fi': absent,
                }
            result = result_by_enrollment.get(enrollment.id)
            final = result.final if result and result.complete else None
            if enrollment.state in ENROLLED:
                if final is None:
                    summary['without_final'] += 1
                elif final >= policy.pass_grade:
                    summary['positives'] += 1
                    summary['total'] += final
                else:
                    summary['negatives'] += 1
                    summary['total'] += final
            pg_assessment = assessments.filtered(lambda a: a.assessment_type == 'global_exam')[:1]
            en_assessment = assessments.filtered(lambda a: a.assessment_type == 'national_exam')[:1]
            pg_grade = grade_by_key.get((enrollment.id, pg_assessment.id)) if pg_assessment else None
            en_grade = grade_by_key.get((enrollment.id, en_assessment.id)) if en_assessment else None
            students.append(
                {
                    'enrollment_id': enrollment.id,
                    'number': enrollment.order_number if enrollment.class_id == edu_class else '',
                    'name': enrollment.student_id.name,
                    'exit': EXIT_CODES.get(enrollment.state, False),
                    'visiting': enrollment.class_id != edu_class and f'Da {enrollment.class_id.class_number}ª classe',
                    'terms': terms_row,
                    'cf': result.cf if result and result.trimesters_graded else None,
                    'pg': pg_grade.score if pg_grade and pg_grade.graded else None,
                    'pg_absent': bool(pg_grade and pg_grade.absent),
                    'en': en_grade.score if en_grade and en_grade.graded else None,
                    'en_absent': bool(en_grade and en_grade.absent),
                    'annual': result.annual if result and result.complete else None,
                    'final': final,
                    'cfd': result.cfd if result and result.complete and result.terminal_subject else None,
                    'complete': bool(result and result.complete),
                }
            )
        graded = summary['positives'] + summary['negatives']
        span, terminal = results[:1]._subject_span() if results else ([edu_class.class_number], True)
        last_editable = trimester_rows[-1]['editable'] if trimester_rows else False
        return {
            'class': {'id': edu_class.id, 'name': edu_class._editor_label(), 'class_number': edu_class.class_number},
            'subject': {
                'id': subject.id,
                'name': subject.name,
                'code': subject.code or '',
                'span': span,
                'terminal': terminal,
                'has_pg': has_pg,
                'has_en': has_en,
                'pg_editable': has_pg and last_editable,
                'en_editable': has_en and last_editable,
            },
            'regime': policy.regime,
            'technical': technical,
            'exam_class': exam_class,
            'policy': {
                'scale_max': policy.scale_max,
                'pass_grade': policy.pass_grade,
                'mac_weight': policy.mac_weight,
                'rounding': policy.rounding,
            },
            'can_edit': any(t['editable'] for t in trimester_rows),
            'trimesters': trimester_rows,
            'students': students,
            'summary': {
                'positives': summary['positives'],
                'negatives': summary['negatives'],
                'without_final': summary['without_final'],
                'average': round(summary['total'] / graded, 1) if graded else None,
                # O último trimestre com classificações (antes da nota final, é o que interessa à turma).
                'term': next(
                    (
                        {'name': t.name, 'positives': by_term[t.id][0], 'negatives': by_term[t.id][1]}
                        for t in reversed(trimesters)
                        if sum(by_term[t.id])
                    ),
                    None,
                ),
            },
        }

    @api.model
    def _editable(self, edu_class, subject, trimester):
        """(pode lançar, porquê não): as mesmas regras do lançamento (check_grade_entry)."""
        try:
            check_grade_entry(self.env, edu_class, subject, trimester)
        except (AccessError, UserError) as error:
            return False, str(error.args[0] if error.args else error)
        return True, False

    @api.model
    def _absences(self, enrollments, subject):
        if 'edu.absence.summary' not in self.env:
            return {}
        rows = (
            self.env['edu.absence.summary']
            .sudo()
            .search([('enrollment_id', 'in', enrollments.ids), ('subject_id', '=', subject.id)])
        )
        return {(r.enrollment_id.id, r.trimester_id.id): (r.excused, r.absent) for r in rows}

    # Gravação

    @api.model
    def grid_save(self, class_id, subject_id, changes):
        """Grava as notas escritas na grelha, tudo ou nada. ``changes``: [{enrollment_id, trimester_id, column
        ('npt'|'npp'|'pg'|'en'), value (número ou None para apagar), absent}]. Devolve {ok, errors, data}."""
        edu_class = self._class(class_id)
        subject = self.env['edu.subject'].browse(subject_id)
        if not self._teaches(edu_class, subject):
            raise AccessError(self.env._('Só o professor que lecciona a disciplina lança as notas.'))
        trimesters = edu_class.academic_year_id.trimester_ids.sorted('number')
        last = trimesters[-1:]
        # As mesmas regras da grelha, no servidor: as colunas que existem e os alunos que ainda estão na turma.
        data = self.grid_data(class_id, subject_id)
        allowed = {'npt'}
        if data['technical']:
            allowed.add('npp')
        if data['subject']['has_pg']:
            allowed.add('pg')
        if data['subject']['has_en']:
            allowed.add('en')
        students = {s['enrollment_id'] for s in data['students'] if not s['exit']}
        errors = []
        try:
            with self.env.cr.savepoint():
                for change in changes:
                    column = change.get('column')
                    if column not in COLUMN_TYPES:
                        raise UserError(self.env._('Coluna desconhecida: %s.', column))
                    trimester = (
                        last if column in ('pg', 'en') else self.env['edu.trimester'].browse(change.get('trimester_id'))
                    )
                    try:
                        if column not in allowed:
                            raise UserError(self.env._('Esta disciplina não tem a coluna %s.', COLUMN_NAMES[column]))
                        if change.get('enrollment_id') not in students:
                            raise UserError(self.env._('Este aluno já não está na turma.'))
                        assessment = self._assessment(edu_class, subject, trimester, column)
                        self._write_grade(assessment, change)
                    except (UserError, ValidationError, AccessError) as error:
                        errors.append({**change, 'message': str(error.args[0] if error.args else error)})
                if errors:
                    raise _RollbackGrid
        except _RollbackGrid:
            return {'ok': False, 'errors': errors}
        return {'ok': True, 'errors': [], 'data': self.grid_data(class_id, subject_id)}

    @api.model
    def _assessment(self, edu_class, subject, trimester, column):
        """A avaliação da coluna (NPT, NPP, PG, EN) do trimestre: a que existe, ou uma nova."""
        kind = COLUMN_TYPES[column]
        Assessment = self.env['edu.assessment']
        domain = [
            ('class_id', '=', edu_class.id),
            ('subject_id', '=', subject.id),
            ('assessment_type', '=', kind),
        ]
        if column in ('npt', 'npp'):
            domain.append(('trimester_id', '=', trimester.id))
        if column == 'npp' and Assessment.sudo().search_count(domain) > 1:
            raise UserError(
                self.env._('Este trimestre tem várias avaliações contínuas antigas: a NPP é a média delas.')
            )
        assessment = Assessment.sudo().search(domain, limit=1)
        if assessment:
            return assessment.with_env(self.env)
        check_grade_entry(self.env, edu_class, subject, trimester)
        name = COLUMN_NAMES[column]
        if column == 'npt':
            name = self.env._('Prova do %s', trimester.name)
        return (
            Assessment.sudo()
            .create(
                {
                    'name': name if column != 'npp' else 'NPP',
                    'class_id': edu_class.id,
                    'subject_id': subject.id,
                    'trimester_id': trimester.id,
                    'assessment_type': kind,
                    'date': fields.Date.context_today(self),
                }
            )
            .with_env(self.env)
        )

    @api.model
    def _write_grade(self, assessment, change):
        enrollment = self.env['edu.enrollment'].browse(change.get('enrollment_id'))
        Grade = self.env['edu.grade']
        grade = Grade.search([('assessment_id', '=', assessment.id), ('enrollment_id', '=', enrollment.id)], limit=1)
        value = change.get('value')
        if change.get('absent'):
            vals = {'absent': True}
        elif value is None or value == '':
            if grade:
                grade.action_clear()
            return
        else:
            vals = {'score': float(value), 'absent': False}
        if grade:
            grade.write(vals)
        else:
            Grade.create({'assessment_id': assessment.id, 'enrollment_id': enrollment.id, **vals})

    # Lançar MAC (avaliações contínuas)

    @api.model
    def grid_open_continuous(self, class_id, subject_id, trimester_id):
        """As avaliações contínuas do trimestre (o MAC), na lista de avaliações já filtrada."""
        edu_class = self._class(class_id)
        subject = self.env['edu.subject'].browse(subject_id)
        self._check_read(edu_class, subject)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Avaliações contínuas · %(subject)s · %(class)s', subject=subject.name,
                               **{'class': edu_class._editor_label()}),
            'res_model': 'edu.assessment',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [
                ('class_id', '=', edu_class.id),
                ('subject_id', '=', subject.id),
                ('trimester_id', '=', trimester_id),
                ('assessment_type', '=', 'continuous'),
            ],
            'context': {
                'default_class_id': edu_class.id,
                'default_subject_id': subject.id,
                'default_trimester_id': trimester_id,
                'default_assessment_type': 'continuous',
            },
        }  # fmt: skip
