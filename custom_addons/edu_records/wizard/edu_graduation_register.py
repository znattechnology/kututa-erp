from odoo import api, fields, models


class EduGraduationRegister(models.TransientModel):
    """Registar conclusões, como no secPed: a turma da classe final, os alunos que o conselho de turma deu como tendo
    concluído o curso, e registar um a um ou todos de uma vez."""

    _name = 'edu.graduation.register'
    _description = 'Registar conclusões de curso'

    academic_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano lectivo',
        required=True,
        default=lambda self: self.env.company.edu_current_year_id,
    )
    class_id = fields.Many2one('edu.class', string='Turma da classe final', domain="[('id', 'in', final_class_ids)]")
    final_class_ids = fields.Many2many('edu.class', compute='_compute_final_class_ids')
    result_ids = fields.Many2many('edu.year.result', string='Alunos', compute='_compute_result_ids')
    message = fields.Char(compute='_compute_result_ids')

    @api.depends('academic_year_id')
    def _compute_final_class_ids(self):
        for wizard in self:
            classes = self.env['edu.class'].search([('academic_year_id', '=', wizard.academic_year_id.id)])
            wizard.final_class_ids = classes.filtered(
                lambda c: c.class_number == (c.curriculum_id.class_to or c.level_id.class_to)
            )

    @api.depends('class_id')
    def _compute_result_ids(self):
        for wizard in self:
            if not wizard.class_id:
                wizard.result_ids = False
                wizard.message = self.env._('Escolha a turma para ver quem tem a conclusão do curso.')
                continue
            results = self.env['edu.year.result'].search(
                [('class_id', '=', wizard.class_id.id), ('status', 'in', ('graduated', 'promoted'))]
            )
            wizard.result_ids = results
            wizard.message = (
                False
                if results
                else self.env._(
                    'Nenhum aluno da %s tem ainda a conclusão do curso. Aparecem aqui quando o conselho de turma a '
                    'decidir.',
                    wizard.class_id.display_name,
                )
            )

    def action_register_all(self):
        self.ensure_one()
        pending = self.result_ids.filtered(lambda r: not r.graduation_id)
        graduations = self.env['edu.graduation']
        for result in pending:
            graduations |= result._register_graduation()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Conclusões registadas'),
            'res_model': 'edu.graduation',
            'view_mode': 'list,form',
            'domain': [('year_result_id', 'in', self.result_ids.ids)],
        }
