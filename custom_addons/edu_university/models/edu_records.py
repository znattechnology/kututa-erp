from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import trusted

from ..tools.grading_higher import round_grade


class EduCurriculumLine(models.Model):
    _inherit = 'edu.curriculum.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._edu_flag_final_work()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if vals.get('is_final_work'):
            self._edu_flag_final_work()
        return result

    def _edu_flag_final_work(self):
        """O curso com trabalho final no plano exige-o (o TFC ou a dissertação registam-se como a PAP)."""
        courses = self.filtered('is_final_work').curriculum_id.course_id.filtered(
            lambda c: not c.requires_final_project
        )
        courses.sudo().requires_final_project = True


class EduFinalProject(models.Model):
    """No superior, o trabalho final: TFC na licenciatura (DP 193/18, arts. 47.º e 48.º) ou dissertação no
    mestrado. A nota da defesa é a nota da UC do trabalho final."""

    _inherit = 'edu.final.project'

    edu_kind = fields.Selection(
        [('pap', 'PAP'), ('tfc', 'Trabalho de fim de curso'), ('dissertation', 'Dissertação')],
        string='Tipo',
        compute='_compute_edu_kind',
        store=True,
    )
    co_advisor_id = fields.Many2one('hr.employee', string='Co-orientador(a)', check_company=True)
    external_jury = fields.Char(string='Júri externo', help='Membros do júri de fora da instituição.')
    uc_registration_id = fields.Many2one(
        'edu.uc.registration', string='UC do trabalho final', compute='_compute_uc_registration_id'
    )

    @api.depends('course_id.level_id')
    def _compute_edu_kind(self):
        mestrado = self.env.ref('edu_university.level_mestrado', raise_if_not_found=False)
        for project in self:
            level = project.course_id.level_id
            if level.subsystem != 'higher':
                project.edu_kind = 'pap'
            else:
                project.edu_kind = 'dissertation' if level == mestrado else 'tfc'

    def _compute_uc_registration_id(self):
        for project in self:
            project.uc_registration_id = project.enrollment_id.uc_registration_ids.filtered(
                lambda r: r.curriculum_line_id.is_final_work
            )[:1]

    def action_evaluate(self, grade=None):
        result = super().action_evaluate(grade=grade)
        self._edu_push_to_uc()
        return result

    def action_reopen(self):
        result = super().action_reopen()
        self._edu_push_to_uc()
        return result

    def _edu_push_to_uc(self):
        self.sudo().uc_registration_id._edu_uc_refresh()


class EduGraduation(models.Model):
    _inherit = 'edu.graduation'

    uc_result_ids = fields.Many2many(
        'edu.uc.registration', string='Unidades curriculares', compute='_compute_uc_result_ids'
    )
    uc_credits = fields.Float(string='Créditos obtidos', compute='_compute_uc_result_ids', digits=(6, 1))

    def _edu_is_higher(self):
        self.ensure_one()
        return self.level_id.subsystem == 'higher'

    def _compute_uc_result_ids(self):
        for graduation in self:
            results = graduation._uc_results() if graduation._edu_is_higher() else self.env['edu.uc.registration']
            graduation.uc_result_ids = results
            graduation.uc_credits = sum(results.mapped('credits'))

    def _uc_results(self):
        """A aprovação de cada UC do curso (a mais recente, se houver melhoria noutro ano)."""
        self.ensure_one()
        registrations = (
            self.env['edu.uc.registration']
            .sudo()
            .search(
                [
                    ('student_id', '=', self.student_id.id),
                    ('course_id', '=', self.course_id.id),
                    ('state', '=', 'passed'),
                ]
            )
        )
        latest = {}
        for registration in registrations.sorted(lambda r: r.academic_year_id.date_start):
            latest[registration.subject_id] = registration
        return registrations.browse([r.id for r in latest.values()]).sorted(
            lambda r: (r.course_year, r.semester or '', r.curriculum_line_id.sequence, r.subject_id.name)
        )

    def action_compute(self):
        """Média final do curso: a média das notas das UCs pesada pelos créditos (o trabalho final é uma UC),
        arredondada como manda o regulamento."""
        higher = self.filtered(lambda g: g._edu_is_higher())
        for graduation in higher:
            if graduation.state != 'draft':
                continue
            results = graduation._uc_results()
            credits = sum(results.mapped('credits'))
            enrollment = graduation.enrollment_id
            regulation = self.env['edu.university.regulation']._get(
                enrollment.company_id, enrollment.course_id.level_id
            )
            average = sum(r.final_grade * r.credits for r in results) / credits if credits else 0.0
            average = round_grade(average, regulation.rounding)
            with trusted(self.env):
                graduation.write({'plan_average': average, 'final_grade': average})
        return super(EduGraduation, self - higher).action_compute()
