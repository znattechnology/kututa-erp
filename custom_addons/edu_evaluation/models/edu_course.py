from odoo import fields, models


class EduCourse(models.Model):
    _inherit = 'edu.course'

    edu_area_subject_ids = fields.Many2many(
        'edu.subject',
        string='Disciplinas específicas da área',
        check_company=True,
        help='II ciclo: na transição, a negativa não pode coincidir em Língua Portuguesa e numa destas '
        '(RAA, art. 25.º, n.º 10).',
    )
