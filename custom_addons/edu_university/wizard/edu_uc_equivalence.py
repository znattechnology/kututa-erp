from odoo import fields, models


class EduUcEquivalence(models.TransientModel):
    """Crédito de uma UC por equivalência (transferência, outro curso, migração)."""

    _name = 'edu.uc.equivalence'
    _description = 'Creditar UC por equivalência'

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True)
    curriculum_id = fields.Many2one(related='enrollment_id.class_id.curriculum_id')
    subject_id = fields.Many2one(
        'edu.subject', string='Unidade curricular', required=True, domain="[('id', 'in', allowed_subject_ids)]"
    )
    allowed_subject_ids = fields.Many2many('edu.subject', compute='_compute_allowed_subject_ids')
    grade = fields.Float(string='Nota', required=True, default=10, digits=(4, 2))
    note = fields.Char(string='Origem', help='Instituição, curso e documento que comprovam a aprovação.')

    def _compute_allowed_subject_ids(self):
        for wizard in self:
            enrollment = wizard.enrollment_id
            lines = enrollment.class_id.curriculum_id.line_ids.filtered(
                lambda line, n=enrollment.class_number: line.year_id.year <= n
            )
            wizard.allowed_subject_ids = lines.subject_id - enrollment.uc_registration_ids.subject_id

    def action_confirm(self):
        self.ensure_one()
        self.env['edu.uc.registration']._edu_credit_equivalence(
            self.enrollment_id, self.subject_id, self.grade, self.note
        )
        return {'type': 'ir.actions.act_window_close'}
