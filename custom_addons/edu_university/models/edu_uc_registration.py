from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import import_mode, is_trusted, trusted
from odoo.addons.edu_enrollment.models.edu_enrollment import SEAT_STATES
from odoo.exceptions import AccessError, UserError, ValidationError

from .edu_curriculum import SEMESTERS

STATES = [
    ('enrolled', 'Inscrito'),
    ('passed', 'Aprovado'),
    ('failed', 'Reprovado'),
    ('dropped', 'Anulada'),
]
# Por aprovar: conta como UC em atraso no ano seguinte.
PENDING = ('failed', 'dropped', 'enrolled')


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
        'edu.curriculum.line', string='Linha do plano', compute='_compute_curriculum_line_id', store=True
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
        if not is_trusted(self.env) and enrollments.filtered(lambda e: e.state not in SEAT_STATES):
            raise UserError(self.env._('Só se inscreve em UCs com a matrícula em curso.'))
        registrations = super().create(vals_list)
        for registration in registrations:
            with trusted(self.env):
                registration.attempt = len(registration._previous()) + 1
                registration._sync_enrollment()
        # As regras correm depois do n.º da inscrição (prescrição) e da ligação à turma.
        registrations._check_registration()
        return registrations

    def write(self, vals):
        if 'state' in vals and not is_trusted(self.env):
            raise AccessError(self.env._('A situação na UC resulta da avaliação (ou de «Anular»).'))
        if {'enrollment_id', 'subject_id'} & set(vals) and not is_trusted(self.env):
            raise UserError(self.env._('Para mudar de UC, anule esta inscrição e crie outra.'))
        old_classes = {registration: registration.class_id for registration in self}
        result = super().write(vals)
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
        pairs = [(registration, registration.class_id) for registration in self]
        for registration, edu_class in pairs:
            registration._unsync_enrollment(edu_class)
        return super().unlink()

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
