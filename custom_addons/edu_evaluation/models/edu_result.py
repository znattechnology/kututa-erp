from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools import grading
from ..tools.grading import TECHNICAL


class EduCurriculumLine(models.Model):
    _inherit = 'edu.curriculum.line'

    has_global_exam = fields.Boolean(
        string='Prova global',
        compute='_compute_has_global_exam',
        store=True,
        readonly=False,
        help='Técnico: só disciplinas com 3 ou mais tempos semanais, fora da componente técnica/prática e das práticas '
        '(Despacho 60/08, art. 18.º).',
    )

    @api.depends('weekly_hours', 'component', 'subject_id')
    def _compute_has_global_exam(self):
        for line in self:
            line.has_global_exam = grading.has_global_exam(
                line.weekly_hours, line.component, line.subject_id.name, line.subject_id.code
            )


class EduTermResult(models.Model):
    """Linha da mini-pauta: média das avaliações contínuas, prova trimestral e média do trimestre."""

    _name = 'edu.term.result'
    _description = 'Resultado do trimestre'
    _order = 'class_id, subject_id, trimester_id, order_number'
    _check_company_auto = True

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True, ondelete='cascade', index=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True)
    order_number = fields.Integer(related='enrollment_id.order_number', store=True, string='N.º', aggregator=False)
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True, index=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True, index=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, index=True)
    trimester_id = fields.Many2one('edu.trimester', string='Trimestre', required=True, index=True)
    trimester_number = fields.Integer(
        related='trimester_id.number', store=True, string='Trimestre n.º', aggregator=False
    )
    mac = fields.Float(
        string='MAC / NPP',
        digits=(4, 2),
        aggregator='avg',
        help='Média das avaliações contínuas (geral) ou NPP (técnico).',
    )
    npt = fields.Float(string='Prova trimestral', digits=(4, 2), aggregator='avg')
    mt = fields.Float(string='Média do trimestre', digits=(4, 2), aggregator='avg')
    has_mac = fields.Boolean()
    has_npt = fields.Boolean()
    has_mt = fields.Boolean(string='Com média')

    _key_uniq = models.Constraint(
        'UNIQUE(enrollment_id, subject_id, trimester_id)', 'Já existe o resultado deste trimestre.'
    )

    @api.model
    def _recompute_keys(self, keys):
        """Recalcula os trimestres das disciplinas tocadas, por ordem (a MT3 das classes de exame depende das
        anteriores), e depois o resultado anual."""
        Grade = self.env['edu.grade'].sudo()
        pairs = {(enrollment_id, subject_id) for enrollment_id, subject_id, _trimester_id in keys}
        for enrollment_id, subject_id in pairs:
            enrollment = self.env['edu.enrollment'].sudo().browse(enrollment_id)
            subject = self.env['edu.subject'].browse(subject_id)
            for trimester in enrollment.academic_year_id.trimester_ids.sorted('number'):
                grades = Grade.search(
                    [
                        ('enrollment_id', '=', enrollment_id),
                        ('subject_id', '=', subject_id),
                        ('trimester_id', '=', trimester.id),
                        ('graded', '=', True),
                    ]
                )
                values = self._compute_values(enrollment, subject, trimester, grades)
                result = self.sudo().search(
                    [
                        ('enrollment_id', '=', enrollment_id),
                        ('subject_id', '=', subject_id),
                        ('trimester_id', '=', trimester.id),
                    ]
                )
                if result:
                    result.write(values)
                elif values['has_mac'] or values['has_npt'] or values['has_mt']:
                    self.sudo().create(
                        {
                            'enrollment_id': enrollment_id,
                            'subject_id': subject_id,
                            'trimester_id': trimester.id,
                            **values,
                        }
                    )
        self.env['edu.subject.result']._recompute_keys(pairs)

    def _compute_values(self, enrollment, subject, trimester, grades):
        policy = self.env['edu.evaluation.policy']._get(enrollment.company_id, enrollment.class_id.level_id)
        round_fn = grading.rounder(policy.rounding)
        scale = policy.scale_max

        def score(grade):
            return grading.normalise(grade.score, grade.assessment_id.max_score, scale)

        continuous = grades.filtered(lambda g: g.assessment_type == 'continuous')
        tests = grades.filtered(lambda g: g.assessment_type == 'trimester_test')
        if policy.regime == TECHNICAL:
            mac = grading.mean([score(g) for g in continuous])  # NPP: média simples
        else:
            mac = grading.weighted_mean([(score(g), g.assessment_id.weight) for g in continuous])
        npt = score(tests[:1]) if tests else None
        if policy.regime == TECHNICAL:
            mt = grading.technical_ct(mac, npt, round_fn)
        else:
            last = enrollment.academic_year_id.trimester_ids.sorted('number')[-1:]
            if policy._is_exam_class(enrollment.class_number) and trimester == last:
                previous = self.sudo().search(
                    [
                        ('enrollment_id', '=', enrollment.id),
                        ('subject_id', '=', subject.id),
                        ('trimester_id', '!=', trimester.id),
                        ('has_mt', '=', True),
                    ]
                )
                mt = grading.exam_class_mt3(previous.mapped('mt'), mac, round_fn)
            else:
                mt = grading.general_mt(mac, npt, policy.mac_weight, round_fn)
        return {
            'mac': mac or 0.0,
            'npt': npt or 0.0,
            'mt': mt or 0.0,
            'has_mac': mac is not None,
            'has_npt': npt is not None,
            'has_mt': mt is not None,
        }


class EduSubjectResult(models.Model):
    """Linha da pauta anual: médias dos trimestres, CF, prova global, exame nacional, bonificação do conselho,
    classificação do ano e classificação final da disciplina."""

    _name = 'edu.subject.result'
    _description = 'Resultado anual da disciplina'
    _inherit = ['mail.thread']
    _order = 'class_id, order_number, subject_id'
    _check_company_auto = True

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True, ondelete='cascade', index=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, index=True)
    order_number = fields.Integer(related='enrollment_id.order_number', store=True, string='N.º', aggregator=False)
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id', store=True, index=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True, index=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, index=True)
    subject_code = fields.Char(related='subject_id.code')
    mt1 = fields.Float(string='1.º T', digits=(4, 2), aggregator='avg')
    mt2 = fields.Float(string='2.º T', digits=(4, 2), aggregator='avg')
    mt3 = fields.Float(string='3.º T', digits=(4, 2), aggregator='avg')
    trimesters_graded = fields.Integer(string='Trimestres com média', aggregator=False)
    cf = fields.Float(
        string='CF / MFD',
        digits=(4, 2),
        aggregator='avg',
        help='Técnico: classificação de frequência (cumulativa). Geral: média final.',
    )
    imported_cf = fields.Float(
        string='CF importada', digits=(4, 2), aggregator='avg', help='Classificação anual assinada (migração).'
    )
    has_imported_cf = fields.Boolean(string='Com CF importada')
    has_global_exam = fields.Boolean(string='Com prova global')
    pg = fields.Float(string='PG', digits=(4, 2), aggregator='avg')
    has_pg = fields.Boolean()
    national = fields.Float(string='EN', digits=(4, 2), aggregator='avg', help='Exame nacional.')
    has_national = fields.Boolean()
    annual = fields.Float(
        string='Classificação do ano', digits=(4, 2), aggregator='avg', help='CA (técnico), MFD ou MFED (geral).'
    )
    council_points = fields.Integer(string='Bonificação', readonly=True, tracking=True, aggregator=False)
    council_source = fields.Selection(
        [('teacher', 'Professor'), ('council', 'Conselho de turma')], string='Bonificação dada por', readonly=True
    )
    special_exam = fields.Float(string='Exame especial', digits=(4, 2), aggregator='avg', readonly=True)
    has_special_exam = fields.Boolean(readonly=True)
    final = fields.Float(string='Classificação final', digits=(4, 2), aggregator='avg', tracking=True)
    cfd = fields.Float(
        string='CFD',
        digits=(4, 2),
        aggregator='avg',
        help='Disciplina plurianual: média das classificações anuais, no último ano.',
    )
    terminal_subject = fields.Boolean(string='Último ano da disciplina')
    complete = fields.Boolean(string='Completa')
    passed = fields.Boolean(string='Aprovado')
    pass_grade = fields.Float(compute='_compute_display_flags')
    borderline = fields.Boolean(string='Caso limite', compute='_compute_display_flags')

    _key_uniq = models.Constraint('UNIQUE(enrollment_id, subject_id)', 'Já existe o resultado anual desta disciplina.')

    @api.depends('final', 'annual', 'council_points')
    def _compute_display_flags(self):
        for result in self:
            policy = result._policy()
            result.pass_grade = policy.pass_grade
            base = result.annual
            result.borderline = (
                result.complete and policy.pass_grade - 2 <= base < policy.pass_grade and not result.council_points
            )

    def _policy(self):
        self.ensure_one()
        return self.env['edu.evaluation.policy']._get(self.company_id or self.env.company, self.class_id.level_id)

    @api.model
    def _recompute_keys(self, keys):
        for enrollment_id, subject_id in keys:
            result = self.sudo().search([('enrollment_id', '=', enrollment_id), ('subject_id', '=', subject_id)])
            if not result:
                result = self.sudo().create({'enrollment_id': enrollment_id, 'subject_id': subject_id})
            result._recompute()

    def _recompute(self):
        Term = self.env['edu.term.result'].sudo()
        Grade = self.env['edu.grade'].sudo()
        for result in self:
            enrollment = result.enrollment_id
            policy = result._policy()
            round_fn = grading.rounder(policy.rounding)
            trimesters = enrollment.academic_year_id.trimester_ids.sorted('number')
            terms = Term.search([('enrollment_id', '=', enrollment.id), ('subject_id', '=', result.subject_id.id)])
            mts = []
            for trimester in trimesters:
                term = terms.filtered(lambda t, tr=trimester: t.trimester_id == tr and t.has_mt)
                mts.append(term.mt if term else None)
            graded = len([mt for mt in mts if mt is not None])
            imported = result.imported_cf if result.has_imported_cf else None
            line = enrollment.class_id.subject_line_ids.filtered(
                lambda line, s=result.subject_id: line.subject_id == s
            )[:1]
            vals = {
                'mt1': mts[0] or 0.0 if len(mts) > 0 else 0.0,
                'mt2': mts[1] or 0.0 if len(mts) > 1 else 0.0,
                'mt3': mts[2] or 0.0 if len(mts) > 2 else 0.0,
                'trimesters_graded': graded,
                'has_global_exam': bool(line.has_global_exam) and policy.regime == TECHNICAL,
            }
            last = trimesters[-1:]
            final_grades = Grade.search(
                [
                    ('enrollment_id', '=', enrollment.id),
                    ('subject_id', '=', result.subject_id.id),
                    ('trimester_id', 'in', last.ids),
                    ('assessment_type', 'in', ('global_exam', 'national_exam')),
                    ('graded', '=', True),
                ]
            )
            pg = final_grades.filtered(lambda g: g.assessment_type == 'global_exam')[:1]
            national = final_grades.filtered(lambda g: g.assessment_type == 'national_exam')[:1]
            pg_value = round_fn(pg.score) if pg else None
            national_value = national.score if national else None
            if policy.regime == TECHNICAL:
                precise = grading.frequency_classification(mts, TECHNICAL, (lambda v: v), imported)
                cf = grading.frequency_classification(mts, TECHNICAL, round_fn, imported)
                base_cf = precise if policy.technical_ca_precise else cf
                annual = grading.technical_ca(base_cf, pg_value, vals['has_global_exam'], round_fn, policy.cf_weight)
            else:
                cf = grading.frequency_classification(mts, 'general', round_fn, imported)
                annual = cf
                if policy._is_exam_class(enrollment.class_number) and result.subject_id.is_national_exam:
                    # MFED a partir da MT3 (Anexo III, n.os 6 e 7), só com as três médias.
                    annual = (
                        grading.national_final(
                            mts[-1] if mts else None,
                            national_value,
                            policy._national_weight(enrollment.class_number),
                            round_fn,
                        )
                        if national_value is not None and graded == len(trimesters)
                        else cf
                    )
            complete = imported is not None or (graded >= len(trimesters) and annual is not None)
            adjusted = grading.with_adjustment(annual, result.council_points, policy.scale_max)
            # O resultado do exame especial (já com a regra da melhoria) substitui a classificação do ano.
            final = result.special_exam if result.has_special_exam else adjusted
            span, terminal = result._subject_span()
            cfd = final
            if len(span) > 1:
                previous = self.sudo().search(
                    [
                        ('student_id', '=', enrollment.student_id.id),
                        ('subject_id', '=', result.subject_id.id),
                        ('id', '!=', result.id),
                        ('complete', '=', True),
                        ('academic_year_id.date_start', '<', enrollment.academic_year_id.date_start),
                    ]
                )
                cfd = grading.multi_year_final([*previous.mapped('final'), final], round_fn) if terminal else None
            vals.update(
                {
                    'cf': cf or 0.0,
                    'pg': pg_value or 0.0,
                    'has_pg': pg_value is not None,
                    'national': national_value or 0.0,
                    'has_national': national_value is not None,
                    'annual': annual or 0.0,
                    'final': final or 0.0,
                    'cfd': cfd or 0.0,
                    'terminal_subject': terminal,
                    'complete': complete,
                    'passed': complete and final is not None and final >= policy.pass_grade,
                }
            )
            result.write(vals)

    def _subject_span(self):
        """Classes do plano em que a disciplina é leccionada e se esta turma é a última delas."""
        self.ensure_one()
        edu_class = self.enrollment_id.class_id
        lines = edu_class.curriculum_id.line_ids.filtered(lambda line: line.subject_id == self.subject_id)
        span = sorted(set(lines.mapped('year_id.class_number')))
        terminal = not span or edu_class.class_number >= span[-1]
        return span, terminal

    # ------------------------------------------------------------------
    # Bonificação do professor (caso limite: 8 ou 9 valores)
    # ------------------------------------------------------------------
    def _check_council_open(self):
        session = (
            self.env['edu.council.session']
            .sudo()
            .search([('class_id', '=', self.class_id.id), ('state', '=', 'realized')], limit=1)
        )
        if session:
            raise UserError(self.env._('O conselho de turma já foi realizado: a pauta não se altera.'))

    def _set_points(self, points, source, vote=None):
        self.ensure_one()
        self._check_council_open()
        if points and not self.borderline:
            raise UserError(self.env._('Só se bonifica um caso limite (até 2 valores abaixo da aprovação).'))
        self.sudo().write({'council_points': points, 'council_source': source if points else False})
        self._recompute()

    def action_grant_one(self):
        self._grant_by_teacher(1)

    def action_grant_two(self):
        self._grant_by_teacher(2)

    def _grant_by_teacher(self, points):
        for result in self:
            if not self.env.user.has_group('edu_core.group_edu_user'):
                employee = self.env.user.employee_id
                assigned = (
                    self.env['edu.teaching.assignment']
                    .sudo()
                    .search_count(
                        [
                            ('class_id', '=', result.class_id.id),
                            ('subject_id', '=', result.subject_id.id),
                            ('teacher_id', '=', employee.id),
                        ]
                    )
                )
                if not assigned:
                    raise UserError(self.env._('Só o professor da disciplina bonifica a sua nota.'))
            result._set_points(points, 'teacher')
        return True

    def action_council_vote(self):
        """O director de turma abre a votação de +2 valores para este caso limite."""
        self.ensure_one()
        session = self.env['edu.council.session'].search([('class_id', '=', self.class_id.id)], limit=1)
        if not session:
            session = self.env['edu.council.session'].create({'class_id': self.class_id.id})
        vote = session.action_open_vote(self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.council.vote',
            'res_id': vote.id,
            'view_mode': 'form',
        }

    def action_remove_points(self):
        for result in self:
            result._check_council_open()
            vote = (
                self.env['edu.council.vote'].sudo().search([('result_id', '=', result.id), ('state', '=', 'applied')])
            )
            vote.write({'state': 'cancelled'})
            result.sudo().write({'council_points': 0, 'council_source': False})
            result._recompute()
        return True
