from odoo import api, fields, models
from odoo.addons.edu_evaluation.tools import grading
from odoo.exceptions import UserError, ValidationError


class EduStudent(models.Model):
    _inherit = 'edu.student'

    process_number = fields.Char(string='Processo individual n.º', copy=False, tracking=True)
    subject_result_ids = fields.One2many('edu.subject.result', 'student_id', string='Histórico escolar')
    graduation_ids = fields.One2many('edu.graduation', 'student_id', string='Conclusões')

    _process_company_uniq = models.Constraint(
        'UNIQUE(company_id, process_number)', 'Já existe um aluno com este número de processo.'
    )

    def action_view_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Histórico escolar de %s', self.name),
            'res_model': 'edu.subject.result',
            'view_mode': 'list,pivot',
            'domain': [('student_id', '=', self.id)],
            'context': {'group_by': ['academic_year_id']},
        }


class EduInternship(models.Model):
    """Estágio curricular (resumo do regime de avaliação, III.5: condição de conclusão do curso técnico)."""

    _name = 'edu.internship'
    _description = 'Estágio curricular'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', check_company=True, domain="[('student_id', '=', student_id)]"
    )
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    course_id = fields.Many2one(related='enrollment_id.course_id', store=True)
    entity = fields.Char(string='Entidade de acolhimento', required=True)
    supervisor = fields.Char(string='Supervisor na entidade')
    supervisor_contact = fields.Char(string='Contacto do supervisor')
    tutor_id = fields.Many2one('hr.employee', string='Tutor(a) da escola', check_company=True)
    date_start = fields.Date(string='Início')
    date_end = fields.Date(string='Fim')
    hours = fields.Integer(string='Horas realizadas')
    grade = fields.Float(string='Classificação', digits=(4, 2))
    state = fields.Selection(
        [
            ('planned', 'Planeado'),
            ('ongoing', 'Em curso'),
            ('passed', 'Aprovado'),
            ('failed', 'Não aprovado'),
            ('cancelled', 'Anulado'),
        ],
        string='Estado',
        default='planned',
        required=True,
        tracking=True,
    )
    note = fields.Text(string='Observações')

    @api.constrains('grade', 'date_start', 'date_end')
    def _check_internship(self):
        for internship in self:
            if not 0 <= internship.grade <= 20:
                raise ValidationError(self.env._('A classificação vai de 0 a 20.'))
            if internship.date_start and internship.date_end and internship.date_end < internship.date_start:
                raise ValidationError(self.env._('O estágio termina antes de começar.'))

    def action_start(self):
        self.write({'state': 'ongoing'})
        return True

    def action_evaluate(self):
        """Fecha o estágio com a classificação: aprovado com 10 ou mais."""
        for internship in self:
            internship.state = 'passed' if internship.grade >= 10 else 'failed'
        return True


class EduFinalProject(models.Model):
    """Prova de Aptidão Profissional (PAP): defesa do projecto final do curso técnico."""

    _name = 'edu.final.project'
    _description = 'Prova de Aptidão Profissional (PAP)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'defense_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Tema', required=True, tracking=True)
    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', check_company=True, domain="[('student_id', '=', student_id)]"
    )
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    course_id = fields.Many2one(related='enrollment_id.course_id', store=True)
    advisor_id = fields.Many2one('hr.employee', string='Orientador(a)', check_company=True)
    jury_ids = fields.Many2many('hr.employee', string='Júri', check_company=True)
    description = fields.Text(string='Resumo')
    defense_date = fields.Date(string='Data da defesa')
    grade = fields.Float(string='Classificação', digits=(4, 2), tracking=True)
    state = fields.Selection(
        [
            ('proposed', 'Proposta'),
            ('ongoing', 'Em elaboração'),
            ('submitted', 'Entregue'),
            ('defended', 'Defendida'),
            ('passed', 'Aprovada'),
            ('failed', 'Não aprovada'),
        ],
        string='Estado',
        default='proposed',
        required=True,
        tracking=True,
    )

    @api.constrains('grade')
    def _check_grade(self):
        for project in self:
            if not 0 <= project.grade <= 20:
                raise ValidationError(self.env._('A classificação vai de 0 a 20.'))

    def action_evaluate(self):
        for project in self:
            if not project.defense_date:
                raise UserError(self.env._('Indique a data da defesa.'))
            project.state = 'passed' if project.grade >= 10 else 'failed'
        return True


class EduGraduation(models.Model):
    """Conclusão de curso ou de nível: base do diploma e do certificado de habilitações."""

    _name = 'edu.graduation'
    _description = 'Conclusão de curso'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    year_result_id = fields.Many2one(
        'edu.year.result', string='Resultado do ano terminal', required=True, check_company=True
    )
    enrollment_id = fields.Many2one(related='year_result_id.enrollment_id', store=True)
    company_id = fields.Many2one(related='year_result_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='year_result_id.academic_year_id', store=True)
    course_id = fields.Many2one(related='enrollment_id.course_id', store=True)
    level_id = fields.Many2one(related='enrollment_id.class_id.level_id', store=True)
    date = fields.Date(string='Data de conclusão', required=True, default=fields.Date.context_today)
    plan_average = fields.Float(string='Classificação do plano curricular (PC)', digits=(4, 2), readonly=True)
    internship_id = fields.Many2one(
        'edu.internship', string='Estágio', domain="[('student_id', '=', student_id), ('state', '=', 'passed')]"
    )
    final_project_id = fields.Many2one(
        'edu.final.project', string='PAP', domain="[('student_id', '=', student_id), ('state', '=', 'passed')]"
    )
    final_grade = fields.Float(string='Classificação final', digits=(4, 2), readonly=True, tracking=True)
    diploma_number = fields.Char(string='Diploma n.º', readonly=True, copy=False, tracking=True)
    book_number = fields.Char(string='Livro de termos n.º')
    page_number = fields.Char(string='Folha n.º')
    state = fields.Selection(
        [('draft', 'Rascunho'), ('issued', 'Emitido'), ('cancelled', 'Anulado')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    final_result_ids = fields.Many2many(
        'edu.subject.result', string='Classificações finais das disciplinas', compute='_compute_final_result_ids'
    )

    _year_result_uniq = models.Constraint('UNIQUE(year_result_id)', 'A conclusão deste ano já está registada.')

    @api.constrains('year_result_id', 'student_id')
    def _check_graduated(self):
        for graduation in self:
            result = graduation.year_result_id
            if result.student_id != graduation.student_id:
                raise ValidationError(self.env._('O resultado do ano é de outro aluno.'))
            if result.status not in ('graduated', 'promoted') or (
                result.status == 'promoted' and not result._policy()._rules(result.class_id).terminal
            ):
                raise ValidationError(
                    self.env._('%s não concluiu o curso neste ano lectivo.', graduation.student_id.name)
                )

    def _compute_final_result_ids(self):
        for graduation in self:
            graduation.final_result_ids = graduation._final_results()

    def _final_results(self):
        """Classificação final de cada disciplina do curso: a do último ano em que foi leccionada."""
        self.ensure_one()
        results = (
            self.env['edu.subject.result']
            .sudo()
            .search(
                [
                    ('student_id', '=', self.student_id.id),
                    ('complete', '=', True),
                    ('class_id.course_id', '=', self.course_id.id),
                ]
            )
        )
        latest = {}
        for result in results.sorted(lambda r: r.academic_year_id.date_start):
            latest[result.subject_id] = result
        return results.browse([result.id for result in latest.values()])

    def action_compute(self):
        """PC = média das classificações finais das disciplinas (CFD); classificação final pela fórmula da escola."""
        for graduation in self:
            if graduation.state != 'draft':
                raise UserError(self.env._('A conclusão já foi emitida.'))
            results = graduation._final_results()
            finals = [r.cfd if r.cfd else r.final for r in results]
            pc = grading.round_units(grading.mean(finals)) if finals else None
            policy = graduation.year_result_id._policy()
            final = grading.course_final(
                pc,
                pap=graduation.final_project_id.grade if graduation.final_project_id else None,
                internship=graduation.internship_id.grade if graduation.internship_id else None,
                formula=policy.course_formula,
            )
            graduation.write({'plan_average': pc or 0.0, 'final_grade': final or 0.0})
        return True

    def action_issue(self):
        """Emite: número de diploma sequencial na escola (ano/sequência)."""
        for graduation in self:
            if graduation.state != 'draft':
                continue
            graduation.action_compute()
            course = graduation.course_id
            if course.requires_final_project and not graduation.final_project_id:
                raise UserError(self.env._('O curso exige a PAP aprovada.'))
            if course.requires_internship and not graduation.internship_id:
                raise UserError(self.env._('O curso exige o estágio curricular aprovado.'))
            sequence = graduation._diploma_sequence()
            graduation.write(
                {
                    'diploma_number': sequence.with_context(ir_sequence_date=graduation.date).next_by_id(),
                    'state': 'issued',
                }
            )
        return True

    def action_cancel(self):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('Só a direcção anula uma conclusão emitida.'))
        self.write({'state': 'cancelled'})
        return True

    def _diploma_sequence(self):
        self.ensure_one()
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search([('code', '=', 'edu.graduation'), ('company_id', '=', self.company_id.id)], limit=1)
        return sequence or Sequence.create(
            {
                'name': self.env._('Diplomas (%s)', self.company_id.name),
                'code': 'edu.graduation',
                'company_id': self.company_id.id,
                'implementation': 'no_gap',
                'prefix': '%(year)s/',
                'padding': 4,
                'use_date_range': True,
            }
        )


class EduYearResult(models.Model):
    _inherit = 'edu.year.result'

    graduation_id = fields.Many2one('edu.graduation', string='Conclusão', compute='_compute_graduation_id')

    def _compute_graduation_id(self):
        Graduation = self.env['edu.graduation'].sudo()
        for result in self:
            result.graduation_id = Graduation.search([('year_result_id', '=', result.id)], limit=1)

    def action_register_graduation(self):
        self.ensure_one()
        graduation = self.graduation_id or self.env['edu.graduation'].create(
            {'student_id': self.student_id.id, 'year_result_id': self.id}
        )
        student = self.student_id
        internship = self.env['edu.internship'].search(
            [('student_id', '=', student.id), ('state', '=', 'passed')], limit=1
        )
        project = self.env['edu.final.project'].search(
            [('student_id', '=', student.id), ('state', '=', 'passed')], limit=1
        )
        if graduation.state == 'draft':
            graduation.write(
                {
                    'internship_id': graduation.internship_id.id or internship.id,
                    'final_project_id': graduation.final_project_id.id or project.id,
                }
            )
            graduation.action_compute()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.graduation',
            'res_id': graduation.id,
            'view_mode': 'form',
        }
