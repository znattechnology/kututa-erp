from odoo import fields, models

# Professores, secretaria e RH vêem os dados de professor.
TEACHER_DATA_GROUPS = 'hr.group_hr_user,edu_core.group_edu_user,edu_core.group_edu_teacher'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    edu_is_teacher = fields.Boolean(string='Professor(a)', groups=TEACHER_DATA_GROUPS)
    edu_specialization = fields.Char(string='Especialidade', groups=TEACHER_DATA_GROUPS)
    edu_coordination_id = fields.Many2one(
        'edu.coordination',
        string='Coordenação',
        groups=TEACHER_DATA_GROUPS,
    )
    edu_subject_ids = fields.Many2many(
        'edu.subject',
        string='Disciplinas que lecciona',
        groups=TEACHER_DATA_GROUPS,
        help='Habilitação: as disciplinas em que o professor pode ser colocado.',
    )


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # Quem não é do RH (secretaria, professores, tesouraria) lê os funcionários pelo perfil público: os dados de
    # professor têm de lá estar, senão as turmas, horários e colocações dão erro de acesso.
    edu_is_teacher = fields.Boolean(string='Professor(a)', readonly=True)
    edu_specialization = fields.Char(string='Especialidade', readonly=True)
    edu_coordination_id = fields.Many2one('edu.coordination', string='Coordenação', readonly=True)
    edu_subject_ids = fields.Many2many(
        'edu.subject', string='Disciplinas que lecciona', compute='_compute_edu_subject_ids'
    )

    def _compute_edu_subject_ids(self):
        for employee in self:
            employee.edu_subject_ids = employee.employee_id.sudo().edu_subject_ids
