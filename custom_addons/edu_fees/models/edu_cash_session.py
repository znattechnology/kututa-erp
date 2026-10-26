from odoo import api, fields, models
from odoo.exceptions import UserError


class EduCashSession(models.Model):
    """A caixa de quem recebe numerário, como no secPed: abre-se no início do turno e, no fim, conta-se o dinheiro e
    declara-se sem ver o esperado. O esperado é o numerário que esse utilizador registou na janela (os pagamentos em
    diários de caixa e os pagamentos em numerário que mandou aprovar e foram aprovados); a diferença aparece no próprio
    dia e, se houver, a direcção é avisada. Negativa: falta dinheiro face ao registado."""

    _name = 'edu.cash.session'
    _description = 'Caixa'
    _inherit = ['mail.thread']
    _order = 'opened_at desc, id desc'
    _check_company_auto = True

    operator_id = fields.Many2one('res.users', string='Operador', required=True, readonly=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, readonly=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    opened_at = fields.Datetime(string='Aberta em', required=True, readonly=True, default=fields.Datetime.now)
    closed_at = fields.Datetime(string='Fechada em', readonly=True, index=True)
    declared_amount = fields.Monetary(string='Contado', readonly=True)
    expected_amount = fields.Monetary(string='Registado', readonly=True)
    difference = fields.Monetary(string='Diferença', readonly=True, help='Contado menos registado.')
    notes = fields.Text(string='Observações', readonly=True)
    state = fields.Selection(
        [('open', 'Aberta'), ('closed', 'Fechada')], string='Estado', default='open', required=True, readonly=True
    )

    @api.model
    def _current(self, user=None):
        user = user or self.env.user
        return self.search(
            [('operator_id', '=', user.id), ('company_id', '=', self.env.company.id), ('state', '=', 'open')], limit=1
        )

    @api.model
    def _open(self):
        """Abre a caixa do utilizador (uma de cada vez: com uma aberta, devolve essa)."""
        return self._current() or self.sudo().create({'operator_id': self.env.uid}).sudo(False)

    def _expected(self, until):
        """O numerário que o operador registou desde que abriu a caixa (pela data de criação, o mesmo relógio da base de
        dados que a dos pagamentos)."""
        self.ensure_one()
        payments = (
            self.env['account.payment']
            .sudo()
            .search(
                [
                    ('company_id', '=', self.company_id.id),
                    ('journal_id.type', '=', 'cash'),
                    ('payment_type', '=', 'inbound'),
                    ('create_uid', '=', self.operator_id.id),
                    ('create_date', '>=', self.create_date),
                    ('create_date', '<=', until),
                    ('state', 'not in', ('draft', 'canceled', 'rejected')),
                ]
            )
        )
        requests = (
            self.env['edu.fee.payment.request']
            .sudo()
            .search(
                [
                    ('company_id', '=', self.company_id.id),
                    ('method', '=', 'cash'),
                    ('submitted_by_id', '=', self.operator_id.id),
                    ('state', '=', 'confirmed'),
                    ('create_date', '>=', self.create_date),
                    ('create_date', '<=', until),
                ]
            )
        )
        # O pagamento de um numerário aprovado é registado por quem aprovou: conta na caixa de quem o recebeu (pelo
        # pedido), não na de quem aprovou.
        approved = (
            self.env['edu.fee.payment.request']
            .sudo()
            .search([('method', '=', 'cash'), ('payment_ids', 'in', payments.ids)])
        )
        payments -= approved.payment_ids
        return self.currency_id.round(sum(payments.mapped('amount')) + sum(requests.mapped('amount')))

    def action_close(self, declared, notes=False):
        self.ensure_one()
        if self.state != 'open' or self.operator_id != self.env.user:
            raise UserError(self.env._('Só quem abriu a caixa a pode fechar.'))
        if declared is None or declared < 0:
            raise UserError(self.env._('Indique o numerário contado.'))
        now = fields.Datetime.now()
        expected = self._expected(now)
        difference = self.currency_id.round(declared - expected)
        self.sudo().write(
            {
                'state': 'closed',
                'closed_at': now,
                'declared_amount': declared,
                'expected_amount': expected,
                'difference': difference,
                'notes': notes or False,
            }
        )
        if not self.currency_id.is_zero(difference):
            managers = self.env.ref('edu_core.group_edu_manager').user_ids.partner_id
            self.sudo().message_post(
                body=self.env._(
                    'Caixa de %(operator)s fechada com uma diferença de %(difference)s (contado %(declared)s, '
                    'registado %(expected)s).',
                    operator=self.operator_id.name,
                    difference=self.currency_id.format(difference),
                    declared=self.currency_id.format(declared),
                    expected=self.currency_id.format(expected),
                ),
                partner_ids=managers.ids,
                subtype_xmlid='mail.mt_comment',
            )
        return True
