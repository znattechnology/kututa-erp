from odoo import api, fields, models

LINE = 'edu.enrollment.confirmation.line'


class EduEnrollmentConfirmation(models.TransientModel):
    """A confirmação de matrículas da secretaria: os alunos separados pelo que lhes cabe (pendentes, a confirmar,
    confirmados e fora da confirmação), cada grupo com a sua contagem."""

    _inherit = 'edu.enrollment.confirmation'

    edu_pending_line_ids = fields.One2many(LINE, 'wizard_id', domain=[('state', '=', 'pending')], string='Pendentes')
    edu_confirm_line_ids = fields.One2many(LINE, 'wizard_id', domain=[('state', '=', 'confirm')], string='A confirmar')
    edu_done_line_ids = fields.One2many(LINE, 'wizard_id', domain=[('state', '=', 'done')], string='Confirmadas')
    edu_excluded_line_ids = fields.One2many(
        LINE, 'wizard_id', domain=[('state', '=', 'excluded')], string='Fora da confirmação'
    )
    edu_pending_count = fields.Integer(compute='_compute_edu_counts')
    edu_confirm_count = fields.Integer(compute='_compute_edu_counts')
    edu_done_count = fields.Integer(compute='_compute_edu_counts')
    edu_excluded_count = fields.Integer(compute='_compute_edu_counts')
    edu_years_label = fields.Char(compute='_compute_edu_years_label')

    @api.depends('line_ids.state')
    def _compute_edu_counts(self):
        for wizard in self:
            states = wizard.line_ids.mapped('state')
            for state in ('pending', 'confirm', 'done', 'excluded'):
                wizard[f'edu_{state}_count'] = states.count(state)

    @api.depends('source_year_id', 'target_year_id', 'classes_created')
    def _compute_edu_years_label(self):
        for wizard in self:
            label = self.env._(
                'De %(from_year)s para %(to_year)s',
                from_year=wizard.source_year_id.name or '',
                to_year=wizard.target_year_id.name or '',
            )
            if wizard.classes_created:
                label += self.env._(', com %s turmas novas', wizard.classes_created)
            wizard.edu_years_label = label
