from odoo import fields, models

# As colunas do quadro das candidaturas que ficam sempre à vista, mesmo vazias.
BOARD_STATES = ['submitted', 'review', 'approved', 'rejected']


class EduApplication(models.Model):
    """O quadro das candidaturas da secretaria: uma coluna por estado (as de decidir e as decididas sempre à
    vista, o rascunho e as canceladas só quando há)."""

    _inherit = 'edu.application'

    state = fields.Selection(group_expand='_edu_expand_states')

    def _edu_expand_states(self, states, domain):
        return [s for s in ['draft', *BOARD_STATES, 'cancelled'] if s in BOARD_STATES or s in states]


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    # O nome do aluno sem o n.º de matrícula à frente (o cartão mostra o número à parte).
    edu_student_name = fields.Char(related='student_id.name', string='Aluno (nome)')
    # A turma escolhida na nova matrícula: os alunos, as vagas e o turno, à vista enquanto se escolhe.
    edu_class_students = fields.Integer(related='class_id.student_count', string='Alunos na turma')
    edu_class_capacity = fields.Integer(related='class_id.capacity', string='Vagas da turma')
    edu_class_seats = fields.Integer(related='class_id.seats_available', string='Vagas livres')
    edu_class_shift = fields.Char(related='class_id.shift_id.name', string='Turno')
