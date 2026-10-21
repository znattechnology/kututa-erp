from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class EduLessonGenerate(models.TransientModel):
    _name = 'edu.lesson.generate'
    _description = 'Gerar as aulas previstas a partir do horário'

    class_ids = fields.Many2many('edu.class', string='Turmas', required=True)
    date_from = fields.Date(string='De', required=True, default=fields.Date.context_today)
    date_to = fields.Date(
        string='Até', required=True, default=lambda self: fields.Date.context_today(self) + timedelta(days=6)
    )

    def action_generate(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(self.env._('A data final é anterior à inicial.'))
        lessons = self.env['edu.lesson']._generate(self.class_ids, self.date_from, self.date_to)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Aulas geradas'),
            'res_model': 'edu.lesson',
            'view_mode': 'list,form',
            'domain': [('id', 'in', lessons.ids)],
        }
