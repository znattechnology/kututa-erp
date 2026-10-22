from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

TYPES = [
    ('full', 'Integral'),
    ('partial', 'Parcial'),
    ('merit', 'Mérito'),
    ('need', 'Carência económica'),
    ('government', 'Bolsa do Estado'),
    ('institutional', 'Institucional'),
]


class EduScholarship(models.Model):
    """Bolsa ou desconto na propina. Aplica-se só à propina, por data de vencimento; com várias, vale a mais vantajosa.
    O desconto fica fixado na factura emitida (alterar a bolsa não mexe nas facturas já emitidas)."""

    _name = 'edu.scholarship'
    _description = 'Bolsa'
    _inherit = ['mail.thread']
    _order = 'academic_year_id desc, id desc'
    _check_company_auto = True

    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    company_id = fields.Many2one(related='student_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    academic_year_id = fields.Many2one('edu.academic.year', string='Ano lectivo', required=True, check_company=True)
    scholarship_type = fields.Selection(TYPES, string='Tipo', required=True, default='partial', tracking=True)
    type_label = fields.Char(compute='_compute_type_label')
    discount_percent = fields.Float(string='Desconto (%)', tracking=True)
    discount_amount = fields.Monetary(string='Desconto (valor)', tracking=True)
    date_from = fields.Date(string='De', required=True)
    date_to = fields.Date(string='Até')
    state = fields.Selection(
        [('draft', 'Pedida'), ('approved', 'Aprovada'), ('cancelled', 'Anulada')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    requested_by_id = fields.Many2one(
        'res.users', string='Pedida por', default=lambda self: self.env.user, readonly=True
    )
    approved_by_id = fields.Many2one('res.users', string='Aprovada por', readonly=True)
    note = fields.Text(string='Fundamento')

    # As anuladas não contam: depois de anular, pode pedir-se outra do mesmo tipo.
    _student_year_type_active_uniq = models.UniqueIndex(
        "(student_id, academic_year_id, scholarship_type) WHERE state != 'cancelled'",
        'O aluno já tem uma bolsa deste tipo no ano.',
    )

    def init(self):
        self.env.cr.execute(
            'ALTER TABLE edu_scholarship DROP CONSTRAINT IF EXISTS edu_scholarship_student_year_type_uniq'
        )

    @api.depends('scholarship_type')
    def _compute_type_label(self):
        labels = dict(TYPES)
        for scholarship in self:
            scholarship.type_label = labels.get(scholarship.scholarship_type, '')

    @api.constrains('scholarship_type', 'discount_percent', 'discount_amount', 'date_from', 'date_to')
    def _check_values(self):
        for scholarship in self:
            if scholarship.scholarship_type != 'full':
                if not scholarship.discount_percent and not scholarship.discount_amount:
                    raise ValidationError(self.env._('Indique a percentagem ou o valor do desconto.'))
                if scholarship.discount_percent and not 0 < scholarship.discount_percent <= 100:
                    raise ValidationError(self.env._('A percentagem vai de 0 a 100.'))
            if scholarship.date_to and scholarship.date_to < scholarship.date_from:
                raise ValidationError(self.env._('A bolsa termina antes de começar.'))

    def write(self, vals):
        if 'requested_by_id' in vals and not self.env.su:
            vals = {k: v for k, v in vals.items() if k != 'requested_by_id'}  # quem pediu não se escolhe
        locked = {'scholarship_type', 'discount_percent', 'discount_amount', 'date_from', 'date_to', 'student_id'}
        approved = self.filtered(lambda s: s.state == 'approved') if locked & set(vals) else self.browse()
        if approved:
            # Alterar uma bolsa aprovada volta a pedido, em nome de quem a alterou (quatro olhos: outro aprova).
            super(EduScholarship, approved).write(
                {'state': 'draft', 'approved_by_id': False, 'requested_by_id': self.env.uid}
            )
        return super().write(vals)

    def action_approve(self):
        for scholarship in self.filtered(lambda s: s.state == 'draft'):
            if scholarship.company_id.edu_scholarship_approval and scholarship.requested_by_id == self.env.user:
                raise UserError(self.env._('Quem pediu a bolsa não a pode aprovar.'))
            scholarship.write({'state': 'approved', 'approved_by_id': self.env.uid})
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def _discount(self, amount):
        self.ensure_one()
        if self.scholarship_type == 'full':
            return amount
        value = amount * self.discount_percent / 100 if self.discount_percent else self.discount_amount
        return self.currency_id.round(min(max(value, 0.0), amount))

    @api.model
    def _relief(self, student, year, due, amount):
        """(bolsa, desconto): a bolsa aprovada mais vantajosa em vigor na data de vencimento."""
        scholarships = self.search(
            [('student_id', '=', student.id), ('academic_year_id', '=', year.id), ('state', '=', 'approved')]
        ).filtered(lambda s: s.date_from <= due and (not s.date_to or due <= s.date_to))
        best, value = self.browse(), 0.0
        for scholarship in scholarships:
            discount = scholarship._discount(amount)
            if discount > value:
                best, value = scholarship, discount
        return best, value
