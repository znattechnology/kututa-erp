import io

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError

REPORT_TITLES = {
    'balance_sheet': 'Balanço',
    'income_statement': 'Demonstração de Resultados (por natureza)',
    'trial_balance': 'Balancete geral',
}
TRIAL_BALANCE_COLUMNS = ['Saldo inicial', 'Débito', 'Crédito', 'Saldo devedor', 'Saldo credor']


def format_amount(amount, unit):
    """Formato angolano: espaço nos milhares e vírgula decimal; zero como traço."""
    if amount is None:
        return ''
    if abs(amount) < 0.005:
        return '-'
    digits = 0 if unit > 1 else 2
    text = f'{abs(amount):,.{digits}f}'.replace(',', ' ').replace('.', ',')
    return f'({text})' if amount < 0 else text


class L10nAoReportsWizard(models.TransientModel):
    _name = 'l10n_ao_reports.wizard'
    _description = 'Demonstrações financeiras PGC'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],
    )
    report = fields.Selection(
        [
            ('balance_sheet', 'Balanço'),
            ('income_statement', 'Demonstração de Resultados (por natureza)'),
            ('trial_balance', 'Balancete geral'),
        ],
        string='Mapa',
        required=True,
        default='balance_sheet',
    )
    date_from = fields.Date(string='De', compute='_compute_dates', store=True, readonly=False, required=True)
    date_to = fields.Date(string='Até', compute='_compute_dates', store=True, readonly=False, required=True)
    comparative = fields.Boolean(
        string='Comparativo N-1', default=True, help='Obrigatório nas demonstrações financeiras (PGC 4.1).'
    )
    unit = fields.Selection(
        [('1', 'Kwanzas'), ('1000', 'Milhares de Kwanzas')],
        string='Valores expressos em',
        required=True,
        default='1',
    )
    posted_only = fields.Boolean(string='Só lançamentos publicados', default=True)
    hide_empty = fields.Boolean(
        string='Omitir rubricas sem valor',
        default=True,
        help='PGC 4.1.7: as rubricas sem valor no exercício e no comparativo podem ser omitidas.',
    )
    trial_depth = fields.Selection(
        [('0', 'Classes'), ('1', 'Contas (2 dígitos)'), ('2', 'Subcontas (3 níveis)'), ('all', 'Todas as contas')],
        string='Detalhe',
        default='all',
        required=True,
    )

    @api.depends('company_id')
    def _compute_dates(self):
        today = fields.Date.context_today(self)
        for wizard in self:
            dates = wizard.company_id.compute_fiscalyear_dates(today)
            wizard.date_from = dates['date_from']
            wizard.date_to = min(dates['date_to'], today)

    # ------------------------------------------------------------------
    def _unit(self):
        return int(self.unit)

    def _get_report_data(self):
        """Dados do mapa, comuns ao PDF, à pré-visualização e ao Excel."""
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise UserError(self.env._('Não tem acesso à empresa %s.', self.company_id.name))
        if self.date_from > self.date_to:
            raise UserError(self.env._('A data inicial é posterior à data final.'))
        engine = self.env['l10n_ao_reports.engine']
        company = self.company_id
        unit = self._unit()
        data = {
            'title': REPORT_TITLES[self.report],
            'report': self.report,
            'company': company,
            'unit': unit,
            'unit_label': dict(self._fields['unit'].selection)[self.unit],
            'date_from': self.date_from,
            'date_to': self.date_to,
            'posted_only': self.posted_only,
            'fmt': lambda amount: format_amount(amount, unit),
        }
        if self.report == 'balance_sheet':
            result = engine._balance_sheet(
                company,
                self.date_to,
                comparative=self.comparative,
                unit=unit,
                posted_only=self.posted_only,
                hide_empty=self.hide_empty,
            )
            data.update(
                lines=result['lines'],
                columns=[d.strftime('%d/%m/%Y') for d in result['dates']],
                subtitle=f'Balanço em {self.date_to.strftime("%d/%m/%Y")}',
                unmapped=result['unmapped'],
            )
        elif self.report == 'income_statement':
            result = engine._income_statement(
                company,
                self.date_from,
                self.date_to,
                comparative=self.comparative,
                unit=unit,
                posted_only=self.posted_only,
                hide_empty=self.hide_empty,
            )
            data.update(
                lines=result['lines'],
                columns=[f'{df.strftime("%d/%m/%Y")} a {dt.strftime("%d/%m/%Y")}' for df, dt in result['periods']],
                subtitle=(
                    f'Demonstração de Resultados de {self.date_from.strftime("%d/%m/%Y")} '
                    f'a {self.date_to.strftime("%d/%m/%Y")}'
                ),
            )
        else:
            depth = None if self.trial_depth == 'all' else int(self.trial_depth)
            result = engine._trial_balance(
                company,
                self.date_from,
                self.date_to,
                max_depth=depth,
                posted_only=self.posted_only,
                hide_empty=self.hide_empty,
            )
            data.update(
                lines=result['lines'],
                totals=result['totals'],
                columns=TRIAL_BALANCE_COLUMNS,
                subtitle=(f'Balancete de {self.date_from.strftime("%d/%m/%Y")} a {self.date_to.strftime("%d/%m/%Y")}'),
                fmt=lambda amount: format_amount(amount, 1),
            )
        return data

    # ------------------------------------------------------------------
    def action_print_pdf(self):
        return self.env.ref('l10n_ao_reports.action_report_financial').report_action(self, config=False)

    def action_preview(self):
        return self.env.ref('l10n_ao_reports.action_report_financial_html').report_action(self, config=False)

    def action_export_xlsx(self):
        self.ensure_one()
        data = self._get_report_data()
        content = self._render_xlsx(data)
        filename = f'{data["title"]} - {self.company_id.name} - {self.date_to}.xlsx'
        attachment = self.env['ir.attachment'].create(
            {
                'name': filename,
                'raw': content,
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'download',
        }

    def _render_xlsx(self, data):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(data['title'][:31])
        bold = workbook.add_format({'bold': True})
        title = workbook.add_format({'bold': True, 'font_size': 14})
        header = workbook.add_format({'bold': True, 'bottom': 1, 'align': 'center', 'text_wrap': True})
        decimals = '0' if data['unit'] > 1 and data['report'] != 'trial_balance' else '0.00'
        number_format = f'#,##{decimals};(#,##{decimals});"-"'
        number = workbook.add_format({'num_format': number_format})
        number_bold = workbook.add_format({'num_format': number_format, 'bold': True, 'top': 1})
        company = data['company']
        sheet.write(0, 0, company.name, title)
        sheet.write(1, 0, f'NIF: {company.vat or ""}')
        sheet.write(2, 0, data['subtitle'], bold)
        sheet.write(3, 0, f'Valores expressos em {data["unit_label"]}')
        row = 5
        if data['report'] == 'trial_balance':
            sheet.set_column(0, 0, 14)
            sheet.set_column(1, 1, 50)
            sheet.set_column(2, 6, 18)
            sheet.write_row(row, 0, ['Conta', 'Designação', *data['columns']], header)
            for line in data['lines']:
                row += 1
                fmt = number_bold if line['depth'] == 0 else number
                sheet.write(row, 0, line['code'], bold if line['depth'] == 0 else None)
                sheet.write(row, 1, '  ' * line['depth'] + line['name'], bold if line['depth'] == 0 else None)
                for col, amount in enumerate(line['amounts']):
                    sheet.write_number(row, 2 + col, amount, fmt)
            row += 1
            sheet.write(row, 1, 'TOTAIS', bold)
            for col, amount in enumerate(data['totals']):
                sheet.write_number(row, 2 + col, amount, number_bold)
        else:
            sheet.set_column(0, 0, 60)
            sheet.set_column(1, 1, 8)
            sheet.set_column(2, 3, 20)
            sheet.write_row(row, 0, ['Rubricas', 'Notas', *data['columns']], header)
            for line in data['lines']:
                row += 1
                is_total = line['style'] in ('total', 'grand_total')
                sheet.write(row, 0, line['name'], bold if line['style'] != 'line' else None)
                sheet.write(row, 1, line['note'])
                for col, amount in enumerate(line['amounts']):
                    sheet.write_number(row, 2 + col, amount, number_bold if is_total else number)
        workbook.close()
        return output.getvalue()
