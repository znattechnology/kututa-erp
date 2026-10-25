import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError

CARD_STATES = [
    ('ready', 'Pronto a imprimir'),
    ('awaiting', 'Aguarda pagamento'),
    ('issued', 'Emitido'),
    ('none', 'Sem pedido'),
]
PAID = ('paid', 'in_payment')


class EduStudentCard(models.Model):
    """Cartão de estudante, como no secPed: a tesouraria cobra a taxa do cartão e regista o pagamento; a secretaria só
    emite (imprime) com uma factura do cartão paga e ainda sem cartão — cada pagamento dá um cartão — e com a
    fotografia do aluno. Uma nova emissão revoga o cartão activo (é a 2.ª via, que se paga outra vez). O cartão vale
    até ao fim do ano lectivo; o código vai no QR, para a portaria verificar."""

    _name = 'edu.student.card'
    _description = 'Cartão de estudante'
    _order = 'issue_date desc, id desc'
    _rec_name = 'code'

    code = fields.Char(
        string='Código', required=True, readonly=True, copy=False, index=True,
        default=lambda self: uuid.uuid4().hex[:12].upper(),
    )  # fmt: skip
    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='student_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one('edu.academic.year', string='Ano lectivo', readonly=True)
    state = fields.Selection(
        [('active', 'Activo'), ('revoked', 'Revogado')], string='Estado', default='active', required=True
    )
    invoice_id = fields.Many2one(
        'account.move', string='Factura da taxa', required=True, readonly=True, ondelete='restrict'
    )
    issued_by_id = fields.Many2one('res.users', string='Emitido por', readonly=True, default=lambda self: self.env.user)
    issue_date = fields.Datetime(string='Emitido em', readonly=True, default=fields.Datetime.now)
    expiry_date = fields.Date(string='Válido até', readonly=True)
    revoke_date = fields.Datetime(string='Revogado em', readonly=True)
    revoke_reason = fields.Char(string='Motivo da revogação', readonly=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'O código do cartão já existe.')
    _invoice_uniq = models.Constraint('UNIQUE(invoice_id)', 'Este pagamento já deu um cartão.')

    def _revoke(self, reason):
        self.filtered(lambda c: c.state == 'active').write(
            {'state': 'revoked', 'revoke_date': fields.Datetime.now(), 'revoke_reason': reason}
        )


class EduStudent(models.Model):
    _inherit = 'edu.student'

    edu_card_ids = fields.One2many('edu.student.card', 'student_id', string='Cartões')
    edu_card_id = fields.Many2one('edu.student.card', string='Cartão activo', compute='_compute_edu_card_state')
    edu_card_state = fields.Selection(
        CARD_STATES, string='Cartão', compute='_compute_edu_card_state', store=True, index=True,
        group_expand='_edu_expand_card_states',
    )  # fmt: skip
    edu_card_revoked = fields.Boolean(string='Já teve cartão', compute='_compute_edu_card_state')
    edu_card_expiry = fields.Date(related='edu_card_id.expiry_date', string='Cartão válido até')

    def _edu_card_invoices(self):
        return self.sudo().edu_invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted' and m.edu_category == 'card'
        )

    def _edu_card_payable_invoice(self):
        """A factura do cartão paga e ainda sem cartão: a «senha» da impressão."""
        self.ensure_one()
        used = self.sudo().edu_card_ids.invoice_id
        return self._edu_card_invoices().filtered(lambda m: m.payment_state in PAID and m not in used)[:1]

    @api.depends(
        'edu_card_ids.state',
        'edu_invoice_ids.state',
        'edu_invoice_ids.payment_state',
        'edu_invoice_ids.edu_category',
    )
    def _compute_edu_card_state(self):
        for student in self:
            cards = student.sudo().edu_card_ids
            active = cards.filtered(lambda c: c.state == 'active')[:1]
            student.edu_card_id = active
            student.edu_card_revoked = bool(cards - active)
            if active:
                state = 'issued'
            elif student._edu_card_payable_invoice():
                state = 'ready'
            elif student._edu_card_invoices().filtered(lambda m: m.payment_state not in PAID + ('reversed',)):
                state = 'awaiting'
            else:
                state = 'none'
            student.edu_card_state = state

    def _edu_expand_card_states(self, states, domain):
        return [state for state, _label in CARD_STATES]

    def action_edu_issue_card(self):
        """Emite o cartão e abre a impressão. Sem fotografia ou sem a taxa paga, recusa e diz o que falta."""
        self.ensure_one()
        if not self.image_1920:
            raise UserError(
                self.env._('%s ainda não tem fotografia: junte a foto na ficha do aluno antes de emitir.', self.name)
            )
        invoice = self._edu_card_payable_invoice()
        if not invoice:
            raise UserError(
                self.env._(
                    'A taxa do cartão de %s ainda não está paga: o aluno paga primeiro na tesouraria.', self.name
                )
            )
        year = self.company_id.edu_current_year_id
        Card = self.env['edu.student.card'].sudo()
        Card.search([('student_id', '=', self.id), ('state', '=', 'active')])._revoke(
            self.env._('Substituído por nova emissão')
        )
        Card.create(
            {
                'student_id': self.id,
                'academic_year_id': year.id,
                'invoice_id': invoice.id,
                'issued_by_id': self.env.uid,
                'expiry_date': year.date_end,
            }
        )
        return self.action_edu_print_card()

    def action_edu_print_card(self):
        return self.env.ref('edu_documents.action_report_student_card').report_action(self)

    def action_edu_charge_card(self):
        """A tesouraria cobra a taxa do cartão: o serviço «Cartão de estudante» do plano do aluno."""
        self.ensure_one()
        enrollment = self.current_enrollment_id
        plan = enrollment and self.env['edu.fee.plan']._for_enrollment(enrollment)
        line = plan and plan.line_ids.filtered(lambda line: line.category == 'card')[:1]
        if not line:
            raise UserError(self.env._('O plano de propinas do aluno não tem a taxa do cartão de estudante.'))
        action = self.action_charge_service()
        action['context'] = {**action['context'], 'default_fee_line_id': line.id}
        return action

    def action_edu_revoke_card(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Revogar o cartão'),
            'res_model': 'edu.student.card.revoke',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_student_id': self.id},
        }


class ReportStudentCard(models.AbstractModel):
    _inherit = 'report.edu_documents.report_student_card'

    def _extra_values(self, docs):
        """Só se imprime o cartão emitido: quem não o tem passa por «Emitir cartão» (taxa paga e fotografia)."""
        missing = docs.filtered(lambda s: not s.edu_card_id)
        if missing:
            raise UserError(
                self.env._(
                    'Sem cartão emitido: %s. Emita-o primeiro em «Cartão de estudante».',
                    ', '.join(missing[:5].mapped('name')) + ('…' if len(missing) > 5 else ''),
                )
            )
        return super()._extra_values(docs)
