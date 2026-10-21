from odoo import fields, models
from odoo.exceptions import UserError

from ..tools.payroll_calc import Settings

DEFAULT_ACCOUNTS = {
    'l10n_ao_payroll_expense_account_id': '72.2',
    'l10n_ao_payroll_employer_account_id': '72.5.2',
    'l10n_ao_payroll_payable_account_id': '36.1.2',
    'l10n_ao_payroll_irt_account_id': '34.3.1',
    'l10n_ao_payroll_inss_account_id': '34.9.1',
    'l10n_ao_payroll_advance_account_id': '36.3',
}
JOURNAL_CODE = 'SAL'


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ao_payroll_inss_employee_pct = fields.Float(string='INSS do trabalhador (%)', default=3.0, digits=(5, 2))
    l10n_ao_payroll_inss_employer_pct = fields.Float(
        string='INSS da entidade empregadora (%)', default=8.0, digits=(5, 2)
    )
    l10n_ao_payroll_meal_cap = fields.Monetary(
        string='Subsídio de alimentação isento de IRT até',
        default=30000.0,
        currency_field='currency_id',
        help='CIRT, art. 2.º: até 30 000 Kz por mês não é sujeito a IRT (o INSS incide sobre o total).',
    )
    l10n_ao_payroll_transport_cap = fields.Monetary(
        string='Subsídio de transporte isento de IRT até', default=30000.0, currency_field='currency_id'
    )
    l10n_ao_payroll_vacation_pct = fields.Float(
        string='Subsídio de férias (% do salário base)', default=50.0, digits=(5, 2)
    )
    l10n_ao_payroll_christmas_pct = fields.Float(
        string='Subsídio de Natal (% do salário base)', default=50.0, digits=(5, 2)
    )
    l10n_ao_payroll_christmas_month = fields.Integer(string='Mês do subsídio de Natal', default=12)
    l10n_ao_payroll_min_wage = fields.Monetary(
        string='Salário mínimo nacional',
        default=100000.0,
        currency_field='currency_id',
        help='DP n.º 152/24: 100 000 Kz desde Setembro de 2025 (50 000 Kz nas micro-empresas e startups).',
    )
    l10n_ao_payroll_journal_id = fields.Many2one('account.journal', string='Diário de salários', check_company=True)
    l10n_ao_payroll_expense_account_id = fields.Many2one(
        'account.account', string='Remunerações (72.2)', check_company=True
    )
    l10n_ao_payroll_employer_account_id = fields.Many2one(
        'account.account', string='Encargos sobre remunerações (72.5.2)', check_company=True
    )
    l10n_ao_payroll_payable_account_id = fields.Many2one(
        'account.account', string='Remunerações a pagar (36.1.2)', check_company=True
    )
    l10n_ao_payroll_irt_account_id = fields.Many2one(
        'account.account', string='IRT retido (34.3.1)', check_company=True
    )
    l10n_ao_payroll_inss_account_id = fields.Many2one(
        'account.account', string='INSS a entregar (34.9.1)', check_company=True
    )
    l10n_ao_payroll_advance_account_id = fields.Many2one(
        'account.account', string='Adiantamentos ao pessoal (36.3)', check_company=True
    )

    def _l10n_ao_payroll_settings(self, day):
        self.ensure_one()
        return Settings(
            inss_employee_pct=self.l10n_ao_payroll_inss_employee_pct,
            inss_employer_pct=self.l10n_ao_payroll_inss_employer_pct,
            vacation_subsidy_pct=self.l10n_ao_payroll_vacation_pct,
            christmas_subsidy_pct=self.l10n_ao_payroll_christmas_pct,
            irt_brackets=self.env['l10n_ao_payroll.irt.bracket']._brackets_for(day),
        )

    def _l10n_ao_payroll_ensure_accounting(self):
        """Preenche o diário e as contas do PGC por omissão, se faltarem."""
        self.ensure_one()
        Account = self.env['account.account'].with_company(self)
        for field_name, code in DEFAULT_ACCOUNTS.items():
            if not self[field_name]:
                account = Account.search([('code', '=', code), ('company_ids', 'in', self.id)], limit=1)
                if not account:
                    raise UserError(
                        self.env._(
                            'Falta a conta %(code)s do PGC na empresa %(company)s.', code=code, company=self.name
                        )
                    )
                self[field_name] = account
        if not self.l10n_ao_payroll_journal_id:
            Journal = self.env['account.journal']
            journal = Journal.search(
                [('company_id', '=', self.id), ('code', '=', JOURNAL_CODE), ('type', '=', 'general')], limit=1
            )
            self.l10n_ao_payroll_journal_id = journal or Journal.create(
                {'name': 'Salários', 'code': JOURNAL_CODE, 'type': 'general', 'company_id': self.id}
            )
