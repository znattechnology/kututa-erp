from odoo import api, models
from odoo.exceptions import AccessError


class EduGradeGrid(models.AbstractModel):
    """Na grelha «Notas da turma», a secretaria visualiza e imprime a pauta da turma do trimestre, como no secPed."""

    _inherit = 'edu.grade.grid'

    @api.model
    def grid_data(self, class_id, subject_id):
        data = super().grid_data(class_id, subject_id)
        data['can_print'] = self._is_staff()
        return data

    @api.model
    def grid_print(self, class_id, trimester_id, preview=True):
        """A pauta da turma até ao trimestre escolhido: na aplicação (Visualizar) ou em PDF (Imprimir)."""
        if not self._is_staff():
            raise AccessError(self.env._('Só a secretaria imprime a pauta da turma.'))
        wizard = self.env['edu.pauta.print'].create(
            {'class_id': self._class(class_id).id, 'kind': 'final', 'trimester_id': trimester_id}
        )
        return wizard.action_preview() if preview else wizard.action_print()
