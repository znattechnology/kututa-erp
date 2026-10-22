from odoo import api, fields, models
from odoo.exceptions import UserError


class EduAbsenceJustify(models.TransientModel):
    """Justifica de uma vez as faltas injustificadas de um aluno num período (um atestado de vários dias, por
    exemplo). Só a secretaria e o director de turma justificam."""

    _name = 'edu.absence.justify'
    _description = 'Justificar as faltas de um período'

    student_id = fields.Many2one('edu.student', string='Aluno', required=True)
    date_from = fields.Date(string='De', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Até', required=True, default=fields.Date.context_today)
    justification = fields.Char(string='Motivo da justificação', required=True)
    line_ids = fields.Many2many('edu.lesson.attendance', string='Faltas a justificar', compute='_compute_line_ids')

    @api.depends('student_id', 'date_from', 'date_to')
    def _compute_line_ids(self):
        for wizard in self:
            wizard.line_ids = wizard._lines()

    def _lines(self):
        self.ensure_one()
        if not (self.student_id and self.date_from and self.date_to):
            return self.env['edu.lesson.attendance']
        return self.env['edu.lesson.attendance'].search(
            [
                ('student_id', '=', self.student_id.id),
                ('state', '=', 'absent'),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ],
            order='date, id',
        )

    def action_justify(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(self.env._('A data final é anterior à inicial.'))
        lines = self._lines()
        if not lines:
            raise UserError(self.env._('%s não tem faltas injustificadas nesse período.', self.student_id.name))
        lines._check_can_justify()
        lines.write({'justification': self.justification, 'state': 'excused'})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Faltas justificadas'),
            'res_model': 'edu.lesson.attendance',
            'view_mode': 'list',
            'domain': [('id', 'in', lines.ids)],
        }
