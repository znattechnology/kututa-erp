import io
import json
from collections import Counter
from datetime import date, datetime, time

import pytz
import xlsxwriter
from lxml import etree

from odoo import api, fields, models
from odoo.addons.l10n_ao_edi.tools.jws import jws_sign
from odoo.exceptions import UserError

COST_METHODS = {'fifo': 'FIFO', 'average': 'CMP', 'standard': 'CMP'}
SIGNATURE_MAX = 500
# Campos da Circular n.º 05/GACA/GJ/DSF/AGT/2026. As etiquetas sem nome em inglês na Circular
# (método de custeio, valor, ano, sem operações) seguem a designação portuguesa: a confirmar com a AGT.
HEADER_FIELDS = [
    ('Assinatura', 'signature'),
    ('TaxRegistrationNumber', 'nif'),
    ('DateCreated', 'date_created'),
    ('SoftwareValidationNumber', 'software'),
    ('ProductID', 'product_id'),
    ('ProductVersion', 'product_version'),
    ('AAAA', 'year'),
    ('SemOperacoes', 'no_operations'),
]
STOCK_COLUMNS = [
    ('MetodoCusteio', 'Método de custeio', 'cost_method'),
    ('Product', 'Tipo de produto (Product)', 'product_type'),
    ('ProductCode', 'Identificador único do produto (ProductCode)', 'code'),
    ('ProductDescription', 'Descrição do produto (ProductDescription)', 'description'),
    ('Quantity', 'Quantidade (Quantity)', 'quantity'),
    ('UnitOfMeasure', 'Unidade de medida (UnitOfMeasure)', 'uom'),
    ('Valor', 'Valor', 'value'),
]


def format_quantity(quantity, decimals):
    return f'{quantity:.{decimals}f}'


class L10nAoStockInventoryExport(models.TransientModel):
    _name = 'l10n_ao_stock.inventory.export'
    _description = 'SAF-T de inventário (AGT)'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],
    )
    year = fields.Integer(
        string='Exercício',
        required=True,
        default=lambda self: fields.Date.context_today(self).year - 1,
        help='Existências finais a 31 de Dezembro (o período de tributação é o ano civil, CII art. 77.º).',
    )
    file_format = fields.Selection(
        [('xlsx', 'Excel'), ('xml', 'XML'), ('json', 'JSON')], string='Formato', required=True, default='xlsx'
    )
    warning = fields.Text(compute='_compute_warning')

    @api.depends('company_id', 'year')
    def _compute_warning(self):
        today = fields.Date.context_today(self)
        for wizard in self:
            messages = []
            if wizard.year == today.year:
                messages.append(
                    self.env._(
                        'O exercício %s ainda não terminou: o ficheiro terá as existências de hoje.', wizard.year
                    )
                )
            standard = wizard._products().filtered(lambda p: p.cost_method == 'standard')
            if standard:
                messages.append(
                    self.env._(
                        '%s artigo(s) com custo padrão: a AGT só prevê FIFO, LIFO ou custo médio ponderado (CMP); '
                        'saem como CMP. Reveja o método de custeio das categorias.',
                        len(standard),
                    )
                )
            wizard.warning = '\n'.join(messages) or False

    # ------------------------------------------------------------------
    def _check_company(self):
        if self.company_id not in self.env.companies:
            raise UserError(self.env._('Não tem acesso à empresa %s.', self.company_id.name))

    def _check_year(self):
        today = fields.Date.context_today(self)
        if not 2000 <= self.year <= today.year:
            raise UserError(self.env._('Indique um exercício entre 2000 e %s.', today.year))

    def _at_date(self):
        """31/12 às 23:59:59 em Luanda, em UTC, para a valorização à data."""
        local = pytz.timezone('Africa/Luanda').localize(datetime.combine(date(self.year, 12, 31), time.max))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _products(self):
        """Artigos valorizados da empresa, como o relatório de valorização do Odoo: localizações
        valorizadas, stock próprio (sem consignação) e sem kits."""
        company = self.company_id
        products = (
            self.env['product.product']
            .sudo()
            .with_company(company)
            .with_context(active_test=False, allowed_company_ids=company.ids, skip_kit_qty_available=True)
            ._with_valuation_context()
        )
        return products.search(company._get_inventory_valuation_products_domain())

    def _lines(self):
        """Existências finais a 31/12: quantidade e valor pela valorização do Odoo à data."""
        self._check_company()
        self._check_year()
        company = self.company_id
        at_date = self._at_date()
        products = self._products().with_context(at_date=at_date, to_date=at_date)
        decimals = self.env['decimal.precision'].precision_get('Product Unit')
        lines = []
        negatives = []
        for product in products.sorted(lambda p: p.default_code or str(p.id)):
            quantity = product.qty_available
            if product.uom_id.is_zero(quantity):
                continue
            if quantity < 0:
                negatives.append(product.display_name)
            lines.append(
                {
                    'cost_method': COST_METHODS.get(product.cost_method, 'CMP'),
                    'product_type': product.categ_id._l10n_ao_stock_product_type(company),
                    # O mesmo código da facturação electrónica (productCode)
                    'code': (product.default_code or str(product.id))[:60],
                    'description': (product.name or '-')[:200],
                    'quantity': product.uom_id.round(quantity),
                    'quantity_decimals': decimals,
                    'uom': (product.uom_id.name or 'UN')[:20],
                    'value': company.currency_id.round(product.total_value),
                }
            )
        if negatives:
            raise UserError(
                self.env._(
                    'Há artigos com existências negativas a 31/12/%(year)s: %(products)s. Regularize o stock antes '
                    'de comunicar o inventário.',
                    year=self.year,
                    products=', '.join(negatives[:20]),
                )
            )
        duplicates = [code for code, count in Counter(line['code'] for line in lines).items() if count > 1]
        if duplicates:
            raise UserError(
                self.env._(
                    'O código de produto tem de ser único no inventário. Códigos repetidos: %s.',
                    ', '.join(sorted(duplicates)[:20]),
                )
            )
        return lines

    def _header(self, lines):
        company = self.company_id
        if not company.vat:
            raise UserError(self.env._('Indique o NIF da empresa %s.', company.name))
        header = {
            'nif': company.partner_id._l10n_ao_normalize_nif(company.vat),
            'date_created': fields.Date.to_string(fields.Date.context_today(self)),
            'software': (company.l10n_ao_edi_software_validation_number or '0')[:17],
            'product_id': (company.l10n_ao_edi_product_id or 'Kututa ERP')[:255],
            'product_version': (company.l10n_ao_edi_product_version or '1.0')[:20],
            'year': str(self.year),
            'no_operations': '' if lines else 'Sim',
        }
        # Assinatura digital (até 500 caracteres): assinatura RS256 do cabeçalho e das linhas, com a chave do
        # contribuinte ou, na sua falta, a do produtor do software.
        key = company.sudo().l10n_ao_edi_taxpayer_key_id or company.sudo().l10n_ao_edi_software_key_id
        if not key:
            raise UserError(
                self.env._('Configure a chave privada do contribuinte ou do produtor (separador AGT da empresa).')
            )
        signed = {
            'header': dict(header),
            'stock': [{k: v for k, v in line.items() if k != 'quantity_decimals'} for line in lines],
        }
        signature = jws_sign(signed, key).rsplit('.', 1)[1]
        if len(signature) > SIGNATURE_MAX:
            raise UserError(
                self.env._(
                    'A assinatura tem %(size)s caracteres e a AGT aceita %(max)s: use uma chave RSA de 2048 bits.',
                    size=len(signature),
                    max=SIGNATURE_MAX,
                )
            )
        header['signature'] = signature
        return header

    def action_export(self):
        self.ensure_one()
        lines = self._lines()
        header = self._header(lines)
        content = getattr(self, f'_render_{self.file_format}')(header, lines)
        attachment = self.env['ir.attachment'].create(
            {
                'name': f'SAFT_AO_Inventario_{header["nif"]}_{self.year}.{self.file_format}',
                'raw': content,
                'res_model': self._name,
                'res_id': self.id,
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'download',
        }

    # ------------------------------------------------------------------
    def _cell(self, line, key):
        if key == 'value':
            return f'{line["value"]:.2f}'
        if key == 'quantity':
            return format_quantity(line['quantity'], line['quantity_decimals'])
        return str(line[key])

    def _render_xml(self, header, lines):
        root = etree.Element('SAFTInventario')
        header_node = etree.SubElement(root, 'StockHeader')
        for tag, key in HEADER_FIELDS:
            if header[key]:
                etree.SubElement(header_node, tag).text = header[key]
        for line in lines:
            stock = etree.SubElement(root, 'Stock')
            for tag, _label, key in STOCK_COLUMNS:
                etree.SubElement(stock, tag).text = self._cell(line, key)
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)

    def _render_json(self, header, lines):
        data = {
            'StockHeader': {tag: header[key] for tag, key in HEADER_FIELDS if header[key]},
            'Stock': [{tag: line[key] for tag, _label, key in STOCK_COLUMNS} for line in lines],
        }
        return json.dumps(data, ensure_ascii=False, indent=2).encode()

    def _render_xlsx(self, header, lines):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        bold = workbook.add_format({'bold': True})
        head = workbook.add_format({'bold': True, 'bottom': 1, 'text_wrap': True})
        number = workbook.add_format({'num_format': '0.00'})
        quantity = workbook.add_format({'num_format': '0.00####'})
        sheet = workbook.add_worksheet('StockHeader')
        sheet.set_column(0, 0, 28)
        sheet.set_column(1, 1, 60)
        sheet.write_row(0, 0, ['Parâmetro', 'Valor'], head)
        for row, (tag, key) in enumerate(HEADER_FIELDS, start=1):
            sheet.write(row, 0, tag, bold)
            sheet.write(row, 1, header[key])
        sheet = workbook.add_worksheet('Stock')
        sheet.set_column(0, 1, 14)
        sheet.set_column(2, 3, 40)
        sheet.set_column(4, 6, 16)
        sheet.write_row(0, 0, [label for _tag, label, _key in STOCK_COLUMNS], head)
        for row, line in enumerate(lines, start=1):
            for col, (_tag, _label, key) in enumerate(STOCK_COLUMNS):
                value = line[key]
                if key == 'quantity':
                    sheet.write_number(row, col, value, quantity)
                elif key == 'value':
                    sheet.write_number(row, col, value, number)
                else:
                    sheet.write(row, col, value)
        workbook.close()
        return output.getvalue()
