from odoo import api, models
from odoo.exceptions import AccessError, UserError


class EduGradeGrid(models.AbstractModel):
    """Na grelha «Notas da turma», a secretaria e o director de turma visualizam e imprimem a pauta da turma do
    trimestre, como no secPed."""

    _inherit = 'edu.grade.grid'

    @api.model
    def grid_data(self, class_id, subject_id):
        data = super().grid_data(class_id, subject_id)
        data['can_print'] = self._can_print(self._class(class_id))
        return data

    @api.model
    def _can_print(self, edu_class):
        employee = self._employee()
        return self._is_staff() or (bool(employee) and edu_class.sudo().director_id == employee)

    @api.model
    def grid_print(self, class_id, trimester_id, preview=True):
        """A pauta da turma até ao trimestre escolhido: na aplicação (Visualizar) ou em PDF (Imprimir)."""
        edu_class = self._class(class_id)
        if not self._can_print(edu_class):
            raise AccessError(self.env._('Só a secretaria e o director de turma imprimem a pauta da turma.'))
        trimester = edu_class.academic_year_id.trimester_ids.filtered(lambda t: t.id == trimester_id)
        if not trimester:
            raise UserError(self.env._('Escolha um trimestre do ano lectivo da turma.'))
        wizard = self.env['edu.pauta.print'].create(
            {'class_id': edu_class.id, 'kind': 'final', 'trimester_id': trimester.id}
        )
        return wizard.action_preview() if preview else wizard.action_print()

    @api.model
    def _class_links(self, edu_class, directs):
        # A mini-pauta abre-se da turma, como no secPed (o menu do professor deixou de a ter).
        links = super()._class_links(edu_class, directs)
        if edu_class.level_id.code != 'INICIACAO':
            links.insert(0, {'key': 'mini_pauta', 'label': self.env._('Mini-pauta'), 'icon': 'table_view'})
        return links

    @api.model
    def _class_link_action(self, edu_class, key):
        if key == 'mini_pauta':
            action = self.env['ir.actions.actions']._for_xml_id('edu_documents.action_edu_mini_pauta')
            action['context'] = {
                'default_class_id': edu_class.id,
                'default_academic_year_id': edu_class.academic_year_id.id,
            }
            return action
        return super()._class_link_action(edu_class, key)
