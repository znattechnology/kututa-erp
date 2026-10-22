from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

ASSESSMENT_TYPES = [
    ('continuous', 'Avaliação contínua'),
    ('trimester_test', 'Prova trimestral'),
    ('global_exam', 'Prova global (técnico)'),
    ('national_exam', 'Exame nacional'),
]
ENROLLED = ('active', 'irregular')


def check_grade_entry(env, edu_class, subject, trimester):
    """Janela de lançamento: trimestre fechado → só por reapreciação; a secretaria lança em qualquer trimestre
    aberto; o professor só na sua disciplina e no trimestre em curso do ano em curso, ou com autorização."""
    if env.context.get('edu_grade_appeal') or env.su:
        return
    if trimester.state == 'closed':
        raise UserError(env._('O %s está fechado: a correcção das notas faz-se por reapreciação.', trimester.name))
    if env.user.has_group('edu_core.group_edu_user'):
        return
    employee = env.user.employee_id
    assigned = (
        env['edu.teaching.assignment']
        .sudo()
        .search_count(
            [('class_id', '=', edu_class.id), ('subject_id', '=', subject.id), ('teacher_id', '=', employee.id)]
        )
    )
    if not employee or not assigned:
        raise AccessError(env._('Só o professor da disciplina lança as notas desta turma.'))
    if trimester.is_current and trimester.academic_year_id.is_current:
        return
    if env['edu.grade.edit.permission']._allows(employee, edu_class, subject, trimester):
        return
    raise AccessError(
        env._(
            'O professor lança notas no trimestre em curso. Para o %s, peça autorização à secretaria.', trimester.name
        )
    )


class EduAssessment(models.Model):
    """Coluna da mini-pauta: uma avaliação de uma disciplina numa turma e trimestre."""

    _name = 'edu.assessment'
    _description = 'Avaliação'
    _inherit = ['mail.thread']
    _order = 'trimester_id, date, id'
    _check_company_auto = True

    name = fields.Char(string='Avaliação', required=True)
    class_id = fields.Many2one('edu.class', string='Turma', required=True, index=True, check_company=True)
    company_id = fields.Many2one(related='class_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='class_id.academic_year_id', store=True, index=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, index=True, check_company=True)
    trimester_id = fields.Many2one(
        'edu.trimester',
        string='Trimestre',
        required=True,
        index=True,
        domain="[('academic_year_id', '=', academic_year_id)]",
    )
    assessment_type = fields.Selection(ASSESSMENT_TYPES, string='Tipo', required=True, default='continuous')
    date = fields.Date(string='Data', default=fields.Date.context_today)
    max_score = fields.Float(
        string='Cotação', compute='_compute_max_score', store=True, readonly=False, precompute=True
    )
    weight = fields.Float(string='Peso', default=1.0, help='Peso na média das avaliações contínuas.')
    grade_ids = fields.One2many('edu.grade', 'assessment_id', string='Notas')
    graded_count = fields.Integer(string='Notas lançadas', compute='_compute_graded_count')

    @api.depends('class_id')
    def _compute_max_score(self):
        for assessment in self:
            if not assessment.max_score:
                assessment.max_score = assessment._policy().scale_max or 20

    @api.depends('grade_ids.graded')
    def _compute_graded_count(self):
        for assessment in self:
            assessment.graded_count = len(assessment.grade_ids.filtered('graded'))

    def _policy(self):
        self.ensure_one()
        return self.env['edu.evaluation.policy']._get(self.class_id.company_id, self.class_id.level_id)

    @api.constrains('class_id', 'subject_id', 'trimester_id', 'assessment_type', 'max_score')
    def _check_assessment(self):
        for assessment in self:
            policy = assessment._policy()
            if policy.regime == 'preschool':
                raise ValidationError(self.env._('Na iniciação a avaliação é qualitativa, pelo RDEC.'))
            if assessment.trimester_id.academic_year_id != assessment.academic_year_id:
                raise ValidationError(self.env._('O trimestre não é do ano lectivo da turma.'))
            subjects = assessment.class_id.subject_line_ids.subject_id
            if subjects and assessment.subject_id not in subjects:
                raise ValidationError(self.env._('%s não faz parte do plano da turma.', assessment.subject_id.name))
            if not 0 < assessment.max_score <= policy.scale_max:
                raise ValidationError(self.env._('A cotação vai até %s valores.', policy.scale_max))
            if assessment.assessment_type == 'global_exam':
                line = assessment.class_id.subject_line_ids.filtered(
                    lambda line, subject=assessment.subject_id: line.subject_id == subject
                )
                # Migração: a PG que a escola lançou entra mesmo fora da regra (fica no relatório).
                if policy.regime != 'technical' or (
                    not line[:1].has_global_exam and not self.env.context.get('edu_global_exam_import')
                ):
                    raise ValidationError(self.env._('%s não tem prova global.', assessment.subject_id.name))
            if assessment.assessment_type == 'national_exam':
                if not policy._is_exam_class(assessment.class_id.class_number):
                    raise ValidationError(self.env._('Só há exame nacional nas classes de exame (6.ª, 9.ª e 12.ª).'))
            if assessment.assessment_type in ('global_exam', 'national_exam'):
                last = assessment.academic_year_id.trimester_ids.sorted('number')[-1:]
                if assessment.trimester_id != last:
                    raise ValidationError(self.env._('A prova global e o exame nacional são do último trimestre.'))

    @api.model_create_multi
    def create(self, vals_list):
        assessments = super().create(vals_list)
        for assessment in assessments:
            check_grade_entry(self.env, assessment.class_id, assessment.subject_id, assessment.trimester_id)
        return assessments

    def write(self, vals):
        for assessment in self:
            check_grade_entry(self.env, assessment.class_id, assessment.subject_id, assessment.trimester_id)
        result = super().write(vals)
        if {'weight', 'max_score', 'assessment_type'} & set(vals):
            self.grade_ids._recompute_results()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_check(self):
        for assessment in self:
            check_grade_entry(self.env, assessment.class_id, assessment.subject_id, assessment.trimester_id)
            if assessment.grade_ids.filtered('graded'):
                raise UserError(self.env._('A avaliação %s já tem notas lançadas.', assessment.name))

    def action_fill_students(self):
        """Uma linha por aluno matriculado na disciplina, pela ordem da pauta."""
        for assessment in self:
            # Os da turma inscritos na disciplina e os de outras turmas que a fazem aqui (Decreto Executivo 60/08).
            enrollments = self.env['edu.enrollment']._for_class_subject(assessment.class_id, assessment.subject_id)
            missing = enrollments - assessment.grade_ids.enrollment_id
            self.env['edu.grade'].create(
                [{'assessment_id': assessment.id, 'enrollment_id': enrollment.id} for enrollment in missing]
            )
        return True


class EduGrade(models.Model):
    _name = 'edu.grade'
    _description = 'Nota'
    _order = 'assessment_id, order_number, id'
    _check_company_auto = True

    assessment_id = fields.Many2one('edu.assessment', string='Avaliação', required=True, ondelete='cascade', index=True)
    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True, index=True, check_company=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, index=True)
    order_number = fields.Integer(related='enrollment_id.order_number', store=True, string='N.º', aggregator=False)
    company_id = fields.Many2one(related='assessment_id.company_id', store=True, index=True)
    class_id = fields.Many2one(related='assessment_id.class_id', store=True, index=True)
    subject_id = fields.Many2one(related='assessment_id.subject_id', store=True, index=True)
    trimester_id = fields.Many2one(related='assessment_id.trimester_id', store=True, index=True)
    assessment_type = fields.Selection(related='assessment_id.assessment_type', store=True)
    score = fields.Float(string='Nota', digits=(4, 2))
    graded = fields.Boolean(string='Lançada', readonly=True, help='A nota foi lançada (0 é uma nota).')
    absent = fields.Boolean(
        string='Faltou', help='Falta injustificada à prova: vale 0 valores (Despacho 60/08, art. 21.º).'
    )
    note = fields.Char(string='Observação')

    _assessment_enrollment_uniq = models.Constraint(
        'UNIQUE(assessment_id, enrollment_id)', 'O aluno já tem nota nesta avaliação.'
    )

    @api.constrains('score', 'assessment_id', 'enrollment_id')
    def _check_score(self):
        for grade in self:
            if grade.score < 0 or grade.score > grade.assessment_id.max_score:
                raise ValidationError(
                    self.env._('A nota vai de 0 a %s (cotação da avaliação).', grade.assessment_id.max_score)
                )
            assessment = grade.assessment_id
            visiting = grade.enrollment_id.lower_subject_ids.filtered(
                lambda line, a=assessment: line.class_id == a.class_id and line.subject_id == a.subject_id
            )
            if grade.enrollment_id.class_id != assessment.class_id and not visiting:
                raise ValidationError(self.env._('%s não é desta turma.', grade.student_id.name))

    def _prepare(self, vals):
        if vals.get('absent'):
            vals = dict(vals, score=0.0, graded=True)
        elif 'score' in vals and 'graded' not in vals:
            vals = dict(vals, graded=vals['score'] is not False and vals['score'] is not None)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prepare(vals) for vals in vals_list]
        grades = super().create(vals_list)
        for assessment in grades.assessment_id:
            check_grade_entry(self.env, assessment.class_id, assessment.subject_id, assessment.trimester_id)
        grades.filtered('graded')._recompute_results()
        return grades

    def write(self, vals):
        for assessment in self.assessment_id:
            check_grade_entry(self.env, assessment.class_id, assessment.subject_id, assessment.trimester_id)
        result = super().write(self._prepare(vals))
        if {'score', 'absent', 'graded'} & set(vals):
            self._recompute_results()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_check(self):
        for assessment in self.assessment_id:
            check_grade_entry(self.env, assessment.class_id, assessment.subject_id, assessment.trimester_id)

    def unlink(self):
        keys = self._result_keys()
        result = super().unlink()
        self.env['edu.term.result']._recompute_keys(keys)
        return result

    def action_clear(self):
        """Apaga a nota lançada (a linha do aluno fica)."""
        self.write({'score': 0.0, 'graded': False, 'absent': False})
        return True

    def _result_keys(self):
        return {(grade.enrollment_id.id, grade.subject_id.id, grade.trimester_id.id) for grade in self}

    def _recompute_results(self):
        if self.env.context.get('edu_defer_results'):
            return  # importação: quem importa recalcula a pauta no fim, uma só vez
        self.env['edu.term.result']._recompute_keys(self._result_keys())
