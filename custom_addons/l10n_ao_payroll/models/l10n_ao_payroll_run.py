import csv
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytz
import xlsxwriter

from odoo import api, fields, models
from odoo.addons.l10n_ao_hr.models.l10n_ao_hr_overtime import round_overtime_hours
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import date_utils

from ..tools.payroll_calc import Component, Inputs, compute, round2
from ..tools.trust import is_trusted, trusted

UNPAID_CODES = ('UNPAID', 'UNJUSTIFIED', 'MATERNITY')
# Descontos que não são encargos nem retenções: valores devidos pelo trabalhador (aviso prévio em falta).
STANDARD_DEDUCTIONS = ('ABSENCE', 'SANCTION', 'INSS', 'IRT', 'ADVANCE')
MONTHS = [
    (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'), (5, 'Maio'), (6, 'Junho'),
    (7, 'Julho'), (8, 'Agosto'), (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
]  # fmt: skip


def business_days(date_from, date_to):
    """Dias úteis (segunda a sexta) entre duas datas, inclusive."""
    count = 0
    day = date_from
    while day <= date_to:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


class L10nAoPayrollRun(models.Model):
    _name = 'l10n_ao_payroll.run'
    _description = 'Folha de salários (mês)'
    _inherit = ['mail.thread']
    _order = 'year desc, month desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Folha', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    year = fields.Integer(string='Ano', required=True, default=lambda self: fields.Date.context_today(self).year)
    month = fields.Selection(
        [(str(m), name) for m, name in MONTHS],
        string='Mês',
        required=True,
        default=lambda self: str(fields.Date.context_today(self).month),
    )
    date_from = fields.Date(compute='_compute_dates', store=True)
    date_to = fields.Date(compute='_compute_dates', store=True)
    state = fields.Selection(
        [('draft', 'Rascunho'), ('computed', 'Calculada'), ('closed', 'Fechada'), ('cancelled', 'Anulada')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    payslip_ids = fields.One2many('l10n_ao_payroll.payslip', 'run_id', string='Recibos')
    payslip_count = fields.Integer(string='N.º de recibos', compute='_compute_totals')
    total_gross = fields.Monetary(string='Bruto', compute='_compute_totals')
    total_net = fields.Monetary(string='Líquido', compute='_compute_totals')
    total_irt = fields.Monetary(string='IRT', compute='_compute_totals')
    total_inss = fields.Monetary(string='INSS (trabalhador + empresa)', compute='_compute_totals')
    total_cost = fields.Monetary(string='Custo total', compute='_compute_totals')
    move_id = fields.Many2one('account.move', string='Lançamento', readonly=True, copy=False)
    note = fields.Text(string='Notas')

    _year_month_company_uniq = models.Constraint(
        'UNIQUE(company_id, year, month)', 'Já existe uma folha deste mês nesta empresa.'
    )

    @api.depends('year', 'month')
    def _compute_name(self):
        names = dict(MONTHS)
        for run in self:
            run.name = f'{names.get(int(run.month or 1))} de {run.year}' if run.year else self.env._('Folha')

    @api.depends('year', 'month')
    def _compute_dates(self):
        for run in self:
            if run.year and run.month:
                run.date_from = date(run.year, int(run.month), 1)
                run.date_to = date_utils.end_of(run.date_from, 'month')
            else:
                run.date_from = run.date_to = False

    @api.depends(
        'payslip_ids.gross',
        'payslip_ids.net',
        'payslip_ids.irt',
        'payslip_ids.inss_employee',
        'payslip_ids.inss_employer',
        'payslip_ids.state',
    )
    def _compute_totals(self):
        for run in self:
            slips = run.payslip_ids.filtered(lambda s: s.state != 'cancelled')
            run.payslip_count = len(slips)
            run.total_gross = sum(slips.mapped('gross'))
            run.total_net = sum(slips.mapped('net'))
            run.total_irt = sum(slips.mapped('irt'))
            run.total_inss = sum(slips.mapped('inss_employee')) + sum(slips.mapped('inss_employer'))
            run.total_cost = run.total_gross + sum(slips.mapped('inss_employer'))

    @api.constrains('year', 'month')
    def _check_period(self):
        today = fields.Date.context_today(self)
        for run in self:
            if run.date_from and run.date_from > today:
                raise ValidationError(self.env._('Não se processa um mês futuro.'))

    # ------------------------------------------------------------------
    def _employees(self):
        """Trabalhadores com contrato em vigor em algum dia do mês."""
        self.ensure_one()
        # Inclui os arquivados: quem saiu a meio do mês recebe os dias trabalhados.
        return (
            self.env['hr.employee']
            .with_company(self.company_id)
            .with_context(active_test=False)
            .search([('company_id', '=', self.company_id.id)])
            .filtered(lambda e: e._l10n_ao_payroll_segments(self.date_from, self.date_to))
        )

    def action_compute(self):
        for run in self:
            if run.state not in ('draft', 'computed'):
                raise UserError(self.env._('A folha já está fechada.'))
            # Recalcula no sítio: os tempos lectivos, as outras linhas e as contas finais mantêm-se.
            employees = run._employees()
            run.payslip_ids.filtered(lambda s: s.state == 'draft' and s.kind == 'regular').filtered_domain(
                [('employee_id', 'not in', employees.ids)]
            ).unlink()
            existing = run.payslip_ids.mapped('employee_id')
            self.env['l10n_ao_payroll.payslip'].create(
                [{'run_id': run.id, 'employee_id': employee.id} for employee in employees if employee not in existing]
            )
            run.payslip_ids.filtered(lambda s: s.state == 'draft').action_compute()
            with trusted(self.env):
                run.state = 'computed'

    def action_close(self):
        for run in self:
            if run.state != 'computed':
                raise UserError(self.env._('Calcule a folha antes de a fechar.'))
            slips = run.payslip_ids.filtered(lambda s: s.state == 'draft')
            if not slips:
                raise UserError(self.env._('A folha não tem recibos.'))
            slips.action_compute()
            negative = slips.filtered(lambda s: s.net < 0)
            if negative:
                raise UserError(
                    self.env._(
                        'Líquido negativo em %s: reveja os descontos antes de fechar.',
                        ', '.join(negative.mapped('employee_id.name')),
                    )
                )
            # O fecho mexe na contabilidade e na sequência: o utilizador de RH não precisa de direitos nelas.
            run.company_id.sudo()._l10n_ao_payroll_ensure_accounting()
            sequence = run._payslip_sequence()
            with trusted(self.env):
                for slip in slips.sorted(lambda s: (s.employee_id.name or '', s.id)):
                    slip.number = sequence.next_by_id()
                    slip._apply_advances()
                    if slip.vacation_subsidy:
                        employee = slip.employee_id.sudo()
                        slip.vacation_subsidy_prev_year = employee.l10n_ao_payroll_vacation_subsidy_year
                        employee.l10n_ao_payroll_vacation_subsidy_year = run.year
                slips.write({'state': 'done'})
                run.move_id = run.sudo()._create_move(slips.sudo())
                run.state = 'closed'

    def action_cancel(self):
        for run in self:
            move = run.move_id.sudo()
            if move.state == 'posted':
                # Estorno, para o lançamento original ficar no diário (não se apaga contabilidade publicada).
                move._reverse_moves([{'date': move.date, 'ref': self.env._('Anulação: %s', move.ref)}], cancel=True)
            elif move.state == 'draft':
                move.button_cancel()
            for slip in run.payslip_ids.filtered(lambda s: s.state == 'done' and s.vacation_subsidy):
                employee = slip.employee_id.sudo()
                if employee.l10n_ao_payroll_vacation_subsidy_year == run.year:
                    employee.l10n_ao_payroll_vacation_subsidy_year = slip.vacation_subsidy_prev_year
            with trusted(self.env):
                run.payslip_ids.write({'state': 'cancelled'})
                run.payslip_ids.mapped('advance_deduction_ids.advance_id')._settle_if_done()
                run.state = 'cancelled'

    def action_draft(self):
        for run in self:
            if run.state != 'cancelled':
                raise UserError(self.env._('Só uma folha anulada volta a rascunho.'))
            run.payslip_ids.unlink()
            with trusted(self.env):
                run.state = 'draft'

    def write(self, vals):
        # O estado e o lançamento da folha só mudam pelas acções (Calcular, Fechar, Anular, Repor).
        if not is_trusted(self.env) and {'state', 'move_id'} & set(vals):
            raise AccessError(self.env._('O estado da folha muda pelos botões (Calcular, Fechar, Anular).'))
        return super().write(vals)

    def _payslip_sequence(self):
        self.ensure_one()
        Sequence = self.env['ir.sequence'].sudo()
        code = 'l10n_ao_payroll.payslip'
        sequence = Sequence.search([('code', '=', code), ('company_id', '=', self.company_id.id)], limit=1)
        if not sequence:
            sequence = Sequence.create(
                {
                    'name': 'Recibos de salário',
                    'code': code,
                    'company_id': self.company_id.id,
                    'prefix': '%(year)s/',
                    'padding': 5,
                    'use_date_range': True,
                }
            )
        return sequence.with_context(ir_sequence_date=self.date_to)

    def _create_move(self, slips):
        """Lançamento do fecho (PGC): D 72.2 remunerações, D 72.8.2 compensações, D 72.5.2 encargos;
        C 36.1.2 por trabalhador, C 34.3.1 IRT, C 34.9.1 INSS, C 36.3 adiantamentos."""
        self.ensure_one()
        company = self.company_id
        label = self.env._('Salários de %s', self.name)
        lines = []
        compensation = sum(slips.line_ids.filtered(lambda line: line.code == 'COMPENSATION').mapped('amount'))
        owed = sum(
            slips.line_ids.filtered(
                lambda line: line.kind == 'deduction' and line.code not in STANDARD_DEDUCTIONS
            ).mapped('amount')
        )
        expense = sum(s.gross - s.absences - s.sanction for s in slips) - compensation - owed
        employer = sum(slips.mapped('inss_employer'))
        if expense:
            lines.append((company.l10n_ao_payroll_expense_account_id, None, expense))
        if compensation:
            lines.append((company.l10n_ao_payroll_compensation_account_id, None, compensation))
        if employer:
            lines.append((company.l10n_ao_payroll_employer_account_id, None, employer))
        for slip in slips:
            if slip.net:
                lines.append((company.l10n_ao_payroll_payable_account_id, slip.employee_id.work_contact_id, -slip.net))
        irt = sum(slips.mapped('irt'))
        inss = sum(slips.mapped('inss_employee')) + employer
        advances = sum(slips.mapped('advance'))
        if irt:
            lines.append((company.l10n_ao_payroll_irt_account_id, None, -irt))
        if inss:
            lines.append((company.l10n_ao_payroll_inss_account_id, None, -inss))
        if advances:
            lines.append((company.l10n_ao_payroll_advance_account_id, None, -advances))
        move = (
            self.env['account.move']
            .with_company(company)
            .create(
                {
                    'move_type': 'entry',
                    'journal_id': company.l10n_ao_payroll_journal_id.id,
                    'date': self.date_to,
                    'ref': label,
                    'line_ids': [
                        fields.Command.create(
                            {
                                'account_id': account.id,
                                'partner_id': partner.id if partner else False,
                                'name': label,
                                'debit': round2(amount) if amount > 0 else 0.0,
                                'credit': round2(-amount) if amount < 0 else 0.0,
                            }
                        )
                        for account, partner, amount in lines
                    ],
                }
            )
        )
        move.action_post()
        return move

    # ------------------------------------------------------------------
    # Exportações
    # ------------------------------------------------------------------
    def _attachment(self, name, content, mimetype):
        attachment = self.env['ir.attachment'].create(
            {'name': name, 'raw': content, 'res_model': self._name, 'res_id': self.id, 'mimetype': mimetype}
        )
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'download',
        }

    def _done_slips(self):
        return self.payslip_ids.filtered(lambda s: s.state == 'done')

    def action_export_bank_file(self):
        """Ficheiro de transferências (CSV): IBAN, nome, valor líquido. O formato de cada banco configura-se à parte."""
        self.ensure_one()
        slips = self._done_slips().filtered(lambda s: s.net > 0)
        missing = slips.filtered(lambda s: not s.bank_account_id)
        if missing:
            raise UserError(
                self.env._(
                    'Sem conta bancária (IBAN): %s. Registe-a no trabalhador ou no contrato.',
                    ', '.join(missing.mapped('employee_id.name')),
                )
            )
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['IBAN', 'Nome', 'Valor', 'Descritivo'])
        for slip in slips:
            writer.writerow(
                [slip.bank_account_id.account_number, slip.employee_id.name, f'{slip.net:.2f}', f'Salario {self.name}']
            )
        name = f'transferencias_{self.year}_{int(self.month):02d}.csv'
        return self._attachment(name, output.getvalue().encode('utf-8-sig'), 'text/csv')

    def _xlsx(self, title, headers, rows, widths):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(title[:31])
        bold = workbook.add_format({'bold': True})
        head = workbook.add_format({'bold': True, 'bottom': 1, 'text_wrap': True})
        number = workbook.add_format({'num_format': '#,##0.00'})
        sheet.write(0, 0, self.company_id.name, bold)
        sheet.write(1, 0, f'NIF: {self.company_id.vat or ""}')
        sheet.write(2, 0, f'{title}: {self.name}', bold)
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
        sheet.write_row(4, 0, headers, head)
        for index, row in enumerate(rows, start=5):
            for col, value in enumerate(row):
                if isinstance(value, float):
                    sheet.write_number(index, col, value, number)
                else:
                    sheet.write(index, col, value)
        total_row = 5 + len(rows)
        sheet.write(total_row, 0, 'TOTAL', bold)
        for col in range(len(headers)):
            if rows and isinstance(rows[0][col], float):
                sheet.write_number(
                    total_row,
                    col,
                    sum(r[col] for r in rows),
                    workbook.add_format({'num_format': '#,##0.00', 'bold': True, 'top': 1}),
                )
        workbook.close()
        return output.getvalue()

    def action_export_irt_map(self):
        """Mapa mensal de remunerações para a AGT (CIRT, art. 17.º): colunas do modelo do Portal do Contribuinte."""
        self.ensure_one()
        # sudo: o BI e o n.º do INSS só são legíveis pelo RH, e o contabilista também exporta o mapa.
        rows = []
        for slip in self._done_slips().sudo():
            discounts = slip.absences + slip.sanction
            rows.append(
                (
                    slip.employee_id.identification_id or '',
                    slip.employee_id.name,
                    slip.employee_id.l10n_ao_inss_number or '',
                    float(slip.gross),
                    float(discounts),
                    float(round2(slip.gross - discounts - slip.irt_base - slip.inss_employee)),
                    float(slip.inss_employee),
                    float(slip.irt_base),
                    float(slip.irt),
                )
            )
        headers = [
            'NIF / BI',
            'Nome',
            'N.º INSS',
            'Remuneração bruta',
            'Faltas e sanções',
            'Rendimentos não sujeitos',
            'INSS (3%)',
            'Matéria colectável',
            'IRT retido',
        ]
        content = self._xlsx('Mapa de remunerações (IRT)', headers, rows, [16, 36, 14, 18, 16, 18, 14, 18, 14])
        return self._attachment(
            f'mapa_irt_{self.year}_{int(self.month):02d}.xlsx',
            content,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def action_export_inss_map(self):
        """Folha de remunerações para o INSS (DP n.º 227/18): base, 3% e 8%."""
        self.ensure_one()
        rows = [
            (
                slip.employee_id.l10n_ao_inss_number or '',
                slip.employee_id.name,
                slip.employee_id.identification_id or '',
                float(slip.inss_base),
                float(slip.inss_employee),
                float(slip.inss_employer),
                float(slip.inss_employee + slip.inss_employer),
            )
            for slip in self._done_slips().sudo()
        ]
        headers = ['N.º de segurado', 'Nome', 'BI', 'Remuneração sujeita', 'Trabalhador (3%)', 'Empresa (8%)', 'Total']
        content = self._xlsx('Folha de remunerações (INSS)', headers, rows, [16, 36, 16, 18, 16, 16, 16])
        return self._attachment(
            f'folha_inss_{self.year}_{int(self.month):02d}.xlsx',
            content,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def action_print_sheet(self):
        return self.env.ref('l10n_ao_payroll.action_report_payroll_sheet').report_action(self, config=False)


class L10nAoPayrollPayslip(models.Model):
    _name = 'l10n_ao_payroll.payslip'
    _description = 'Recibo de salário (LGT, art. 247.º)'
    _order = 'run_id desc, employee_id'
    _check_company_auto = True

    run_id = fields.Many2one('l10n_ao_payroll.run', string='Folha', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='run_id.company_id', store=True)
    currency_id = fields.Many2one(related='run_id.currency_id')
    employee_id = fields.Many2one('hr.employee', string='Trabalhador', required=True, index=True, check_company=True)
    version_id = fields.Many2one('hr.version', string='Contrato', readonly=True)
    number = fields.Char(string='N.º', readonly=True, copy=False)
    date_from = fields.Date(related='run_id.date_from')
    date_to = fields.Date(related='run_id.date_to')
    state = fields.Selection(
        [('draft', 'Rascunho'), ('done', 'Fechado'), ('cancelled', 'Anulado')],
        string='Estado',
        default='draft',
        required=True,
    )
    kind = fields.Selection(
        [('regular', 'Mensal'), ('final', 'Contas finais')], string='Tipo', default='regular', required=True
    )
    line_ids = fields.One2many('l10n_ao_payroll.payslip.line', 'payslip_id', string='Linhas')
    # Dados de entrada
    base_salary = fields.Monetary(string='Salário base', readonly=True)
    weekly_hours = fields.Float(string='Horas semanais', readonly=True)
    worked_days = fields.Integer(string='Dias úteis com contrato', readonly=True)
    month_days = fields.Integer(string='Dias úteis do mês', readonly=True)
    lesson_count = fields.Float(string='Tempos lectivos', help='Preenchido pelo módulo académico ou à mão.')
    lesson_rate = fields.Monetary(string='Valor por tempo', readonly=True)
    overtime_hours = fields.Float(string='Horas extra', readonly=True)
    night_hours = fields.Float(string='Horas nocturnas', readonly=True)
    rest_day_hours = fields.Float(string='Horas em dia de descanso', readonly=True)
    holiday_hours = fields.Float(string='Horas em feriado', readonly=True)
    absence_hours = fields.Float(string='Horas de faltas não pagas', readonly=True)
    sanction_pct = fields.Float(string='Sanção (%)', readonly=True)
    vacation_subsidy = fields.Boolean(string='Subsídio de férias')
    christmas_months = fields.Integer(string='Meses do subsídio de Natal')
    subsidies_manual = fields.Boolean(
        string='Subsídios definidos à mão', help='O recálculo não altera o subsídio de férias nem o de Natal.'
    )
    vacation_subsidy_prev_year = fields.Integer(readonly=True, copy=False)  # para repor ao anular a folha
    reference_salary = fields.Monetary(
        string='Salário de referência',
        readonly=True,
        help='Base do salário-hora e dos subsídios; nos pagos ao tempo lectivo, a média dos últimos 12 meses '
        '(LGT, art. 237.º, n.º 8).',
    )
    advance_requested = fields.Monetary(string='Adiantamento a descontar', readonly=True)
    extra_line_ids = fields.One2many('l10n_ao_payroll.payslip.extra', 'payslip_id', string='Outras linhas')
    # Resultados
    hourly_rate = fields.Monetary(string='Salário-hora', readonly=True)
    gross = fields.Monetary(string='Bruto', readonly=True)
    irt_base = fields.Monetary(string='Matéria colectável', readonly=True)
    irt = fields.Monetary(string='IRT', readonly=True)
    inss_base = fields.Monetary(string='Base do INSS', readonly=True)
    inss_employee = fields.Monetary(string='INSS trabalhador', readonly=True)
    inss_employer = fields.Monetary(string='INSS empresa', readonly=True)
    absences = fields.Monetary(string='Faltas', readonly=True)
    sanction = fields.Monetary(string='Sanção', readonly=True)
    advance = fields.Monetary(string='Adiantamento descontado', readonly=True)
    deductions = fields.Monetary(string='Descontos', readonly=True)
    net = fields.Monetary(string='Líquido', readonly=True)
    warning = fields.Text(string='Avisos', readonly=True)
    advance_deduction_ids = fields.One2many('l10n_ao_payroll.advance.deduction', 'payslip_id', string='Amortizações')
    bank_account_id = fields.Many2one(
        'res.partner.bank', string='Conta bancária', compute='_compute_bank_account', compute_sudo=True
    )

    _run_employee_uniq = models.Constraint('UNIQUE(run_id, employee_id)', 'O trabalhador já tem recibo nesta folha.')

    @api.depends('employee_id', 'version_id')
    def _compute_bank_account(self):
        for slip in self:
            slip.bank_account_id = (
                slip.version_id.l10n_ao_payroll_bank_account_id or slip.employee_id.sudo().primary_bank_account_id
            )

    @api.depends('employee_id', 'run_id.name', 'number')
    def _compute_display_name(self):
        for slip in self:
            slip.display_name = f'{slip.number or "Rascunho"} · {slip.employee_id.name} · {slip.run_id.name}'

    # ------------------------------------------------------------------
    # Calculados pelo processamento (cálculo, fecho, anulação): não se escrevem por chamada directa.
    _RESULT_FIELDS = frozenset(
        {
            'state', 'number', 'hourly_rate', 'gross', 'irt_base', 'irt', 'inss_base', 'inss_employee',
            'inss_employer', 'absences', 'sanction', 'advance', 'deductions', 'net', 'warning', 'line_ids',
            'vacation_subsidy_prev_year', 'run_id', 'employee_id',
        }
    )  # fmt: skip

    def write(self, vals):
        if not is_trusted(self.env):
            if self._RESULT_FIELDS & set(vals):
                raise AccessError(self.env._('Os valores do recibo calculam-se pela folha (Calcular, Fechar, Anular).'))
            if self.filtered(lambda s: s.state != 'draft') and {k for k in vals if not k.startswith('message_')}:
                raise UserError(self.env._('O recibo já está fechado ou anulado: não pode ser alterado.'))
        if not self.env.context.get('l10n_ao_payroll_auto') and {'vacation_subsidy', 'christmas_months'} & set(vals):
            vals = dict(vals, subsidies_manual=True)
        return super().write(vals)

    def _inputs(self):
        """Dados de entrada do mês a partir dos contratos, ausências, horas extra, sanções e adiantamentos."""
        self.ensure_one()
        run = self.run_id
        employee = self.employee_id
        company = run.company_id
        segments = employee._l10n_ao_payroll_segments(run.date_from, run.date_to)
        if not segments:
            raise UserError(
                self.env._('%(employee)s não tem contrato em vigor em %(run)s.', employee=employee.name, run=run.name)
            )
        version = segments[-1][0]
        auto = self.with_context(l10n_ao_payroll_auto=True)
        auto.version_id = version
        start, end = segments[0][1], segments[-1][2]
        month_days = business_days(run.date_from, run.date_to)
        # Mudanças de salário e renovações a meio do mês: cada versão paga os seus dias úteis.
        worked_days = 0
        base_amount = 0.0
        for segment_version, segment_start, segment_end in segments:
            days = business_days(segment_start, segment_end)
            worked_days += days
            if segment_version.l10n_ao_pay_basis != 'lesson' and month_days:
                base_amount += segment_version.wage * days / month_days
        fraction = worked_days / month_days if month_days else 0.0
        components = [
            Component(
                code=c.code,
                name=c.name,
                amount=c.amount,
                subject_irt=c.subject_irt,
                subject_inss=c.subject_inss,
                irt_exempt_cap=self._irt_exempt_cap(c),
                proportional=c.proportional,
            )
            for c in version.l10n_ao_payroll_component_ids
        ]
        overtime = self._overtime_hours()
        sanction_pct = max(
            [s._reduction_in_month(run.year, int(run.month)) for s in employee.l10n_ao_sanction_ids] or [0.0]
        )
        if self.kind == 'regular' and not self.subsidies_manual:
            auto.write({'vacation_subsidy': self._vacation_subsidy_due(), 'christmas_months': self._christmas_months()})
        advance_requested = sum(min(advance.monthly_deduction, advance.balance) for advance in self._advances_due())
        base = version.wage if version.l10n_ao_pay_basis != 'lesson' else 0.0
        lesson_count = self.lesson_count if version.l10n_ao_pay_basis != 'month' else 0.0
        reference = employee._l10n_ao_payroll_reference_salary(version, before=run.date_from)
        if version.l10n_ao_pay_basis != 'month' and reference <= base:
            # Ainda sem histórico: os tempos lectivos do próprio mês.
            reference = base + lesson_count * version.l10n_ao_lesson_rate
        weekly_hours = version.l10n_ao_weekly_hours or 44.0
        auto.write(
            {
                'base_salary': base,
                'reference_salary': reference,
                'weekly_hours': weekly_hours,
                'worked_days': worked_days,
                'month_days': month_days,
                'lesson_rate': version.l10n_ao_lesson_rate,
                'overtime_hours': overtime['extra'],
                'night_hours': overtime['night'],
                'rest_day_hours': overtime['rest_day'],
                'holiday_hours': overtime['holiday'],
                'absence_hours': self._absence_hours(start, end, weekly_hours),
                'sanction_pct': sanction_pct,
                'advance_requested': advance_requested,
            }
        )
        return Inputs(
            base_salary=base,
            base_amount=round2(base_amount),
            reference_salary=reference,
            weekly_hours=weekly_hours,
            fraction=fraction,
            worked_days=worked_days,
            month_days=month_days,
            components=components,
            lesson_count=lesson_count,
            lesson_rate=version.l10n_ao_lesson_rate,
            overtime_hours=overtime['extra'],
            night_hours=overtime['night'],
            rest_day_hours=overtime['rest_day'],
            holiday_hours=overtime['holiday'],
            absence_hours=self.absence_hours,
            sanction_pct=sanction_pct,
            vacation_subsidy=self.vacation_subsidy,
            christmas_months=self.christmas_months,
            advance_requested=advance_requested,
            extra_lines=[(e.code, e.name, e.amount, e.subject_irt, e.subject_inss) for e in self.extra_line_ids],
        ), company._l10n_ao_payroll_settings(run.date_to)

    def _advances_due(self):
        """Adiantamentos concedidos até ao fim do mês e ainda por saldar, do mais antigo para o mais recente."""
        return self.employee_id.l10n_ao_payroll_advance_ids.filtered(
            lambda a: a.state == 'approved' and a.date <= self.run_id.date_to
        ).sorted('date')

    def _irt_exempt_cap(self, component):
        company = self.run_id.company_id
        if component.code == 'MEAL':
            return company.l10n_ao_payroll_meal_cap
        if component.code == 'TRANSPORT':
            return company.l10n_ao_payroll_transport_cap
        if component.code == 'FAMILY':
            return self.version_id.wage * 0.05  # CIRT, art. 2.º: abono de família até 5% do salário base
        return 0.0

    def _overtime_hours(self):
        """Horas aprovadas no mês por tipo, arredondadas sobre o total (art. 188.º, n.º 4)."""
        run = self.run_id
        totals = defaultdict(float)
        for record in self.employee_id.l10n_ao_overtime_ids.filtered(
            lambda o: o.state == 'approved' and run.date_from <= o.date <= run.date_to
        ):
            totals[record.kind] += record.hours
        return {kind: round_overtime_hours(totals[kind]) for kind in ('extra', 'night', 'rest_day', 'holiday')}

    def _absence_hours(self, start, end, weekly_hours=44.0):
        """Horas das ausências não pagas validadas que caem no mês (dias úteis do calendário, sem feriados),
        mais a parte das ausências pagas que excede os limites da LGT (falta justificada não remunerada)."""
        employee = self.employee_id
        calendar = employee.resource_calendar_id or self.run_id.company_id.resource_calendar_id
        tz = pytz.timezone(employee.tz or 'Africa/Luanda')
        hours = 0.0
        leaves = self.env['hr.leave'].search(
            [
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', fields.Datetime.to_string(datetime.combine(end, time.max))),
                ('date_to', '>=', fields.Datetime.to_string(datetime.combine(start, time.min))),
            ]
        )
        month_start = tz.localize(datetime.combine(start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        month_end = tz.localize(datetime.combine(end, time.max)).astimezone(pytz.utc).replace(tzinfo=None)
        for leave in leaves:
            kind = leave.work_entry_type_id
            if not (kind.unpaid or kind.l10n_ao_payroll_code in UNPAID_CODES):
                continue
            if leave.date_from >= month_start and leave.date_to <= month_end:
                # Ausência inteira dentro do mês: as horas que o Odoo já calculou (sem feriados).
                hours += leave.number_of_hours
                continue
            clip_from = max(leave.date_from, month_start)
            clip_to = min(leave.date_to, month_end)
            if clip_from >= clip_to:
                continue
            hours += calendar.get_work_hours_count(
                pytz.utc.localize(clip_from), pytz.utc.localize(clip_to), compute_leaves=True
            )
        hours_per_day = (calendar.hours_per_day if calendar else 0.0) or weekly_hours / 5
        hours += self.env['hr.leave']._l10n_ao_unpaid_hours(employee, start, end, hours_per_day)
        return round(hours, 2)

    def _vacation_subsidy_due(self):
        """Subsídio de férias no mês em que começam as férias, uma vez por ano (art. 238.º)."""
        run = self.run_id
        employee = self.employee_id
        if employee.l10n_ao_payroll_vacation_subsidy_year >= run.year:
            return False
        vacation = self.env.ref('l10n_ao_hr.work_entry_type_ao_ferias', raise_if_not_found=False)
        if not vacation:
            return False
        return bool(
            self.env['hr.leave'].search_count(
                [
                    ('employee_id', '=', employee.id),
                    ('work_entry_type_id', '=', vacation.id),
                    ('state', '=', 'validate'),
                    ('date_from', '>=', fields.Datetime.to_string(datetime.combine(run.date_from, time.min))),
                    ('date_from', '<=', fields.Datetime.to_string(datetime.combine(run.date_to, time.max))),
                ],
                limit=1,
            )
        )

    def _christmas_months(self):
        run = self.run_id
        if int(run.month) != (run.company_id.l10n_ao_payroll_christmas_month or 12):
            return 0
        admission = self.employee_id.l10n_ao_admission_date
        if admission and admission.year == run.year:
            # Só meses completos: admitido a meio do mês, conta a partir do mês seguinte.
            first = admission.month if admission.day == 1 else admission.month + 1
            return max(0, 12 - first + 1)
        return 12

    def action_compute(self):
        # Já recusa recibos fechados; o cálculo grava os valores e as linhas como escrita interna.
        with trusted(self.env):
            return self._l10n_ao_payroll_compute()

    def _l10n_ao_payroll_compute(self):
        for slip in self:
            if slip.state != 'draft':
                raise UserError(self.env._('O recibo já está fechado.'))
            inputs, settings = slip._inputs()
            result = compute(inputs, settings)
            slip.line_ids.unlink()
            slip.line_ids = [
                fields.Command.create(
                    {
                        'sequence': index,
                        'kind': line.kind,
                        'code': line.code,
                        'name': line.name,
                        'quantity': line.quantity,
                        'rate': line.rate,
                        'amount': line.amount,
                    }
                )
                for index, line in enumerate(result.lines)
            ]
            warnings = []
            min_wage = slip.run_id.company_id.l10n_ao_payroll_min_wage
            if inputs.base_salary and inputs.fraction >= 1 and inputs.base_salary < min_wage:
                warnings.append(self.env._('Salário base abaixo do salário mínimo nacional (%s).', min_wage))
            if not settings.irt_brackets:
                warnings.append(self.env._('Não há tabela do IRT em vigor: o IRT ficou a zero.'))
            if not slip.employee_id.sudo().l10n_ao_inss_number:
                warnings.append(self.env._('Falta o número de segurado do INSS (obrigatório no recibo, art. 247.º).'))
            if result.net < 0:
                warnings.append(self.env._('Líquido negativo: a folha não fecha com este recibo.'))
            slip.with_context(l10n_ao_payroll_auto=True).write(
                {
                    'hourly_rate': result.hourly_rate,
                    'gross': result.gross,
                    'irt_base': result.irt_base,
                    'irt': result.irt,
                    'inss_base': result.inss_base,
                    'inss_employee': result.inss_employee,
                    'inss_employer': result.inss_employer,
                    'absences': result.absences,
                    'sanction': result.sanction,
                    'advance': result.advance,
                    'deductions': result.deductions,
                    'net': result.net,
                    'warning': '\n'.join(warnings) or False,
                }
            )

    def _apply_advances(self):
        """Amortiza os adiantamentos, do mais antigo para o mais recente, até ao valor descontado no recibo."""
        self.ensure_one()
        remaining = self.advance
        for advance in self._advances_due():
            if remaining <= 0:
                break
            amount = min(advance.monthly_deduction, advance.balance, remaining)
            if amount > 0:
                self.env['l10n_ao_payroll.advance.deduction'].create(
                    {'advance_id': advance.id, 'payslip_id': self.id, 'amount': round2(amount)}
                )
                remaining = round2(remaining - amount)
        self.employee_id.l10n_ao_payroll_advance_ids._settle_if_done()

    def action_print(self):
        return self.env.ref('l10n_ao_payroll.action_report_payslip').report_action(self, config=False)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(slip.state == 'done' for slip in self):
            raise UserError(self.env._('Um recibo fechado não se elimina; anule a folha.'))


class L10nAoPayrollPayslipLine(models.Model):
    _name = 'l10n_ao_payroll.payslip.line'
    _description = 'Linha do recibo'
    _order = 'payslip_id, sequence, id'

    payslip_id = fields.Many2one('l10n_ao_payroll.payslip', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='payslip_id.currency_id')
    sequence = fields.Integer()
    kind = fields.Selection([('earning', 'Remuneração'), ('deduction', 'Desconto')], string='Tipo', required=True)
    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Descrição', required=True)
    quantity = fields.Float(string='Quantidade', default=1.0)
    rate = fields.Monetary(string='Valor unitário')
    amount = fields.Monetary(string='Valor', required=True)

    def _check_payslip_open(self, payslips=None):
        if not is_trusted(self.env) and (payslips or self.payslip_id).filtered(lambda s: s.state != 'draft'):
            raise UserError(self.env._('O recibo já está fechado ou anulado: não pode ser alterado.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_payslip_open()
        return records

    def write(self, vals):
        self._check_payslip_open()
        result = super().write(vals)
        if 'payslip_id' in vals:
            self._check_payslip_open()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_if_open(self):
        self._check_payslip_open()


class L10nAoPayrollPayslipExtra(models.Model):
    _name = 'l10n_ao_payroll.payslip.extra'
    _description = 'Linha adicional do recibo (prémios, compensações, acertos)'

    payslip_id = fields.Many2one('l10n_ao_payroll.payslip', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='payslip_id.currency_id')
    code = fields.Char(string='Código', required=True, default='OTHER')
    name = fields.Char(string='Descrição', required=True)
    amount = fields.Monetary(string='Valor', required=True)
    subject_irt = fields.Boolean(string='Sujeito a IRT', default=True)
    subject_inss = fields.Boolean(string='Sujeito a INSS', default=True)

    def _check_payslip_open(self, payslips=None):
        if not is_trusted(self.env) and (payslips or self.payslip_id).filtered(lambda s: s.state != 'draft'):
            raise UserError(self.env._('O recibo já está fechado ou anulado: não pode ser alterado.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_payslip_open()
        return records

    def write(self, vals):
        self._check_payslip_open()
        result = super().write(vals)
        if 'payslip_id' in vals:
            self._check_payslip_open()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_if_open(self):
        self._check_payslip_open()
