from odoo import api, fields, models
from odoo.exceptions import UserError

from .edu_enrollment import SEAT_STATES

# Alunos da turma: os matriculados e, num ano fechado, os que o concluíram ou ficaram retidos nela.
MEMBER_STATES = (*SEAT_STATES, 'completed', 'retained')


class EduClass(models.Model):
    _inherit = 'edu.class'

    enrollment_ids = fields.One2many('edu.enrollment', 'class_id', string='Matrículas')
    student_count = fields.Integer(string='Alunos', compute='_compute_student_count')
    seats_available = fields.Integer(string='Vagas livres', compute='_compute_student_count')

    @api.depends('enrollment_ids.state', 'capacity')
    def _compute_student_count(self):
        for edu_class in self:
            count = len(edu_class.enrollment_ids.filtered(lambda e: e.state in MEMBER_STATES))
            edu_class.student_count = count
            edu_class.seats_available = max(edu_class.capacity - count, 0)

    def action_view_enrollments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Alunos da %s', self.display_name),
            'res_model': 'edu.enrollment',
            'view_mode': 'list,form',
            'domain': [('class_id', '=', self.id)],
            'context': {'default_class_id': self.id, 'search_default_enrolled': 1},
        }

    def _edu_can_renumber(self):
        """A avaliação impede a renumeração depois de haver notas (a pauta já usa os números)."""
        self.ensure_one()
        return True

    def action_renumber_alphabetical(self):
        """Números de ordem por ordem alfabética, no início do ano (os anulados e transferidos ficam no fim)."""
        for edu_class in self:
            if not edu_class._edu_can_renumber():
                raise UserError(
                    self.env._('A turma %s já tem notas: os números de ordem não se alteram.', edu_class.display_name)
                )
            enrollments = edu_class.enrollment_ids.filtered(lambda e: e.state != 'draft')
            ordered = enrollments.sorted(
                lambda e: (e.state not in SEAT_STATES, (e.student_id.name or '').lower(), e.id)
            )
            enrollments.write({'order_number': False})
            enrollments.flush_recordset(['order_number'])  # libertar os números antes de os redistribuir
            for number, enrollment in enumerate(ordered, start=1):
                enrollment.order_number = number
        return True
