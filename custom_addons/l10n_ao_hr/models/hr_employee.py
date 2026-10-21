from odoo import api, fields, models


def seniority_years(start, end):
    """Anos de antiguidade (LGT, art. 311.º): uma fracção igual ou superior a 3 meses conta como um ano."""
    if not start or not end or end < start:
        return 0
    years = end.year - start.year
    months = end.month - start.month
    if end.day < start.day:
        months -= 1
    total_months = years * 12 + months
    full_years, rest = divmod(total_months, 12)
    return full_years + (1 if rest >= 3 else 0)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    l10n_ao_inss_number = fields.Char(
        string='N.º de segurado (INSS)',
        groups='hr.group_hr_user',
        tracking=True,
        help='Obrigatório no recibo (LGT, art. 247.º).',
    )
    l10n_ao_admission_date = fields.Date(
        string='Data de admissão',
        compute='_compute_l10n_ao_admission_date',
        store=True,
        readonly=False,
        groups='hr.group_hr_user',
        help='Início do primeiro contrato. Conta para a antiguidade (art. 311.º) e para as férias (art. 204.º).',
    )
    l10n_ao_seniority_years = fields.Integer(
        string='Antiguidade (anos)', compute='_compute_l10n_ao_seniority', groups='hr.group_hr_user'
    )
    l10n_ao_overtime_ids = fields.One2many('l10n_ao_hr.overtime', 'employee_id', string='Trabalho extraordinário')
    l10n_ao_sanction_ids = fields.One2many('l10n_ao_hr.sanction', 'employee_id', string='Sanções disciplinares')

    @api.depends('version_ids.contract_date_start')
    def _compute_l10n_ao_admission_date(self):
        for employee in self:
            if employee.l10n_ao_admission_date:
                continue
            starts = employee.version_ids.filtered('contract_date_start').mapped('contract_date_start')
            employee.l10n_ao_admission_date = min(starts) if starts else False

    @api.depends('l10n_ao_admission_date')
    def _compute_l10n_ao_seniority(self):
        today = fields.Date.context_today(self)
        for employee in self:
            end = employee.departure_date if employee.departure_date and employee.departure_date < today else today
            employee.l10n_ao_seniority_years = seniority_years(employee.l10n_ao_admission_date, end)

    def _l10n_ao_seniority_at(self, day):
        self.ensure_one()
        return seniority_years(self.l10n_ao_admission_date, day)
