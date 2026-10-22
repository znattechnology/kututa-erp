from odoo import api, models
from odoo.exceptions import UserError


class EduMiniPauta(models.AbstractModel):
    """Página «Mini-pauta» (acção cliente ``edu_documents.mini_pauta``), como a do secPed-Express: o ano lectivo, a
    turma e o trimestre, e a mini-pauta da turma (mapa de aproveitamento condensado, A4) para ver e imprimir. As
    turmas são as da grelha «Notas da turma»: a secretaria vê todas; o professor, as que lecciona ou dirige."""

    _name = 'edu.mini.pauta'
    _description = 'Mini-pauta'

    @api.model
    def page_options(self, year_id=False):
        options = self.env['edu.grade.grid'].grid_classes(year_id)
        year = self.env['edu.academic.year'].browse(options['year_id'])
        classes = self.env['edu.class'].sudo().browse([c['id'] for c in options['classes']])
        shifts = {c.id: c.shift_id.name or '' for c in classes}
        for row in options['classes']:
            row['shift'] = shifts.get(row['id'], '')
        options['trimesters'] = [
            {'id': t.id, 'number': t.number, 'name': t.name, 'is_current': t.is_current and year.is_current}
            for t in year.trimester_ids.sorted('number')
        ]
        return options

    @api.model
    def page_open(self, class_id, trimester_id, preview=True):
        """A mini-pauta da turma no trimestre: na aplicação (Abrir) ou em PDF (Imprimir)."""
        Grid = self.env['edu.grade.grid']
        edu_class = Grid._class(class_id)
        allowed = [c['id'] for c in Grid.grid_classes(edu_class.academic_year_id.id)['classes']]
        if edu_class.id not in allowed:
            raise UserError(self.env._('Só abre a mini-pauta das turmas onde dá aulas ou que dirige.'))
        trimester = edu_class.academic_year_id.trimester_ids.filtered(lambda t: t.id == trimester_id)
        if not trimester:
            raise UserError(self.env._('Escolha um trimestre do ano lectivo da turma.'))
        if not edu_class.sudo().enrollment_ids.filtered(lambda e: e.state != 'draft'):
            raise UserError(self.env._('Esta turma não tem alunos neste trimestre.'))
        wizard = self.env['edu.pauta.print'].create(
            {'class_id': edu_class.id, 'kind': 'mini', 'trimester_id': trimester.id}
        )
        return wizard.action_preview() if preview else wizard.action_print()
