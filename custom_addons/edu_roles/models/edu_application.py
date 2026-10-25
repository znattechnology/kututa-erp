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
