from datetime import datetime, time

from odoo import api, fields, models
from odoo.addons.l10n_ao_hr.models.hr_employee import seniority_years
from odoo.exceptions import UserError

from ..tools.payroll_calc import hourly_rate, round2, seniority_compensation

# Motivo de cessação (xmlid do l10n_ao_hr) -> artigo da compensação.
COMPENSATION_BY_REASON = {
    'l10n_ao_hr.departure_ao_expiry': 'art307',
    'l10n_ao_hr.departure_ao_objective': 'art308',
    'l10n_ao_hr.departure_ao_collective': 'art308',
    'l10n_ao_hr.departure_ao_unlawful': 'art309',
    'l10n_ao_hr.departure_ao_constructive': 'art310',
}
# Saída por iniciativa do trabalhador: o aviso prévio em falta é ele que o deve (arts. 305.º e 306.º).
EMPLOYEE_NOTICE_REASONS = ('l10n_ao_hr.departure_ao_resignation', 'l10n_ao_hr.departure_ao_abandonment')
ANNUAL_VACATION_DAYS = 22


def full_months_in_year(admission, end):
    """Meses completos de trabalho no ano de ``end``: desde Janeiro (ou do primeiro mês completo após a
    admissão) até ao último mês terminado na data de cessação."""
    first = 1
    if admission and admission.year == end.year:
        first = admission.month if admission.day == 1 else admission.month + 1
    elif admission and admission.year > end.year:
        return 0
    last = end.month if end == fields.Date.end_of(end, 'month') else end.month - 1
    return max(0, min(last - first + 1, 12))


class L10nAoPayrollTermination(models.TransientModel):
    _name = 'l10n_ao_payroll.termination'
    _description = 'Contas finais na cessação do contrato (LGT, arts. 307.º a 311.º)'

    employee_id = fields.Many2one('hr.employee', string='Trabalhador', required=True)
    company_id = fields.Many2one(related='employee_id.company_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(string='Data da cessação', required=True, default=fields.Date.context_today)
    departure_reason_id = fields.Many2one(
        'hr.departure.reason', string='Modalidade', required=True, domain="[('country_id.code', 'in', ('AO', False))]"
    )
    base_salary = fields.Monetary(string='Salário base', compute='_compute_defaults', store=True, readonly=False)
    weekly_hours = fields.Float(string='Horas semanais', compute='_compute_defaults', store=True, readonly=False)
    seniority_years = fields.Integer(
        string='Antiguidade (anos, art. 311.º)', compute='_compute_defaults', store=True, readonly=False
    )
    compensation_article = fields.Selection(
        [
            ('none', 'Sem compensação'),
            ('art307', 'Art. 307.º: 50% do salário base por ano'),
            ('art308', 'Art. 308.º: 1 salário por ano até 5 e 50% acima'),
            ('art309', 'Art. 309.º: 50% do salário base por ano'),
            ('art310', 'Art. 310.º: 1 salário por ano, mínimo 3'),
        ],
        string='Regime da compensação',
        compute='_compute_defaults',
        store=True,
        readonly=False,
    )
    missing_notice = fields.Boolean(
        string='Sem aviso prévio de 30 dias',
        help='Não renovação ou despedimento sem o aviso prévio: acresce um mês de salário (arts. 17.º e 285.º). '
        'Na denúncia e no abandono, o trabalhador deve esse valor e ele é descontado (arts. 305.º e 306.º).',
    )
    notice_by_employee = fields.Boolean(compute='_compute_defaults', store=True)
    vacation_days_due = fields.Float(
        string='Férias vencidas não gozadas (dias)',
        compute='_compute_defaults',
        store=True,
        readonly=False,
        help='Férias do ano anterior ainda não gozadas (art. 212.º).',
    )
    vacation_days_proportional = fields.Float(
        string='Férias proporcionais (dias)',
        compute='_compute_defaults',
        store=True,
        readonly=False,
        help='2 dias por mês completo de trabalho no ano da cessação, até 22 (art. 212.º).',
    )
    vacation_subsidy_paid = fields.Boolean(
        string='Subsídio de férias já pago este ano', compute='_compute_defaults', store=True, readonly=False
    )
    months_worked = fields.Integer(
        string='Meses trabalhados no ano', compute='_compute_defaults', store=True, readonly=False
    )
    compensation_amount = fields.Monetary(string='Compensação', compute='_compute_amounts')
    notice_amount = fields.Monetary(string='Aviso prévio em falta', compute='_compute_amounts')
    vacation_amount = fields.Monetary(string='Férias não gozadas', compute='_compute_amounts')
    vacation_subsidy_amount = fields.Monetary(string='Subsídio de férias', compute='_compute_amounts')
    christmas_amount = fields.Monetary(string='Subsídio de Natal proporcional', compute='_compute_amounts')
    total_amount = fields.Monetary(string='Total das contas finais (bruto)', compute='_compute_amounts')

    @api.depends('employee_id', 'date', 'departure_reason_id')
    def _compute_defaults(self):
        for wizard in self:
            employee = wizard.employee_id
            version = employee.version_id if employee else self.env['hr.version']
            wizard.base_salary = version.wage
            wizard.weekly_hours = version.l10n_ao_weekly_hours or 44.0
            wizard.seniority_years = seniority_years(employee.l10n_ao_admission_date, wizard.date) if employee else 0
            xmlid = (
                wizard.departure_reason_id.get_external_id().get(wizard.departure_reason_id.id, '')
                if wizard.departure_reason_id
                else ''
            )
            wizard.compensation_article = COMPENSATION_BY_REASON.get(xmlid, 'none')
            wizard.notice_by_employee = xmlid in EMPLOYEE_NOTICE_REASONS
            admission = employee.l10n_ao_admission_date if employee else None
            wizard.months_worked = full_months_in_year(admission, wizard.date) if admission and wizard.date else 0
            wizard.vacation_days_proportional = min(ANNUAL_VACATION_DAYS, 2 * wizard.months_worked)
            wizard.vacation_days_due = wizard._vacation_days_due()
            wizard.vacation_subsidy_paid = bool(employee) and employee.l10n_ao_payroll_vacation_subsidy_year >= (
                wizard.date.year if wizard.date else 0
            )

    def _vacation_days_due(self):
        """Férias do ano anterior ainda por gozar: 22 (se o trabalhador já tinha um ano) menos as gozadas no ano."""
        self.ensure_one()
        employee = self.employee_id
        if not employee or not self.date or not employee.l10n_ao_admission_date:
            return 0.0
        if employee.l10n_ao_admission_date.year >= self.date.year:
            return 0.0
        vacation = self.env.ref('l10n_ao_hr.work_entry_type_ao_ferias', raise_if_not_found=False)
        if not vacation:
            return 0.0
        taken = sum(
            self.env['hr.leave']
            .search(
                [
                    ('employee_id', '=', employee.id),
                    ('work_entry_type_id', '=', vacation.id),
                    ('state', '=', 'validate'),
                    (
                        'date_from',
                        '>=',
                        fields.Datetime.to_string(datetime.combine(self.date.replace(month=1, day=1), time.min)),
                    ),
                    ('date_from', '<=', fields.Datetime.to_string(datetime.combine(self.date, time.max))),
                ]
            )
            .mapped('number_of_days')
        )
        return max(ANNUAL_VACATION_DAYS - taken, 0.0)

    @api.depends(
        'base_salary', 'weekly_hours', 'seniority_years', 'compensation_article', 'missing_notice',
        'notice_by_employee', 'vacation_days_due', 'vacation_days_proportional', 'vacation_subsidy_paid',
        'months_worked',
    )  # fmt: skip
    def _compute_amounts(self):
        for wizard in self:
            company = wizard.company_id
            wizard.compensation_amount = seniority_compensation(
                wizard.compensation_article, wizard.base_salary, wizard.seniority_years
            )
            notice = seniority_compensation('notice', wizard.base_salary, 0) if wizard.missing_notice else 0.0
            wizard.notice_amount = -notice if wizard.notice_by_employee else notice
            daily = hourly_rate(wizard.base_salary, wizard.weekly_hours) * wizard.weekly_hours / 5
            wizard.vacation_amount = round2((wizard.vacation_days_due + wizard.vacation_days_proportional) * daily)
            # Subsídio de férias: o das férias vencidas, se ainda não foi pago, mais o proporcional do ano (art. 238.º).
            vacation_pct = company.l10n_ao_payroll_vacation_pct or 50.0
            vested = 1.0 if wizard.vacation_days_due and not wizard.vacation_subsidy_paid else 0.0
            wizard.vacation_subsidy_amount = round2(
                wizard.base_salary * vacation_pct / 100 * (vested + wizard.months_worked / 12)
            )
            christmas_pct = company.l10n_ao_payroll_christmas_pct or 50.0
            wizard.christmas_amount = round2(wizard.base_salary * christmas_pct / 100 * wizard.months_worked / 12)
            wizard.total_amount = (
                wizard.compensation_amount
                + wizard.notice_amount
                + wizard.vacation_amount
                + wizard.vacation_subsidy_amount
                + wizard.christmas_amount
            )

    def action_confirm(self):
        """Regista a saída e cria o recibo de contas finais na folha do mês da cessação."""
        self.ensure_one()
        employee = self.employee_id
        if employee.departure_id and employee.departure_date and employee.departure_date != self.date:
            raise UserError(self.env._('O trabalhador já tem uma saída registada em %s.', employee.departure_date))
        if not employee.departure_id:
            self.env['hr.employee.departure'].create(
                {
                    'employee_id': employee.id,
                    'departure_reason_id': self.departure_reason_id.id,
                    'departure_date': self.date,
                    'dismissal_date': self.date,
                }
            )
        run = self.env['l10n_ao_payroll.run'].search(
            [
                ('company_id', '=', self.company_id.id),
                ('year', '=', self.date.year),
                ('month', '=', str(self.date.month)),
            ],
            limit=1,
        )
        if not run:
            run = self.env['l10n_ao_payroll.run'].create(
                {'company_id': self.company_id.id, 'year': self.date.year, 'month': str(self.date.month)}
            )
        if run.state == 'cancelled':
            raise UserError(self.env._('A folha de %s está anulada: reponha-a em rascunho primeiro.', run.name))
        if run.state == 'closed':
            raise UserError(
                self.env._('A folha de %s já está fechada: as contas finais vão para a folha seguinte.', run.name)
            )
        slip = run.payslip_ids.filtered(lambda s: s.employee_id == employee and s.state == 'draft')
        if not slip:
            slip = self.env['l10n_ao_payroll.payslip'].create({'run_id': run.id, 'employee_id': employee.id})
        extras = []
        if self.compensation_amount:
            label = dict(self._fields['compensation_article'].selection)[self.compensation_article]
            extras.append(
                (
                    'COMPENSATION',
                    f'Compensação por cessação ({label.split(":")[0]})',
                    self.compensation_amount,
                    True,
                    False,
                )
            )
        if self.notice_amount > 0:
            extras.append(('NOTICE', 'Falta de aviso prévio (30 dias)', self.notice_amount, True, False))
        elif self.notice_amount < 0:
            # Valor devido pelo trabalhador: o motor trata-o como desconto, fora do IRT e do INSS.
            extras.append(('NOTICE', 'Aviso prévio em falta (30 dias)', self.notice_amount, False, False))
        if self.vacation_amount:
            days = self.vacation_days_due + self.vacation_days_proportional
            extras.append(('VACATION_PAY', f'Férias não gozadas ({days:g} dias)', self.vacation_amount, True, True))
        if self.vacation_subsidy_amount:
            # Fora do INSS, como o subsídio de férias mensal (DP 227/18, art. 13.º, n.º 3, al. b)).
            extras.append(('VACATION', 'Subsídio de férias (contas finais)', self.vacation_subsidy_amount, True, False))
        if self.christmas_amount:
            extras.append(
                ('CHRISTMAS', f'Subsídio de Natal ({self.months_worked}/12)', self.christmas_amount, True, True)
            )
        slip.write(
            {
                'kind': 'final',
                'vacation_subsidy': False,
                'christmas_months': 0,
                'extra_line_ids': [fields.Command.clear()]
                + [
                    fields.Command.create(
                        {'code': code, 'name': name, 'amount': amount, 'subject_irt': irt, 'subject_inss': inss}
                    )
                    for code, name, amount, irt, inss in extras
                ],
            }
        )
        slip.action_compute()
        if run.state == 'draft':
            run.state = 'computed'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao_payroll.payslip',
            'res_id': slip.id,
            'view_mode': 'form',
        }
