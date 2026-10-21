from odoo import fields, models


class EduEnrollmentDrop(models.TransientModel):
    _name = 'edu.enrollment.drop'
    _description = 'Anulação de matrícula'

    enrollment_ids = fields.Many2many('edu.enrollment', string='Matrículas', required=True)
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    reason = fields.Text(string='Motivo', required=True, help='Obrigatório (MED).')

    def action_confirm(self):
        self.enrollment_ids._drop(self.reason, day=self.date)
        return {'type': 'ir.actions.act_window_close'}
