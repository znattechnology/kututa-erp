from datetime import timedelta

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

    def _l10n_ao_payroll_segments(self, date_from, date_to):
        """[(versão, início, fim)] no período: cada versão vale desde a sua data até à véspera da seguinte,
        dentro das datas do contrato e até à saída do trabalhador."""
        self.ensure_one()
        end_limit = date_to
        if self.departure_date:
            if self.departure_date < date_from:
                return []
            end_limit = min(end_limit, self.departure_date)
        versions = (
            self.sudo()
            .version_ids.filtered(lambda v: v.contract_date_start and v.date_version <= end_limit)
            .sorted(lambda v: (v.date_version, v.id))
        )
        segments = []
        for index, version in enumerate(versions):
            start = max(version.date_version, version.contract_date_start, date_from)
            end = end_limit
            if index + 1 < len(versions):
                end = min(end, versions[index + 1].date_version - timedelta(days=1))
            if version.contract_date_end:
                end = min(end, version.contract_date_end)
            if start <= end:
                segments.append((version, start, end))
        return segments

    def _l10n_ao_payroll_version_for(self, date_from, date_to):
        """Contrato em vigor no mês: a última versão com dias de contrato no período."""
        self.ensure_one()
        segments = self._l10n_ao_payroll_segments(date_from, date_to)
        return segments[-1][0] if segments else self.env['hr.version']

    def _l10n_ao_payroll_reference_salary(self, version, before=None):
        """Salário de referência (LGT, art. 237.º, n.º 8): o salário base mais, nos pagos ao tempo lectivo,
        a média mensal dos tempos lectivos dos últimos 12 recibos fechados (0 se ainda não houver recibos)."""
        self.ensure_one()
        if not version:
            return 0.0
        wage = version.wage if version.l10n_ao_pay_basis != 'lesson' else 0.0
        if version.l10n_ao_pay_basis == 'month':
            return wage
        domain = [('employee_id', '=', self.id), ('state', '=', 'done'), ('kind', '=', 'regular')]
        if before:
            domain.append(('run_id.date_from', '<', before))
        slips = self.env['l10n_ao_payroll.payslip'].sudo().search(domain)
        slips = slips.sorted(lambda s: (s.run_id.year, int(s.run_id.month)), reverse=True)[:12]
        if not slips:
            return wage
        lessons = sum(slips.line_ids.filtered(lambda line: line.code == 'LESSONS').mapped('amount'))
        return wage + lessons / len(slips)
