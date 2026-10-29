from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import import_mode, is_marked, is_trusted, trusted
from odoo.addons.edu_enrollment.models.edu_enrollment import SEAT_STATES
from odoo.exceptions import AccessError, UserError, ValidationError

from ..tools.grading_higher import Outcome, frequency_mark, resolve, round_grade
from .edu_curriculum import SEMESTERS

STATES = [
    ('enrolled', 'Inscrito'),
    ('passed', 'Aprovado'),
    ('failed', 'Reprovado'),
    ('dropped', 'Anulada'),
]
# Por aprovar: conta como UC em atraso no ano seguinte.
PENDING = ('failed', 'dropped', 'enrolled')
FREQUENCY_STATUSES = [
    ('pending', 'Sem média'),
    ('exempt', 'Dispensado'),
    ('admitted', 'Admitido a exame'),
    ('excluded', 'Excluído'),
]
SOURCES = [
    ('frequency', 'Frequência'),
    ('normal', 'Exame normal'),
    ('appeal', 'Recurso'),
    ('special', 'Exame especial'),
    ('improvement', 'Melhoria'),
    ('final_work', 'Defesa do trabalho final'),
    ('equivalence', 'Equivalência'),
]
EXAMS = ('exam_normal', 'exam_appeal', 'exam_special', 'exam_improvement')
# Calculados pelo motor: só o servidor os escreve.
COMPUTED = (
    'frequency_mark', 'has_frequency_mark', 'attendance_rate', 'has_attendance', 'frequency_status', 'final_grade',
    'has_final', 'result_source', 'is_equivalence',
)  # fmt: skip
ASSESSMENT_TYPES = ('frequency', 'coursework', 'continuous')


class EduUcRegistration(models.Model):
    """Inscrição do estudante numa unidade curricular, no ano académico da matrícula. É a fonte das disciplinas da
    matrícula: a UC frequentada na turma do estudante entra nas suas disciplinas; a UC em atraso frequentada numa
    turma de um ano anterior entra como disciplina noutra turma. Assim as notas, a chamada e as pautas servem as UCs
    sem mais nada."""

    _name = 'edu.uc.registration'
    _description = 'Inscrição em unidade curricular'
    _order = 'enrollment_id, semester, course_year, subject_id'
    _check_company_auto = True
    _rec_name = 'subject_id'

    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', required=True, ondelete='cascade', index=True, check_company=True
    )
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, index=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id', store=True, index=True)
    course_id = fields.Many2one(related='enrollment_id.course_id', store=True)
    subject_id = fields.Many2one('edu.subject', string='Unidade curricular', required=True, check_company=True)
    curriculum_line_id = fields.Many2one(
        'edu.curriculum.line',
        string='Linha do plano',
        compute='_compute_curriculum_line_id',
        store=True,
        precompute=True,
    )
    course_year = fields.Integer(string='Ano', related='curriculum_line_id.year_id.year', store=True)
    semester = fields.Selection(SEMESTERS, string='Semestre', related='curriculum_line_id.semester', store=True)
    credits = fields.Float(string='Créditos', related='curriculum_line_id.credits', store=True, digits=(4, 1))
    uc_type = fields.Selection(related='curriculum_line_id.uc_type')
    class_id = fields.Many2one(
        'edu.class',
        string='Turma onde frequenta',
        compute='_compute_class_id',
        store=True,
        readonly=False,
        precompute=True,
        check_company=True,
        domain="[('academic_year_id', '=', academic_year_id), ('course_id', '=', course_id)]",
    )
    attempt = fields.Integer(string='Inscrição n.º', readonly=True, copy=False)
    is_backlog = fields.Boolean(string='Em atraso', compute='_compute_is_backlog', store=True)
    state = fields.Selection(STATES, string='Situação', default='enrolled', required=True, readonly=True, copy=False)
    note = fields.Char(string='Observação')
    # Avaliação (motor em tools/grading_higher.py, regras do regulamento académico)
    frequency_mark = fields.Float(string='MF', digits=(4, 2), readonly=True, help='Média de frequência.')
    has_frequency_mark = fields.Boolean(readonly=True)
    attendance_rate = fields.Float(string='Assiduidade (%)', digits=(5, 1), readonly=True)
    has_attendance = fields.Boolean(readonly=True)
    frequency_status = fields.Selection(
        FREQUENCY_STATUSES, string='Frequência', default='pending', required=True, readonly=True
    )
    exam_normal = fields.Float(string='Exame normal', digits=(4, 2))
    has_exam_normal = fields.Boolean(string='Com exame normal')
    exam_appeal = fields.Float(string='Recurso', digits=(4, 2))
    has_exam_appeal = fields.Boolean(string='Com recurso')
    exam_special = fields.Float(string='Exame especial', digits=(4, 2))
    has_exam_special = fields.Boolean(string='Com exame especial')
    exam_improvement = fields.Float(string='Melhoria', digits=(4, 2))
    has_exam_improvement = fields.Boolean(string='Com melhoria')
    final_grade = fields.Float(string='Nota final', digits=(4, 2), readonly=True)
    has_final = fields.Boolean(string='Com nota final', readonly=True)
    result_source = fields.Selection(SOURCES, string='Origem da nota', readonly=True)
    is_equivalence = fields.Boolean(
        string='Por equivalência', readonly=True, help='Aprovada noutra instituição ou curso e creditada aqui.'
    )
    credits_earned = fields.Float(string='Créditos obtidos', compute='_compute_credits_earned', digits=(4, 1))

    _enrollment_subject_uniq = models.Constraint(
        'UNIQUE(enrollment_id, subject_id)', 'O estudante já está inscrito nesta UC neste ano.'
    )

    @api.depends('subject_id', 'enrollment_id.class_id.curriculum_id')
    def _compute_curriculum_line_id(self):
        for registration in self:
            curriculum = registration.enrollment_id.class_id.curriculum_id
            registration.curriculum_line_id = curriculum.line_ids.filtered(
                lambda line, s=registration.subject_id: line.subject_id == s
            )[:1]

    @api.depends('state', 'credits')
    def _compute_credits_earned(self):
        for registration in self:
            registration.credits_earned = registration.credits if registration.state == 'passed' else 0

    @api.depends('course_year', 'enrollment_id.class_number')
    def _compute_is_backlog(self):
        for registration in self:
            registration.is_backlog = bool(registration.course_year) and (
                registration.course_year < registration.enrollment_id.class_number
            )

    @api.depends('curriculum_line_id', 'enrollment_id.class_id')
    def _compute_class_id(self):
        for registration in self:
            if not registration.class_id:
                registration.class_id = registration._backlog_class() or registration.enrollment_id.class_id

    def _backlog_class(self):
        """Para a UC de um ano anterior, uma turma desse ano no mesmo curso e ano académico (de preferência do mesmo
        turno)."""
        self.ensure_one()
        enrollment = self.enrollment_id
        if not self.course_year or self.course_year >= enrollment.class_number:
            return self.env['edu.class']
        classes = self.env['edu.class'].search(
            [
                ('academic_year_id', '=', enrollment.academic_year_id.id),
                ('course_id', '=', enrollment.course_id.id),
                ('class_number', '=', self.course_year),
            ]
        )
        classes = classes.filtered(lambda c: self.subject_id in c.subject_line_ids.subject_id)
        same_shift = classes.filtered(lambda c: c.shift_id == enrollment.class_id.shift_id)
        return (same_shift or classes)[:1]

    # ------------------------------------------------------------------
    # Regras
    # ------------------------------------------------------------------
    def _regulation(self):
        self.ensure_one()
        enrollment = self.enrollment_id
        return self.env['edu.university.regulation']._get(enrollment.company_id, enrollment.course_id.level_id)

    def _previous(self):
        """As inscrições do estudante nesta UC em anos anteriores."""
        self.ensure_one()
        return self.sudo().search(
            [
                ('student_id', '=', self.student_id.id),
                ('subject_id', '=', self.subject_id.id),
                ('id', '!=', self.id),
                ('academic_year_id.date_start', '<', self.academic_year_id.date_start),
            ]
        )

    def _passed_subjects(self):
        """As UCs que o estudante já aprovou (em qualquer ano)."""
        self.ensure_one()
        return self.sudo().search([('student_id', '=', self.student_id.id), ('state', '=', 'passed')]).subject_id

    def _missing_precedences(self, siblings=None):
        """As precedências da UC que não estão aprovadas nem se fazem num semestre anterior do mesmo ano."""
        self.ensure_one()
        siblings = self.enrollment_id.uc_registration_ids if siblings is None else siblings
        earlier = siblings.filtered(
            lambda r: r != self and r.state != 'dropped' and r.semester == '1' and self.semester == '2'
        ).subject_id
        return self.subject_id.prerequisite_ids - self._passed_subjects() - earlier

    @api.constrains('subject_id', 'enrollment_id')
    def _check_registration(self):
        for registration in self:
            enrollment, subject = registration.enrollment_id, registration.subject_id
            if enrollment.level_subsystem != 'higher':
                raise ValidationError(self.env._('A inscrição por UC é do ensino superior.'))
            if not registration.curriculum_line_id:
                raise ValidationError(
                    self.env._('%(uc)s não é do plano curricular de %(course)s.', uc=subject.name,
                               course=enrollment.course_id.name)
                )  # fmt: skip
            if registration.course_year > enrollment.class_number:
                raise ValidationError(
                    self.env._(
                        '%(uc)s é do %(year)sº ano: o estudante está no %(current)sº.',
                        uc=subject.name,
                        year=registration.course_year,
                        current=enrollment.class_number,
                    )
                )
            if registration.is_equivalence:
                continue
            if subject in registration._passed_subjects() and registration.state != 'passed':
                raise ValidationError(self.env._('O estudante já aprovou %s.', subject.name))
            missing = registration._missing_precedences()
            if missing:
                raise ValidationError(
                    self.env._(
                        'Para %(uc)s falta aprovar: %(missing)s.',
                        uc=subject.name,
                        missing=', '.join(missing.mapped('name')),
                    )
                )
            regulation = registration._regulation()
            if registration.attempt > regulation.max_attempts:
                raise ValidationError(
                    self.env._(
                        '%(uc)s prescreveu: o regulamento permite %(max)s inscrições na mesma UC.',
                        uc=subject.name,
                        max=regulation.max_attempts,
                    )
                )

    @api.constrains('subject_id', 'enrollment_id', 'state')
    def _check_credits(self):
        if import_mode(self.env, 'edu_uc_generate'):
            return
        for enrollment in self.enrollment_id:
            excess = enrollment._edu_uc_credit_excess()
            if excess:
                raise ValidationError(excess)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        enrollments = self.env['edu.enrollment'].browse(
            [vals['enrollment_id'] for vals in vals_list if vals.get('enrollment_id')]
        )
        if not is_trusted(self.env) and any(set(COMPUTED) & set(vals) for vals in vals_list):
            raise AccessError(self.env._('A situação e a nota da UC não se gravam à mão.'))
        if not is_trusted(self.env) and enrollments.filtered(lambda e: e.state not in SEAT_STATES):
            raise UserError(self.env._('Só se inscreve em UCs com a matrícula em curso.'))
        registrations = super().create(vals_list)
        for registration in registrations:
            with trusted(self.env):
                registration.attempt = len(registration._previous()) + 1
                if not registration.is_equivalence:
                    registration._sync_enrollment()
        # As regras correm depois do n.º da inscrição (prescrição) e da ligação à turma.
        registrations._check_registration()
        registrations.filtered('is_backlog')._edu_charge('backlog')
        return registrations

    def write(self, vals):
        if 'state' in vals and not is_trusted(self.env):
            raise AccessError(self.env._('A situação na UC resulta da avaliação (ou de «Anular»).'))
        if set(COMPUTED) & set(vals) and not is_trusted(self.env):
            raise AccessError(self.env._('A média, a situação e a nota final calculam-se a partir das notas.'))
        exams = set(EXAMS) & set(vals)
        if exams:
            vals = dict(vals)
            for name in exams:
                vals.setdefault(f'has_{name}', vals[name] is not False and vals[name] is not None)
            for registration in self:
                registration._check_exam_entry(vals)
        if {'enrollment_id', 'subject_id'} & set(vals) and not is_trusted(self.env):
            raise UserError(self.env._('Para mudar de UC, anule esta inscrição e crie outra.'))
        old_classes = {registration: registration.class_id for registration in self}
        result = super().write(vals)
        if exams or {f'has_{name}' for name in EXAMS} & set(vals):
            self._edu_uc_refresh()
        if 'class_id' in vals:
            for registration in self.filtered(lambda r: r.class_id != old_classes[r]):
                registration._unsync_enrollment(old_classes[registration])
                registration._sync_enrollment()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_only_enrolled(self):
        for registration in self:
            if registration.state != 'enrolled' and not is_trusted(self.env):
                raise UserError(self.env._('Uma UC com resultado não se elimina.'))

    def unlink(self):
        pairs = [(registration, registration.class_id) for registration in self if not registration.is_equivalence]
        for registration, edu_class in pairs:
            registration._unsync_enrollment(edu_class)
        return super().unlink()

    @api.model
    def _edu_credit_equivalence(self, enrollment, subject, grade, note=False):
        """Credita uma UC do plano aprovada noutra instituição ou curso (transferência, migração): fica aprovada com
        a nota, sem frequência nem exames, e não entra nas listas da turma. Só a direcção."""
        if not self.env.su and not self.env.user.has_group('edu_core.group_edu_manager'):
            raise AccessError(self.env._('Só a direcção credita UCs por equivalência.'))
        if not 10 <= grade <= 20:
            raise ValidationError(self.env._('A UC creditada tem nota de aprovação (10 a 20).'))
        with trusted(self.env):
            registration = self.with_context(edu_uc_generate=True).create(
                {'enrollment_id': enrollment.id, 'subject_id': subject.id, 'is_equivalence': True, 'note': note}
            )
            registration.write(
                {
                    'state': 'passed',
                    'final_grade': grade,
                    'has_final': True,
                    'result_source': 'equivalence',
                    'frequency_status': 'exempt',
                }
            )
        # O que estava bloqueado por esta precedência entra agora.
        if enrollment.state in SEAT_STATES:
            enrollment._edu_uc_generate()
        return registration

    def action_drop(self):
        """Anula a inscrição na UC: sai das listas da turma; conta como inscrição e fica por aprovar."""
        for registration in self.filtered(lambda r: r.state == 'enrolled'):
            registration._unsync_enrollment(registration.class_id)
            with trusted(self.env):
                registration.state = 'dropped'
            registration.enrollment_id.message_post(
                body=self.env._('Inscrição anulada na UC %s.', registration.subject_id.name)
            )
        return True

    # ------------------------------------------------------------------
    # Ligação às disciplinas da matrícula (notas, chamada, pautas)
    # ------------------------------------------------------------------
    def _sync_enrollment(self):
        self.ensure_one()
        enrollment = self.enrollment_id.with_context(edu_enrollment_reseed=True)
        with trusted(self.env):
            if self.class_id and self.class_id != enrollment.class_id:
                exists = enrollment.lower_subject_ids.filtered(lambda line: line.subject_id == self.subject_id)
                if not exists:
                    self.env['edu.enrollment.lower.subject'].create(
                        {
                            'enrollment_id': enrollment.id,
                            'subject_id': self.subject_id.id,
                            'class_id': self.class_id.id,
                            'reason': self.env._('UC em atraso'),
                        }
                    )
            elif self.subject_id not in enrollment.subject_ids:
                enrollment.subject_ids |= self.subject_id

    def _unsync_enrollment(self, edu_class):
        self.ensure_one()
        enrollment = self.enrollment_id.with_context(edu_enrollment_reseed=True)
        if self.subject_id in enrollment._edu_locked_subjects():
            raise UserError(self.env._('%s já tem notas lançadas: não sai da matrícula.', self.subject_id.name))
        with trusted(self.env):
            enrollment.lower_subject_ids.filtered(
                lambda line: line.subject_id == self.subject_id and line.class_id == edu_class
            ).unlink()
            if self.subject_id in enrollment.subject_ids:
                enrollment.subject_ids -= self.subject_id

    # ------------------------------------------------------------------
    # Avaliação
    # ------------------------------------------------------------------
    def _check_exam_entry(self, vals):
        """O exame normal é dos admitidos; o recurso, de quem não aprovou (e, se o regulamento deixar, dos excluídos);
        a melhoria, de quem aprovou. As notas de exame vão de 0 a 20."""
        self.ensure_one()
        for name in EXAMS:
            if vals.get(name) and not 0 <= vals[name] <= 20:
                raise ValidationError(self.env._('As notas de exame vão de 0 a 20.'))
        if self.state == 'dropped':
            raise UserError(self.env._('A inscrição em %s foi anulada.', self.subject_id.name))
        if is_marked(self.env):
            return  # as pautas das sessões de exame (o servidor sabe quem foi convocado)
        status = self.frequency_status
        if vals.get('has_exam_normal') and status != 'admitted':
            raise UserError(self.env._('Só os admitidos fazem o exame normal de %s.', self.subject_id.name))
        if vals.get('has_exam_appeal'):
            excluded_ok = status == 'excluded' and self._regulation().appeal_for_excluded
            if status != 'admitted' and not excluded_ok:
                raise UserError(self.env._('O recurso de %s não é para esta situação.', self.subject_id.name))
        if vals.get('has_exam_improvement') and self.state != 'passed':
            raise UserError(self.env._('A melhoria é de uma UC aprovada.'))

    def _period(self):
        """O período lectivo onde a UC termina (a anual, no 2.º semestre)."""
        self.ensure_one()
        number = 2 if self.semester == 'annual' else int(self.semester or 1)
        return self.academic_year_id.trimester_ids.filtered(lambda t: t.number == number)[:1]

    def _frequency_items(self):
        grades = (
            self.env['edu.grade']
            .sudo()
            .search(
                [
                    ('enrollment_id', '=', self.enrollment_id.id),
                    ('subject_id', '=', self.subject_id.id),
                    ('class_id', '=', self.class_id.id),
                    ('assessment_type', 'in', ASSESSMENT_TYPES),
                    ('graded', '=', True),
                ]
            )
        )
        return [
            (grade.score * 20 / (grade.assessment_id.max_score or 20), grade.assessment_id.weight or 0)
            for grade in grades
        ]

    def _attendance(self):
        """% de presenças nas aulas dadas da UC (as faltas justificadas não contam contra); None sem aulas."""
        lines = (
            self.env['edu.lesson.attendance']
            .sudo()
            .search(
                [
                    ('enrollment_id', '=', self.enrollment_id.id),
                    ('subject_id', '=', self.subject_id.id),
                    ('class_id', '=', self.class_id.id),
                    ('lesson_state', '=', 'done'),
                ]
            )
        )
        if not lines:
            return None
        return 100 * len(lines.filtered(lambda line: line.state != 'absent')) / len(lines)

    def _edu_uc_refresh(self):
        """Recalcula a MF, a situação e a nota final; a situação na UC fecha com o período (a nota de exame decide
        logo)."""
        for registration in self.filtered(lambda r: r.state != 'dropped' and not r.is_equivalence):
            rules = registration._regulation()._rules()
            mf = frequency_mark(registration._frequency_items())
            attendance = registration._attendance()
            exams = {
                name.removeprefix('exam_'): registration[name] if registration[f'has_{name}'] else None
                for name in EXAMS
            }
            outcome = resolve(rules, mf, attendance, **exams)
            if registration.curriculum_line_id.is_final_work:
                outcome = registration._final_work_outcome(rules, outcome)
            decided = outcome.source and (outcome.source != 'frequency' or registration._period().state == 'closed')
            vals = {
                'frequency_mark': mf or 0,
                'has_frequency_mark': mf is not None,
                'attendance_rate': attendance or 0,
                'has_attendance': attendance is not None,
                'frequency_status': outcome.status,
                'final_grade': outcome.final or 0,
                'has_final': outcome.final is not None,
                'result_source': outcome.source or False,
                'state': ('passed' if outcome.passed else 'failed') if decided else 'enrolled',
            }
            changed = {key: value for key, value in vals.items() if registration[key] != value}
            if changed:
                with trusted(self.env):
                    registration.write(changed)

    def _final_work_outcome(self, rules, outcome):
        """A UC do trabalho final tem a nota da defesa (TFC ou dissertação), não a da frequência."""
        project = (
            self.env['edu.final.project']
            .sudo()
            .search(
                [
                    ('student_id', '=', self.student_id.id),
                    ('enrollment_id', '=', self.enrollment_id.id),
                    ('state', 'in', ('passed', 'failed')),
                ],
                limit=1,
            )
        )
        if not project:
            return Outcome(outcome.status, None, False, '')
        final = round_grade(project.grade, rules.rounding)
        return Outcome(outcome.status, final, final >= rules.pass_grade, 'final_work')

    @api.model
    def _edu_uc_refresh_keys(self, pairs):
        """Recalcula as inscrições de [(matrícula, UC)] (notas lançadas ou apagadas)."""
        domain = [('enrollment_id', 'in', list({e for e, _s in pairs}))]
        registrations = self.sudo().search(domain).filtered(lambda r: (r.enrollment_id.id, r.subject_id.id) in pairs)
        registrations._edu_uc_refresh()
