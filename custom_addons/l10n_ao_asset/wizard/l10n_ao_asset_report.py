import io
from datetime import date

import xlsxwriter

from odoo import api, fields, models
from odoo.addons.l10n_ao_reports.wizard.l10n_ao_reports_wizard import format_amount

COLUMNS = [
    ('rate_code', 'Código da tabela'),
    ('name', 'Designação'),
    ('acquisition_year', 'Ano de aquisição'),
    ('start_date', 'Entrada em funcionamento'),
    ('original_value', 'Valor de aquisição'),
    ('rate', 'Taxa (%)'),
    ('depreciated_start', 'Amortizações acumuladas no início'),
    ('depreciation', 'Amortizações do exercício'),
    ('depreciated_end', 'Amortizações acumuladas no fim'),
    ('book_value', 'Valor líquido'),
    ('disposed', 'Abates: valor bruto'),
    ('disposed_depreciation', 'Abates: amortizações'),
    ('not_accepted', 'Amortização não aceite'),
]
AMOUNT_COLUMNS = (
    'original_value',
    'depreciated_start',
    'depreciation',
    'depreciated_end',
    'book_value',
    'disposed',
    'disposed_depreciation',
    'not_accepted',
)


class L10nAoAssetReport(models.TransientModel):
    _name = 'l10n_ao_asset.report'
    _description = 'Mapa de reintegrações e amortizações'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    year = fields.Integer(string='Exercício', required=True, default=lambda self: fields.Date.context_today(self).year)
    date_from = fields.Date(compute='_compute_dates')
    date_to = fields.Date(compute='_compute_dates')

    @api.depends('company_id', 'year')
    def _compute_dates(self):
        for wizard in self:
            company = wizard.company_id
            # O último dia do exercício pode não existir no ano (29 de Fevereiro): usa-se o dia 1 do mês.
            dates = company.compute_fiscalyear_dates(date(wizard.year or 2000, int(company.fiscalyear_last_month), 1))
            wizard.date_from, wizard.date_to = dates['date_from'], dates['date_to']

    def _get_report_data(self):
        """Uma linha por bem: CII, art. 43.º (só as amortizações contabilizadas, art. 25.º, n.º 3)."""
        self.ensure_one()
        assets = self.env['l10n_ao_asset.asset'].search(
            [
                ('company_id', '=', self.company_id.id),
                ('state', '!=', 'draft'),
                ('start_date', '<=', self.date_to),
                '|',
                ('disposal_date', '=', False),
                ('disposal_date', '>=', self.date_from),
            ],
            order='category_id, start_date, id',
        )
        groups = []
        totals = dict.fromkeys(AMOUNT_COLUMNS, 0.0)
        for category in assets.category_id:
            rows = []
            subtotal = dict.fromkeys(AMOUNT_COLUMNS, 0.0)
            for asset in assets.filtered(lambda a, c=category: a.category_id == c):
                start = asset._depreciated_at(self.date_from, before=True)
                end = asset._depreciated_at(self.date_to)
                depreciation = end - start
                disposed = asset.disposal_date and asset.disposal_date <= self.date_to
                row = {
                    'rate_code': asset.rate_id.code or '',
                    'name': asset.name,
                    'acquisition_year': str(asset.acquisition_date.year),
                    'start_date': asset.start_date.strftime('%d/%m/%Y'),
                    'original_value': asset.original_value,
                    'rate': asset.rate,
                    'depreciated_start': start,
                    'depreciation': depreciation,
                    'depreciated_end': 0.0 if disposed else end,
                    'book_value': 0.0 if disposed else asset.original_value - end,
                    'disposed': asset.original_value if disposed else 0.0,
                    'disposed_depreciation': end if disposed else 0.0,
                    'not_accepted': asset.currency_id.round(depreciation * asset._fiscal_excess_ratio()),
                }
                rows.append(row)
                for key in AMOUNT_COLUMNS:
                    subtotal[key] += row[key]
                    totals[key] += row[key]
            groups.append({'name': category.name, 'rows': rows, 'subtotal': subtotal})
        unit = 1
        return {
            'company': self.company_id,
            'title': 'Mapa de reintegrações e amortizações',
            'subtitle': f'Exercício de {self.year} ({self.date_from.strftime("%d/%m/%Y")} a '
            f'{self.date_to.strftime("%d/%m/%Y")})',
            'columns': COLUMNS,
            'amount_columns': AMOUNT_COLUMNS,
            'groups': groups,
            'totals': totals,
            'fmt': lambda amount: format_amount(amount, unit),
        }

    def action_print_pdf(self):
        return self.env.ref('l10n_ao_asset.action_report_asset_map').report_action(self, config=False)

    def action_export_xlsx(self):
        self.ensure_one()
        data = self._get_report_data()
        attachment = self.env['ir.attachment'].create(
            {
                'name': f'{data["title"]} {self.year} - {self.company_id.name}.xlsx',
                'raw': self._render_xlsx(data),
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
        sheet = workbook.add_worksheet('Mapa')
        bold = workbook.add_format({'bold': True})
        header = workbook.add_format({'bold': True, 'bottom': 1, 'text_wrap': True, 'align': 'center'})
        number = workbook.add_format({'num_format': '#,##0.00;(#,##0.00);"-"'})
        number_bold = workbook.add_format({'num_format': '#,##0.00;(#,##0.00);"-"', 'bold': True, 'top': 1})
        sheet.write(0, 0, data['company'].name, bold)
        sheet.write(1, 0, f'NIF: {data["company"].vat or ""}')
        sheet.write(2, 0, f'{data["title"]} - {data["subtitle"]}', bold)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 1, 40)
        sheet.set_column(2, 11, 16)
        row = 4
        sheet.write_row(row, 0, [label for _key, label in data['columns']], header)
        for group in data['groups']:
            row += 1
            sheet.write(row, 0, group['name'], bold)
            for line in group['rows']:
                row += 1
                for col, (key, _label) in enumerate(data['columns']):
                    value = line[key]
                    if key in AMOUNT_COLUMNS:
                        sheet.write_number(row, col, value, number)
                    else:
                        sheet.write(row, col, value)
            row += 1
            sheet.write(row, 1, f'Total {group["name"]}', bold)
            for col, (key, _label) in enumerate(data['columns']):
                if key in AMOUNT_COLUMNS:
                    sheet.write_number(row, col, group['subtotal'][key], number_bold)
        row += 2
        sheet.write(row, 1, 'TOTAL', bold)
        for col, (key, _label) in enumerate(data['columns']):
            if key in AMOUNT_COLUMNS:
                sheet.write_number(row, col, data['totals'][key], number_bold)
        workbook.close()
        return output.getvalue()


class ReportL10nAoAssetMap(models.AbstractModel):
    _name = 'report.l10n_ao_asset.report_asset_map'
    _description = 'Mapa de reintegrações e amortizações (impressão)'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['l10n_ao_asset.report'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'l10n_ao_asset.report',
            'docs': wizards,
            'reports': [wizard._get_report_data() for wizard in wizards],
        }
