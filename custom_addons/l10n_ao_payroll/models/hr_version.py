from odoo import api, fields, models
from odoo.exceptions import ValidationError

COMPONENT_CODES = [
    ('MEAL', 'Subsídio de alimentação'),
    ('TRANSPORT', 'Subsídio de transporte'),
    ('HOUSING', 'Subsídio de renda de casa'),
    ('FAMILY', 'Abono de família'),
    ('BONUS', 'Gratificação'),
    ('CASH', 'Abono para falhas'),
    ('OTHER', 'Outro'),
]


class L10nAoPayrollComponent(models.Model):
    _name = 'l10n_ao_payroll.component'
    _description = 'Componente fixa da remuneração'
    _order = 'sequence, id'

    version_id = fields.Many2one('hr.version', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='version_id.company_id', store=True)
    currency_id = fields.Many2one(related='version_id.currency_id')
    sequence = fields.Integer(default=10)
    code = fields.Selection(COMPONENT_CODES, required=True, default='MEAL')
    name = fields.Char(
        string='Designação', compute='_compute_name', store=True, readonly=False, required=True, precompute=True
    )
    amount = fields.Monetary(string='Valor mensal', required=True)
    subject_irt = fields.Boolean(
        string='Sujeito a IRT',
        compute='_compute_subject',
        store=True,
        readonly=False,
        precompute=True,
        help='Alimentação e transporte: isentos até 30 000 Kz cada (CIRT, art. 2.º). Renda de casa e abono para '
        'falhas: tributados. Abono de família: isento até 5% do salário base.',
    )
    subject_inss = fields.Boolean(
        string='Sujeito a INSS',
        compute='_compute_subject',
        store=True,
        readonly=False,
        precompute=True,
        help='DP n.º 227/18: todas as prestações pecuniárias, excepto o subsídio de férias e as prestações sociais.',
    )
    proportional = fields.Boolean(
        string='Proporcional aos dias', default=True, help='Reduzido quando o contrato não cobre o mês inteiro.'
    )

    @api.depends('code')
    def _compute_name(self):
        names = dict(COMPONENT_CODES)
        for component in self:
            if not component.name or component.name in names.values():
                component.name = names.get(component.code, component.name)

    @api.depends('code')
    def _compute_subject(self):
        for component in self:
            component.subject_irt = component.code not in ('MEAL', 'TRANSPORT', 'FAMILY')
            component.subject_inss = component.code != 'FAMILY'

    @api.constrains('amount')
    def _check_amount(self):
        for component in self:
            if component.amount < 0:
                raise ValidationError(self.env._('O valor da componente não pode ser negativo.'))


class HrVersion(models.Model):
    _inherit = 'hr.version'

    l10n_ao_payroll_component_ids = fields.One2many(
        'l10n_ao_payroll.component', 'version_id', string='Componentes da remuneração', groups='hr.group_hr_user'
    )
    l10n_ao_payroll_bank_account_id = fields.Many2one(
        'res.partner.bank',
        string='Conta bancária (salário)',
        groups='hr.group_hr_user',
        help='Por omissão, a conta bancária do trabalhador.',
    )
