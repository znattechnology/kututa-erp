from odoo import fields, models


class EduStudent(models.Model):
    _inherit = 'edu.student'

    # No superior o estudante é, em regra, maior: o encarregado é opcional (pode ligar-se quem paga as propinas).
    edu_is_higher = fields.Boolean(related='company_id.edu_is_higher')


class EduApplication(models.Model):
    _inherit = 'edu.application'

    edu_is_higher = fields.Boolean(related='company_id.edu_is_higher')
