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

    @api.model
    def _create_next_year_classes(self, source_year, target_year, entry_classes=True):
        """Turmas do ano seguinte a partir das do ano que acaba: a classe seguinte do mesmo curso, com o mesmo nome,
        capacidade, turno e sala, no plano em vigor do curso; e, com ``entry_classes``, as da classe de entrada de cada
        curso (para os novos alunos e os repetentes). As que já existem ficam como estão. Devolve as criadas."""
        sources = self.search(
            [('academic_year_id', '=', source_year.id), ('company_id', '=', source_year.company_id.id)]
        )
        wanted = []
        for edu_class in sources:
            wanted.append((edu_class, edu_class.class_number + 1))
        if entry_classes:
            for course in sources.course_id:
                first = min(sources.filtered(lambda c, co=course: c.course_id == co).mapped('class_number'))
                wanted += [
                    (c, first)
                    for c in sources.filtered(lambda c, co=course, n=first: c.course_id == co and c.class_number == n)
                ]
        created = self.browse()
        for edu_class, number in wanted:
            curriculum = edu_class.course_id.curriculum_id
            year_line = curriculum.year_ids.filtered(lambda y, n=number: y.class_number == n)[:1]
            if not year_line:
                continue  # classe terminal: não há classe seguinte
            exists = self.with_context(active_test=False).search_count(
                [
                    ('academic_year_id', '=', target_year.id),
                    ('course_id', '=', edu_class.course_id.id),
                    ('class_number', '=', number),
                    ('name', '=', edu_class.name),
                ]
            )
            if exists:
                continue
            created |= self.create(
                {
                    'name': edu_class.name,
                    'academic_year_id': target_year.id,
                    'course_id': edu_class.course_id.id,
                    'curriculum_id': curriculum.id,
                    'curriculum_year_id': year_line.id,
                    'capacity': edu_class.capacity,
                    'shift_id': edu_class.shift_id.id,
                    'room_id': edu_class.room_id.id,
                    'company_id': edu_class.company_id.id,
                }
            )
        return created

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
