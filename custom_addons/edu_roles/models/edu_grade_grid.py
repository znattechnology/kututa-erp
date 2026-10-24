from odoo import api, models


class EduGradeGrid(models.AbstractModel):
    """Na turma que dirige, o director justifica as faltas a partir de «Turmas e notas», como no secPed (o menu do
    professor não tem o grupo «Direcção de turma»)."""

    _inherit = 'edu.grade.grid'

    @api.model
    def _class_links(self, edu_class, directs):
        links = super()._class_links(edu_class, directs)
        if directs and edu_class.academic_year_id.is_current:
            links.append({'key': 'absences', 'label': self.env._('Justificar faltas'), 'icon': 'how_to_reg'})
        return links

    @api.model
    def _class_link_action(self, edu_class, key):
        if key == 'absences':
            action = self.env['ir.actions.actions']._for_xml_id('edu_roles.action_teacher_absences')
            action['domain'] = [
                ('state', 'in', ('absent', 'excused')),
                ('lesson_state', '=', 'done'),
                '|', ('class_id', '=', edu_class.id), ('enrollment_id.class_id', '=', edu_class.id),
            ]  # fmt: skip
            action['context'] = {'search_default_absent': 1}
            action['name'] = self.env._('Justificar faltas · %s', edu_class._editor_label())
            return action
        return super()._class_link_action(edu_class, key)
