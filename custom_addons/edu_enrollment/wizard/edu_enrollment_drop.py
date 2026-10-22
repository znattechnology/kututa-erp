from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.edu_enrollment import DROP_REASONS, DROP_REQUESTERS, JUSTIFIED_REASONS, OFFICIAL_REASONS


class EduEnrollmentDrop(models.TransientModel):
    """Anulação de matrícula (DP 162/23, art. 28.º): quem pede, o motivo da lei e se é justificada; a pedido, só até ao
    prazo (fim do II trimestre no ensino geral, 5.º dia útil do III trimestre no técnico) — depois, só a direcção. A
    anulação oficiosa (processo incompleto, declarações falsas) não tem prazo."""

    _name = 'edu.enrollment.drop'
    _description = 'Anulação de matrícula'

    enrollment_ids = fields.Many2many('edu.enrollment', string='Matrículas', required=True)
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    requested_by = fields.Selection(DROP_REQUESTERS, string='Pedida por', required=True, default='guardian')
    reason_code = fields.Selection(DROP_REASONS, string='Motivo', required=True)
    justified = fields.Boolean(
        string='Anulação justificada',
        compute='_compute_justified',
        store=True,
        readonly=False,
        help='Doença, mudança de residência ou actividades oficiais (art. 28.º, n.º 4): no II Ciclo, dá direito a '
        'exames especiais.',
    )
    reason = fields.Text(string='Observações', help='Documentos entregues, pormenores do pedido.')
    warnings = fields.Text(string='Atenção', compute='_compute_warnings')

    @api.depends('reason_code')
    def _compute_justified(self):
        for wizard in self:
            wizard.justified = wizard.reason_code in JUSTIFIED_REASONS

    @api.onchange('reason_code')
    def _onchange_reason_code(self):
        if self.reason_code in OFFICIAL_REASONS:
            self.requested_by = 'school'

    @api.depends('enrollment_ids', 'date', 'requested_by')
    def _compute_warnings(self):
        for wizard in self:
            lines = []
            for enrollment in wizard.enrollment_ids:
                deadline = enrollment._drop_deadline()
                if deadline and wizard.date and wizard.date > deadline and wizard.requested_by != 'school':
                    lines.append(
                        self.env._(
                            '%(student)s: fora do prazo de anulação (até %(deadline)s). Só a direcção pode anular.',
                            student=enrollment.student_id.name,
                            deadline=deadline.strftime('%d/%m/%Y'),
                        )
                    )
                lines += [f'{enrollment.student_id.name}: {text}' for text in enrollment._edu_drop_warnings()]
            wizard.warnings = '\n'.join(lines) or False

    def action_confirm(self):
        self.ensure_one()
        manager = self.env.user.has_group('edu_core.group_edu_manager')
        for enrollment in self.enrollment_ids:
            deadline = enrollment._drop_deadline()
            late = deadline and self.date > deadline and self.requested_by != 'school'
            if late and not manager:
                raise UserError(
                    self.env._(
                        'A anulação de %(student)s está fora do prazo (até %(deadline)s): só a direcção a pode fazer.',
                        student=enrollment.student_id.name,
                        deadline=deadline.strftime('%d/%m/%Y'),
                    )
                )
        if self.reason_code in OFFICIAL_REASONS and self.requested_by != 'school':
            raise UserError(self.env._('Este motivo é de anulação oficiosa: é a escola que anula.'))
        self.enrollment_ids._drop(
            self.reason,
            day=self.date,
            reason_code=self.reason_code,
            requested_by=self.requested_by,
            justified=self.justified,
        )
        return {'type': 'ir.actions.act_window_close'}
