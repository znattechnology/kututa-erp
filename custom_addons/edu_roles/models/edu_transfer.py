from odoo import api, fields, models

# As colunas do quadro das transferências que ficam sempre à vista, mesmo vazias.
BOARD_STATES = ['pending', 'approved', 'completed']


class EduTransfer(models.Model):
    """O quadro das transferências da secretaria: uma coluna por estado (as por decidir, as por concluir e as
    concluídas sempre à vista, as rejeitadas e as canceladas só quando há)."""

    _inherit = 'edu.transfer'

    state = fields.Selection(group_expand='_edu_expand_states')
    # O nome do aluno, também numa entrada em que o aluno ainda não existe.
    edu_student_name = fields.Char(string='Aluno (nome)', compute='_compute_edu_student_name')

    def _edu_expand_states(self, states, domain):
        return [s for s in [*BOARD_STATES, 'rejected', 'cancelled'] if s in BOARD_STATES or s in states]

    @api.depends('student_id', 'incoming_name')
    def _compute_edu_student_name(self):
        for transfer in self:
            transfer.edu_student_name = transfer.student_id.name or transfer.incoming_name
