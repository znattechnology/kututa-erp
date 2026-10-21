from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    l10n_ao_payroll_vacation_subsidy_year = fields.Integer(
        string='Subsídio de férias pago (ano)',
        groups='hr.group_hr_user',
        copy=False,
        help='Último ano em que o subsídio de férias foi pago na folha.',
    )
    l10n_ao_payroll_payslip_ids = fields.One2many('l10n_ao_payroll.payslip', 'employee_id', string='Recibos de salário')
    l10n_ao_payroll_advance_ids = fields.One2many('l10n_ao_payroll.advance', 'employee_id', string='Adiantamentos')

    def _l10n_ao_payroll_version_for(self, date_from, date_to):
        """Contrato em vigor no mês: a versão mais recente cujo contrato toca o período."""
        self.ensure_one()
        versions = self.sudo().version_ids.filtered(
            lambda v: (
                v.contract_date_start
                and v.contract_date_start <= date_to
                and (not v.contract_date_end or v.contract_date_end >= date_from)
            )
        )
        if self.departure_date and self.departure_date < date_from:
            return self.env['hr.version']
        return max(versions, key=lambda v: v.date_version) if versions else self.env['hr.version']
