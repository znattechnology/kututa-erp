from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..tools import grading

STATUSES = [
    ('pending', 'Pendente'),
    ('promoted', 'Transita'),
    ('graduated', 'Concluiu'),
    ('conditional', 'Transita com disciplinas em atraso'),
    ('exam', 'Admitido a exame de recurso'),
    ('retained', 'Retido'),
]
ENROLLED = ('active', 'irregular')


class EduYearResult(models.Model):
    """Resultado do ano do aluno: média, negativas e decisão de transição (automática ou manual)."""

    _name = 'edu.year.result'
    _description = 'Resultado do ano lectivo'
    _inherit = ['mail.thread']
    _order = 'class_id, order_number'
    _check_company_auto = True

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True, ondelete='cascade', index=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, index=True)
    order_number = fields.Integer(related='enrollment_id.order_number', store=True, string='N.º', aggregator=False)
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id', store=True, index=True)
    level_id = fields.Many2one(related='class_id.level_id', store=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True, index=True)
    average = fields.Float(string='Média', digits=(4, 2), aggregator='avg')
    negative_count = fields.Integer(string='Negativas')
    negative_subject_ids = fields.Many2many('edu.subject', string='Disciplinas negativas')
    absence_excluded = fields.Boolean(string='Reprovado por faltas')
    attendance_rate = fields.Float(string='Frequência', digits=(4, 3))
    status = fields.Selection(STATUSES, string='Decisão', default='pending', required=True, tracking=True)
    reason = fields.Char(string='Fundamento')
    manual = fields.Boolean(string='Decisão manual', readonly=True, tracking=True)
    decided_by_id = fields.Many2one('res.users', string='Decidida por', readonly=True)
    note = fields.Text(string='Observações')
    retention_count = fields.Integer(string='Retenções no nível', readonly=True, aggregator=False)
    requires_review = fields.Boolean(string='Exige decisão da direcção', readonly=True)
    requirement_ids = fields.One2many('edu.exam.requirement', 'year_result_id', string='Exames')
    pending_exam_count = fields.Integer(string='Exames por realizar', compute='_compute_pending_exam_count')

    _enrollment_uniq = models.Constraint('UNIQUE(enrollment_id)', 'O aluno já tem resultado neste ano.')

    @api.depends('requirement_ids.state')
    def _compute_pending_exam_count(self):
        for result in self:
            result.pending_exam_count = len(result.requirement_ids.filtered(lambda r: r.state == 'pending'))

    def _policy(self):
        self.ensure_one()
        return self.env['edu.evaluation.policy']._get(self.company_id, self.level_id)

    @api.model
    def _compute_for_classes(self, classes):
        results = self.browse()
        for edu_class in classes:
            enrollments = edu_class.enrollment_ids.filtered(lambda e: e.state in ENROLLED + ('completed', 'retained'))
            if not enrollments:
                raise UserError(self.env._('A turma %s não tem alunos matriculados.', edu_class.display_name))
            excluded = edu_class._edu_absence_exclusions()
            for enrollment in enrollments:
                result = self.sudo().search([('enrollment_id', '=', enrollment.id)]) or self.sudo().create(
                    {'enrollment_id': enrollment.id}
                )
                result._decide(excluded_absence=enrollment in excluded)
                results |= result
        return results

    def _attendance(self):
        """Frequência do ano (presenças e atrasos sobre as aulas dadas com chamada); None sem chamadas."""
        self.ensure_one()
        lines = (
            self.env['edu.lesson.attendance']
            .sudo()
            .search([('enrollment_id', '=', self.enrollment_id.id), ('lesson_state', '=', 'done')])
        )
        if not lines:
            return None
        return len(lines.filtered(lambda line: line.state in ('present', 'late'))) / len(lines)

    def _decide(self, excluded_absence=False):
        Subject = self.env['edu.subject.result'].sudo()
        for result in self:
            if result.manual:
                continue  # uma decisão manual nunca é sobreposta
            enrollment = result.enrollment_id
            policy = result._policy()
            # A disciplina anulada (Decreto Executivo 60/08, art. 11.º) não conta para a decisão.
            subjects = enrollment.subject_ids - enrollment._dropped_subjects()
            if policy.regime != 'preschool':
                # As médias dos trimestres abertos refazem-se com o regime actual (pesos, arredondamento); as dos
                # trimestres fechados são as da pauta afixada.
                open_grades = (
                    self.env['edu.grade']
                    .sudo()
                    .search(
                        [
                            ('enrollment_id', '=', enrollment.id),
                            ('trimester_id.state', '=', 'open'),
                            ('graded', '=', True),
                        ]
                    )
                )
                if open_grades:
                    self.env['edu.term.result'].sudo()._recompute_keys(open_grades._result_keys())
                Subject._recompute_keys({(enrollment.id, subject.id) for subject in subjects})
            subject_results = Subject.search(
                [('enrollment_id', '=', enrollment.id), ('subject_id', 'in', subjects.ids)]
            )
            # As disciplinas sem professor não contam para as negativas (resumo do regime, IV.6).
            taught = (
                enrollment.class_id.assignment_ids.subject_id or subjects
            ) | enrollment.lower_subject_ids.subject_id
            counted = subject_results.filtered(lambda r, taught=taught: r.subject_id in taught)
            complete = bool(counted) and all(counted.mapped('complete')) and len(counted) == len(subjects & taught)
            finals = {r.subject_id.code or str(r.subject_id.id): r.final for r in counted if r.complete}
            # As negativas contam pela nota para a transição (no técnico, a CFD das disciplinas que terminam aqui).
            averages = {r.subject_id.code or str(r.subject_id.id): r.transition_grade for r in counted if r.complete}
            technical = policy.regime == grading.TECHNICAL
            if technical:
                # Despacho 60/08, art. 30.º e 31.º, n.º 2: as negativas das disciplinas terminais das classes
                # anteriores ainda por recuperar também contam para o máximo de duas.
                for prior in result._prior_terminal_negatives():
                    code = prior.subject_id.code or str(prior.subject_id.id)
                    averages[f'{code} ({prior.class_id.class_number}ª)'] = prior.transition_grade
            rate = result._attendance()
            low_attendance = bool(policy.min_attendance and rate is not None and rate < policy.min_attendance)
            rules = policy._rules(enrollment.class_id)
            structuring = [code.strip() for code in (policy.structuring_codes or '').split(',') if code.strip()]
            decision = grading.decide(
                averages, rules, complete=complete or policy.regime == 'preschool',
                excluded_absence=excluded_absence, low_attendance=low_attendance,
            )  # fmt: skip
            if (
                decision.status not in (grading.RETAINED, grading.PENDING)
                and len(structuring) >= 2
                and all(code in decision.negatives for code in structuring)
            ):
                decision = grading.Decision(grading.RETAINED, decision.negatives, 'Negativa em todas as estruturantes')
            ungraded = result._ungraded_subjects(counted) if technical else counted.browse()
            if ungraded and decision.status != grading.RETAINED:
                # Resumo do regime (técnico), IV.7: sem classificação em dois trimestres, sem aproveitamento no ano.
                codes = [r.subject_id.code or str(r.subject_id.id) for r in ungraded]
                decision = grading.Decision(grading.RETAINED, codes, 'Sem classificação em dois trimestres')
            codes = set(decision.negatives)
            negatives = counted.filtered(lambda r, codes=codes: (r.subject_id.code or str(r.subject_id.id)) in codes)
            prior = result._prior_retentions()
            average = grading.mean(list(finals.values()))
            values = {
                'average': grading.rounder(policy.rounding)(average) if average is not None else 0.0,
                'negative_count': len(decision.negatives),
                'negative_subject_ids': [fields.Command.set(negatives.subject_id.ids)],
                'absence_excluded': excluded_absence,
                'attendance_rate': rate or 0.0,
                'status': decision.status,
                'reason': decision.reason,
                'retention_count': prior + (1 if decision.status == grading.RETAINED else 0),
                'requires_review': decision.status == grading.RETAINED
                and policy.regime != 'primary'
                and prior + 1 > policy.max_retentions,
            }
            result.write(values)
            # Os exames por realizar que a decisão já não pede saem (os realizados ficam no histórico).
            wanted = {grading.CONDITIONAL: 'extraordinary', grading.EXAM: 'resit'}.get(decision.status)
            result.requirement_ids.filtered(
                lambda r, w=wanted, n=negatives.subject_id: (
                    r.state == 'pending' and r.kind != 'improvement' and (r.kind != w or r.subject_id not in n)
                )
            ).sudo().unlink()
            if decision.status in (grading.CONDITIONAL, grading.EXAM):
                kind = 'extraordinary' if decision.status == grading.CONDITIONAL else 'resit'
                for subject_result in negatives:
                    if not result.requirement_ids.filtered(lambda r, s=subject_result: r.subject_id == s.subject_id):
                        self.env['edu.exam.requirement'].sudo().create(
                            {'year_result_id': result.id, 'subject_result_id': subject_result.id, 'kind': kind}
                        )

    def _prior_terminal_negatives(self):
        """Disciplinas terminais negativas de classes anteriores do mesmo nível, em anos em que o aluno transitou
        (nos anos de que ficou retido, repete a classe e as disciplinas)."""
        self.ensure_one()
        progressed = self.sudo().search(
            [
                ('student_id', '=', self.student_id.id),
                ('level_id', '=', self.level_id.id),
                ('status', 'in', ('promoted', 'conditional')),
                ('id', '!=', self.id),
                ('academic_year_id.date_start', '<', self.academic_year_id.date_start),
            ]
        )
        if not progressed:
            return self.env['edu.subject.result']
        policy = self._policy()
        return (
            self.env['edu.subject.result']
            .sudo()
            .search(
                [
                    ('enrollment_id', 'in', progressed.enrollment_id.ids),
                    ('terminal_subject', '=', True),
                    ('complete', '=', True),
                    ('transition_grade', '<', policy.pass_grade),
                ]
            )
        )

    def _ungraded_subjects(self, subject_results):
        """Disciplinas sem classificação em dois ou mais trimestres, depois de fechado o último trimestre (as que só
        têm a classificação anual importada não contam)."""
        self.ensure_one()
        trimesters = self.academic_year_id.trimester_ids.sorted('number')
        if not trimesters or trimesters[-1].state != 'closed':
            return subject_results.browse()
        return subject_results.filtered(lambda r: not r.has_imported_cf and r.trimesters_graded <= len(trimesters) - 2)

    def _prior_retentions(self):
        """Retenções anteriores do aluno no mesmo nível de ensino."""
        self.ensure_one()
        return self.sudo().search_count(
            [
                ('student_id', '=', self.student_id.id),
                ('level_id', '=', self.level_id.id),
                ('status', '=', 'retained'),
                ('id', '!=', self.id),
                ('academic_year_id.date_start', '<', self.academic_year_id.date_start),
            ]
        )

    def action_recompute(self):
        for result in self:
            excluded = result.class_id._edu_absence_exclusions()
            result._decide(excluded_absence=result.enrollment_id in excluded)
        return True

    def _set_manual(self, status):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('Só a direcção decide manualmente a transição.'))
        self.write({'status': status, 'manual': True, 'decided_by_id': self.env.uid, 'requires_review': False})
        # Com o ano já fechado, a matrícula acompanha a decisão (a confirmação de matrículas lê-a).
        for result in self.sudo():
            enrollment = result.enrollment_id
            if enrollment.state in ('completed', 'retained'):
                enrollment.state = 'retained' if status == 'retained' else 'completed'
        return True

    def action_manual_promote(self):
        # Numa classe terminal, transitar é concluir.
        terminal = self[:1]._policy()._rules(self[:1].class_id).terminal if self else False
        return self._set_manual('graduated' if terminal else 'promoted')

    def action_manual_retain(self):
        return self._set_manual('retained')

    def action_reset_automatic(self):
        self.write({'manual': False, 'decided_by_id': False})
        return self.action_recompute()

    def _after_exams(self):
        """Resolvidos os exames de recurso, a decisão volta a correr com as notas novas (as mesmas regras da pauta).
        Se ainda pedir exame, já não há outra época: fica retido. O extraordinário e a melhoria não mudam a decisão
        do ano em que o aluno transitou (DE 424/25, art. 25.º: o efeito é na matrícula seguinte)."""
        for result in self.filtered(lambda r: r.requirement_ids and not r.pending_exam_count and not r.manual):
            if result.status != 'exam':
                continue
            excluded = result.class_id._edu_absence_exclusions()
            result._decide(excluded_absence=result.enrollment_id in excluded)
            if result.status == 'exam':
                result.write({'status': 'retained'})
            result.reason = self.env._('Depois dos exames: %s', result.reason or '')


class EduExamRequirement(models.Model):
    """Disciplina que o aluno tem de fazer em exame especial: recurso, extraordinário (atraso) ou melhoria."""

    _name = 'edu.exam.requirement'
    _description = 'Exame especial'
    _order = 'year_result_id, subject_id'
    _check_company_auto = True

    year_result_id = fields.Many2one('edu.year.result', string='Resultado do ano', required=True, ondelete='cascade')
    subject_result_id = fields.Many2one(
        'edu.subject.result', string='Disciplina (pauta)', required=True, ondelete='cascade'
    )
    student_id = fields.Many2one(related='year_result_id.student_id', store=True)
    class_id = fields.Many2one(related='year_result_id.class_id', store=True)
    company_id = fields.Many2one(related='year_result_id.company_id', store=True)
    subject_id = fields.Many2one(related='subject_result_id.subject_id', store=True)
    kind = fields.Selection(
        [
            ('resit', 'Recurso'),
            ('extraordinary', 'Extraordinário (disciplina em atraso)'),
            ('improvement', 'Melhoria de nota'),
        ],
        string='Exame',
        required=True,
        default='resit',
    )
    previous = fields.Float(string='Nota anterior', related='subject_result_id.annual')
    score = fields.Float(string='Nota do exame', digits=(4, 2), aggregator='avg')
    resulting = fields.Float(string='Classificação resultante', digits=(4, 2), aggregator='avg', readonly=True)
    passed = fields.Boolean(string='Aprovado', readonly=True)
    state = fields.Selection([('pending', 'Por realizar'), ('done', 'Realizado')], default='pending', required=True)
    date = fields.Date(string='Data')

    def action_record(self):
        """Lança a nota do exame: no recurso e no extraordinário substitui; na melhoria prevalece a mais alta."""
        for requirement in self:
            if requirement.state == 'done':
                raise UserError(self.env._('O exame de %s já foi lançado.', requirement.subject_id.name))
            policy = requirement.year_result_id._policy()
            if not 0 <= requirement.score <= policy.scale_max:
                raise ValidationError(self.env._('A nota vai de 0 a %s.', policy.scale_max))
            round_fn = grading.rounder(policy.rounding)
            exam = round_fn(requirement.score)
            subject_result = requirement.subject_result_id
            previous = subject_result.final if subject_result.complete else None
            resulting = grading.special_exam_result(previous, exam, improvement=requirement.kind == 'improvement')
            requirement.write(
                {
                    'resulting': resulting,
                    'passed': resulting >= policy.pass_grade,
                    'state': 'done',
                    'date': requirement.date or fields.Date.context_today(self),
                }
            )
            subject_result.sudo().write({'special_exam': resulting, 'has_special_exam': True})
            subject_result._recompute()
            # Aprovado pela classificação recalculada (no ano terminal de uma plurianual, a CFD).
            requirement.passed = subject_result.passed
        self.year_result_id._after_exams()
        return True
