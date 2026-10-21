from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.edu_enrollment import SEAT_STATES


class EduEnrollmentRenewal(models.TransientModel):
    """Rematrícula: passa os alunos de uma turma para uma turma do ano lectivo seguinte."""

    _name = 'edu.enrollment.renewal'
    _description = 'Rematrícula'

    source_class_id = fields.Many2one('edu.class', string='Turma de origem', required=True)
    target_class_id = fields.Many2one(
        'edu.class',
        string='Turma de destino',
        required=True,
        domain="[('academic_year_id', '!=', source_year_id), ('company_id', '=', company_id)]",
    )
    source_year_id = fields.Many2one(related='source_class_id.academic_year_id')
    company_id = fields.Many2one(related='source_class_id.company_id')
    enrollment_ids = fields.Many2many(
        'edu.enrollment',
        string='Alunos',
        compute='_compute_enrollment_ids',
        store=True,
        readonly=False,
        domain="[('class_id', '=', source_class_id)]",
    )
    confirm = fields.Boolean(string='Activar já as matrículas', default=True)

    @api.depends('source_class_id')
    def _compute_enrollment_ids(self):
        for wizard in self:
            wizard.enrollment_ids = wizard.source_class_id.enrollment_ids.filtered(
                lambda e: e.state in SEAT_STATES + ('completed', 'retained')
            )

    def action_confirm(self):
        self.ensure_one()
        target = self.target_class_id
        if target.academic_year_id.date_start <= self.source_class_id.academic_year_id.date_start:
            raise UserError(self.env._('A turma de destino tem de ser de um ano lectivo posterior.'))
        Enrollment = self.env['edu.enrollment']
        created = Enrollment
        skipped = []
        for previous in self.enrollment_ids.sorted(lambda e: (e.order_number or 0, e.id)):
            student = previous.student_id
            if student.enrollment_ids.filtered(
                lambda e, year=target.academic_year_id: (
                    e.academic_year_id == year and e.state not in ('dropped', 'transferred')
                )
            ):
                skipped.append(student.name)
                continue
            created |= Enrollment.create(
                {
                    'student_id': student.id,
                    'class_id': target.id,
                    'previous_enrollment_id': previous.id,
                    'enrollment_type': 'repeat' if target.class_number == previous.class_number else 'renewal',
                }
            )
        if self.confirm:
            created.action_confirm()
        message = self.env._('%s matrícula(s) criada(s).', len(created))
        if skipped:
            message += ' ' + self.env._('Já matriculados no ano: %s.', ', '.join(skipped))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Rematrícula'),
                'message': message,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
