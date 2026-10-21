from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .edu_enrollment import SEAT_STATES


class EduTransfer(models.Model):
    """Transferência. Dentro da escola, a mesma matrícula muda de turma (as notas acompanham-na) e recebe o número
    de ordem seguinte na turma de destino; a saída para outra escola fecha a matrícula."""

    _name = 'edu.transfer'
    _description = 'Transferência'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    student_id = fields.Many2one(
        'edu.student', string='Aluno', required=True, index=True, tracking=True, check_company=True
    )
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    enrollment_id = fields.Many2one(
        'edu.enrollment',
        string='Matrícula',
        required=True,
        check_company=True,
        domain="[('student_id', '=', student_id), ('state', 'in', ('active', 'irregular'))]",
    )
    transfer_type = fields.Selection(
        [
            ('class_change', 'Mudança de turma'),
            ('course_change', 'Mudança de curso'),
            ('internal', 'Mudança interna'),
            ('external', 'Saída para outra escola'),
        ],
        string='Tipo',
        required=True,
        default='class_change',
        tracking=True,
    )
    from_class_id = fields.Many2one('edu.class', string='Turma de origem', readonly=True, copy=False)
    to_class_id = fields.Many2one(
        'edu.class',
        string='Turma de destino',
        check_company=True,
        domain="[('academic_year_id', '=', academic_year_id)]",
    )
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id')
    external_school = fields.Char(string='Escola de destino')
    reason = fields.Text(string='Motivo', required=True)
    state = fields.Selection(
        [
            ('pending', 'Pendente'),
            ('approved', 'Aprovada'),
            ('rejected', 'Rejeitada'),
            ('completed', 'Concluída'),
            ('cancelled', 'Cancelada'),
        ],
        string='Estado',
        default='pending',
        required=True,
        tracking=True,
    )
    effective_date = fields.Date(string='Data de efeito', default=fields.Date.context_today)
    reviewed_by_id = fields.Many2one('res.users', string='Decidida por', readonly=True, copy=False)
    decision_note = fields.Text(string='Fundamentação')

    @api.constrains('transfer_type', 'to_class_id', 'external_school', 'enrollment_id')
    def _check_target(self):
        for transfer in self:
            if transfer.enrollment_id.student_id != transfer.student_id:
                raise ValidationError(self.env._('A matrícula não é deste aluno.'))
            if transfer.transfer_type == 'external':
                if not transfer.external_school:
                    raise ValidationError(self.env._('Indique a escola de destino.'))
            elif not transfer.to_class_id:
                raise ValidationError(self.env._('Indique a turma de destino.'))
            elif transfer.to_class_id == transfer.enrollment_id.class_id and transfer.state == 'pending':
                raise ValidationError(self.env._('A turma de destino é a actual.'))
            if transfer.transfer_type == 'course_change' and transfer.to_class_id.course_id == (
                transfer.enrollment_id.course_id
            ):
                raise ValidationError(self.env._('Numa mudança de curso, a turma de destino é de outro curso.'))

    def action_approve(self):
        for transfer in self:
            if transfer.state != 'pending':
                raise UserError(self.env._('Só se aprova uma transferência pendente.'))
            transfer.write({'state': 'approved', 'reviewed_by_id': self.env.uid})
        return True

    def action_reject(self):
        for transfer in self:
            if transfer.state != 'pending':
                raise UserError(self.env._('Só se rejeita uma transferência pendente.'))
            transfer.write({'state': 'rejected', 'reviewed_by_id': self.env.uid})
        return True

    def action_cancel(self):
        if self.filtered(lambda t: t.state == 'completed'):
            raise UserError(self.env._('Uma transferência concluída não se cancela.'))
        self.write({'state': 'cancelled'})
        return True

    def action_complete(self):
        Enrollment = self.env['edu.enrollment']
        for transfer in self:
            if transfer.state != 'approved':
                raise UserError(self.env._('Aprove a transferência antes de a concluir.'))
            enrollment = transfer.enrollment_id
            if enrollment.state not in SEAT_STATES:
                raise UserError(self.env._('A matrícula já não está em curso.'))
            transfer.from_class_id = enrollment.class_id
            if transfer.transfer_type == 'external':
                enrollment._drop(
                    self.env._(
                        'Transferido(a) para %(school)s. %(reason)s',
                        school=transfer.external_school,
                        reason=transfer.reason,
                    ),
                    state='transferred',
                    day=transfer.effective_date,
                )
            else:
                target = transfer.to_class_id
                taken = Enrollment.search_count([('class_id', '=', target.id), ('state', 'in', SEAT_STATES)])
                if target.capacity and taken >= target.capacity:
                    raise UserError(self.env._('A turma %s está completa.', target.display_name))
                vals = {'class_id': target.id, 'order_number': Enrollment._next_order_number(target)}
                if target.curriculum_id != transfer.from_class_id.curriculum_id or (
                    target.class_number != transfer.from_class_id.class_number
                ):
                    # Disciplinas do novo plano, mais as que já têm notas.
                    vals['subject_ids'] = [
                        fields.Command.set((target.subject_line_ids.subject_id | enrollment._edu_locked_subjects()).ids)
                    ]
                enrollment.with_context(edu_enrollment_reseed=True).write(vals)
            transfer.state = 'completed'
        return True
