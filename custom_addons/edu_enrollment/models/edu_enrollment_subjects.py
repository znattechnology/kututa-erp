from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .edu_enrollment import SEAT_STATES


class EduEnrollmentSubjectDrop(models.Model):
    """Anulação da matrícula a uma disciplina no ensino técnico (Decreto Executivo n.º 60/08, art. 11.º): até ao 5.º dia
    útil do III trimestre, com efeito só nessa disciplina. Quem anulou pode fazer exame na época normal (art. 39.º,
    n.º 1, al. a)."""

    _name = 'edu.enrollment.subject.drop'
    _description = 'Anulação da matrícula a uma disciplina'
    _order = 'date desc, id desc'
    _check_company_auto = True

    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', required=True, ondelete='cascade', index=True, check_company=True
    )
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True)
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True)
    subject_id = fields.Many2one(
        'edu.subject',
        string='Disciplina',
        required=True,
        check_company=True,
        domain="[('id', 'in', enrollment_subject_ids)]",
    )
    enrollment_subject_ids = fields.Many2many(related='enrollment_id.subject_ids')
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    reason = fields.Char(string='Motivo')

    _enrollment_subject_uniq = models.Constraint(
        'UNIQUE(enrollment_id, subject_id)', 'A matrícula a esta disciplina já foi anulada.'
    )

    @api.constrains('enrollment_id', 'subject_id')
    def _check_subject(self):
        for drop in self:
            enrollment = drop.enrollment_id
            if enrollment.course_id.level_id.subsystem != 'technical':
                raise ValidationError(
                    self.env._(
                        'A anulação por disciplina é do ensino técnico (Decreto Executivo n.º 60/08, art. 11.º).'
                    )
                )
            if drop.subject_id not in enrollment.subject_ids:
                raise ValidationError(self.env._('O aluno não está matriculado em %s.', drop.subject_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        drops = super().create(vals_list)
        manager = self.env.user.has_group('edu_core.group_edu_manager') or self.env.su
        for drop in drops:
            if drop.enrollment_id.state not in SEAT_STATES:
                raise UserError(self.env._('A matrícula já não está em curso.'))
            deadline = drop.enrollment_id._drop_deadline()
            if deadline and drop.date > deadline and not manager:
                raise UserError(
                    self.env._(
                        'Fora do prazo de anulação por disciplina (até %s, Decreto Executivo n.º 60/08, art. 11.º): '
                        'só a direcção.',
                        deadline.strftime('%d/%m/%Y'),
                    )
                )
            drop.enrollment_id.message_post(body=self.env._('Matrícula anulada à disciplina %s.', drop.subject_id.name))
        return drops


class EduEnrollmentLowerSubject(models.Model):
    """Disciplina feita numa turma da classe anterior (Decreto Executivo n.º 60/08, arts. 9.º e 10.º): com 6 ou menos
    valores numa disciplina de continuação, ou com duas negativas seguidas numa trienal, o aluno que transita
    matricula-se nessa disciplina na classe anterior, havendo vaga e condições organizativas. As notas lançadas nessa
    turma contam na sua matrícula."""

    _name = 'edu.enrollment.lower.subject'
    _description = 'Disciplina na classe anterior'
    _order = 'enrollment_id, subject_id'
    _check_company_auto = True

    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', required=True, ondelete='cascade', index=True, check_company=True
    )
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, check_company=True)
    class_id = fields.Many2one(
        'edu.class', string='Turma onde a faz', required=True, index=True, check_company=True,
        domain="[('academic_year_id', '=', academic_year_id)]",
    )  # fmt: skip
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id')
    reason = fields.Char(string='Motivo')

    _enrollment_subject_uniq = models.Constraint(
        'UNIQUE(enrollment_id, subject_id)', 'A disciplina já está noutra turma para este aluno.'
    )

    @api.constrains('class_id', 'subject_id', 'enrollment_id')
    def _check_class(self):
        for line in self:
            enrollment, target = line.enrollment_id, line.class_id
            if target.academic_year_id != enrollment.academic_year_id or target.course_id != enrollment.course_id:
                raise ValidationError(self.env._('A turma tem de ser do mesmo curso e ano lectivo.'))
            if target.class_number >= enrollment.class_number:
                raise ValidationError(self.env._('A turma tem de ser de uma classe anterior.'))
            if line.subject_id not in target.subject_line_ids.subject_id:
                raise ValidationError(
                    self.env._('%(subject)s não é do plano da %(class)s.', subject=line.subject_id.name,
                               **{'class': target.display_name})
                )  # fmt: skip

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            # Fica inscrito na disciplina (as notas lançam-se na turma da classe anterior).
            line.enrollment_id.with_context(edu_enrollment_reseed=True).subject_ids |= line.subject_id
        return lines


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    subject_drop_ids = fields.One2many('edu.enrollment.subject.drop', 'enrollment_id', string='Disciplinas anuladas')
    lower_subject_ids = fields.One2many(
        'edu.enrollment.lower.subject', 'enrollment_id', string='Disciplinas na classe anterior'
    )

    def _dropped_subjects(self):
        return self.subject_drop_ids.subject_id

    @api.model
    def _for_class_subject(self, edu_class, subject):
        """Os alunos que fazem a disciplina nesta turma: os da turma inscritos nela (menos quem a anulou ou a faz numa
        turma da classe anterior) e os de outras turmas que a fazem aqui. É a lista das notas e da chamada."""
        own = self.sudo().search(
            [('class_id', '=', edu_class.id), ('state', 'in', SEAT_STATES), ('subject_ids', 'in', subject.ids)],
            order='order_number, id',
        )
        own = own.filtered(
            lambda e: subject not in e.subject_drop_ids.subject_id and subject not in e.lower_subject_ids.subject_id
        )
        visiting = (
            self.env['edu.enrollment.lower.subject']
            .sudo()
            .search([('class_id', '=', edu_class.id), ('subject_id', '=', subject.id)])
            .enrollment_id.filtered(lambda e: e.state in SEAT_STATES and subject not in e.subject_drop_ids.subject_id)
        )
        return own | visiting.sorted('id')

    def action_drop_subject(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Anular a matrícula a uma disciplina'),
            'res_model': 'edu.enrollment.subject.drop',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_enrollment_id': self.id},
        }
