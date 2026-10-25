from odoo import api, fields, models


class EduStudent(models.Model):
    """Os alunos que falta confirmar: a última matrícula (turma e resultado do ano), o encarregado para contactar e a
    matrícula no ano em curso a um clique, já com o aluno e o tipo."""

    _inherit = 'edu.student'

    edu_last_enrollment_id = fields.Many2one(
        'edu.enrollment', string='Última matrícula', compute='_compute_edu_last_enrollment_id'
    )
    edu_last_class_id = fields.Many2one('edu.class', string='Última turma', compute='_compute_edu_last_enrollment_id')
    edu_last_state = fields.Selection(related='edu_last_enrollment_id.state', string='Resultado do ano')
    edu_guardian_name = fields.Char(related='primary_guardian_id.name', string='Encarregado')
    edu_guardian_phone = fields.Char(related='primary_guardian_id.phone', string='Telefone do encarregado')

    @api.depends('enrollment_ids.academic_year_id', 'enrollment_ids.class_id')
    def _compute_edu_last_enrollment_id(self):
        for student in self:
            last = student.enrollment_ids.sorted(lambda e: (e.academic_year_id.date_start, e.id), reverse=True)[:1]
            student.edu_last_enrollment_id = last
            student.edu_last_class_id = last.class_id

    def action_edu_enroll_again(self):
        """A nova matrícula com o aluno, a matrícula anterior e o tipo (repetente, se ficou retido) já preenchidos."""
        self.ensure_one()
        last = self.edu_last_enrollment_id
        action = self.env['ir.actions.act_window']._for_xml_id('edu_roles.action_edu_enrollment_new')
        action['context'] = {
            'default_student_id': self.id,
            'default_previous_enrollment_id': last.id,
            'default_enrollment_type': 'repeat' if last.state == 'retained' else 'renewal',
        }
        return action
