from odoo import fields, models


class EduLevel(models.Model):
    _inherit = 'edu.level'

    subsystem = fields.Selection(selection_add=[('higher', 'Ensino superior')], ondelete={'higher': 'set default'})
