from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

OPEN = ('pending', 'review')


class EduGradeAppeal(models.Model):
    """Reapreciação de uma nota (RAA, art. 36.º; Despacho 60/08, art. 15.º): a única via de alterar uma nota de um
    trimestre fechado."""

    _name = 'edu.grade.appeal'
    _description = 'Reapreciação de nota'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    grade_id = fields.Many2one('edu.grade', string='Nota', required=True, check_company=True)
    student_id = fields.Many2one(related='grade_id.student_id', store=True)
    subject_id = fields.Many2one(related='grade_id.subject_id', store=True)
    class_id = fields.Many2one(related='grade_id.class_id', store=True)
    company_id = fields.Many2one(related='grade_id.company_id', store=True)
    reason = fields.Text(string='Fundamentação do pedido', required=True)
    original_score = fields.Float(string='Nota inicial', digits=(4, 2), readonly=True)
    new_score = fields.Float(string='Nova nota', digits=(4, 2))
    state = fields.Selection(
        [('pending', 'Pedida'), ('review', 'Em apreciação'), ('granted', 'Deferida'), ('denied', 'Indeferida')],
        string='Estado',
        default='pending',
        required=True,
        tracking=True,
    )
    decision = fields.Text(string='Decisão')
    decided_by_id = fields.Many2one('res.users', string='Decidida por', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        appeals = super().create(vals_list)
        for appeal in appeals:
            if self.search_count(
                [('grade_id', '=', appeal.grade_id.id), ('state', 'in', OPEN), ('id', '!=', appeal.id)]
            ):
                raise ValidationError(self.env._('Esta nota já tem uma reapreciação em curso.'))
            appeal.original_score = appeal.grade_id.score
        return appeals

    def action_review(self):
        self.filtered(lambda a: a.state == 'pending').write({'state': 'review'})
        return True

    def action_grant(self):
        for appeal in self:
            if appeal.state not in OPEN:
                raise UserError(self.env._('A reapreciação já foi decidida.'))
            grade = appeal.grade_id
            if not 0 <= appeal.new_score <= grade.assessment_id.max_score:
                raise ValidationError(self.env._('A nova nota vai de 0 a %s.', grade.assessment_id.max_score))
            grade.with_context(edu_grade_appeal=True).write({'score': appeal.new_score, 'absent': False})
            appeal.write({'state': 'granted', 'decided_by_id': self.env.uid})
            # A decisão do ano (se já tomada e não manual) acompanha a nota reapreciada.
            year_result = grade.enrollment_id.sudo().year_result_id
            if year_result and not year_result.manual:
                year_result.action_recompute()
        return True

    def action_deny(self):
        for appeal in self:
            if appeal.state not in OPEN:
                raise UserError(self.env._('A reapreciação já foi decidida.'))
            appeal.write({'state': 'denied', 'decided_by_id': self.env.uid})
        return True
