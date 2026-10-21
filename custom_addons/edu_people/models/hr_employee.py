from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    edu_is_teacher = fields.Boolean(string='Professor(a)', groups='hr.group_hr_user,edu_core.group_edu_user')
    edu_specialization = fields.Char(string='Especialidade', groups='hr.group_hr_user,edu_core.group_edu_user')
    edu_coordination_id = fields.Many2one(
        'edu.coordination', string='Coordenação', groups='hr.group_hr_user,edu_core.group_edu_user'
    )
    edu_subject_ids = fields.Many2many(
        'edu.subject',
        string='Disciplinas que lecciona',
        groups='hr.group_hr_user,edu_core.group_edu_user',
        help='Habilitação: as disciplinas em que o professor pode ser colocado.',
    )
