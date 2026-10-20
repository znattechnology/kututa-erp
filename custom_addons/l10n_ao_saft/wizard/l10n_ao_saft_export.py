import json
import re
from collections import defaultdict
from datetime import timedelta

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import file_path
from odoo.tools.float_utils import float_round

NAMESPACE = 'urn:OECD:StandardAuditFile-Tax:AO_1.01_01'
XSD_PATH = 'l10n_ao_saft/data/SAFTAO1.01_01.xsd'
CONSUMER_ID = 'CF'
CONSUMER_TAX_ID = '999999999'
UNKNOWN = 'Desconhecido'
# Tabelas de cada tipo de ficheiro (DE n.º 317/20)
FILE_TABLES = {
    'C': {'accounts', 'customers', 'suppliers', 'taxes', 'ledger'},
    'F': {'customers', 'products', 'taxes', 'sales', 'payments'},
    'I': {'accounts', 'customers', 'suppliers', 'products', 'taxes', 'ledger', 'sales', 'payments', 'purchases'},
}
WITHHOLDING_TYPES = {'IRT', 'II', 'IS', 'IVA', 'IPU', 'IAC', 'OU'}


def amount2(value):
    """Montante com exactamente 2 casas decimais e sem sinal (o sinal vai no débito/crédito)."""
    return f'{abs(float_round(value or 0.0, precision_digits=2)):.2f}'


def decimal(value, digits=6):
    text = f'{abs(value or 0.0):.{digits}f}'.rstrip('0').rstrip('.')
    return text or '0'


def text(value, size, default=UNKNOWN):
    value = re.sub(r'\s+', ' ', str(value or '')).strip()
    return (value or default)[:size]


def nospace(value, size):
    return re.sub(r'\s+', '', str(value or ''))[:size]


class L10nAoSaftExport(models.TransientModel):
    _name = 'l10n_ao_saft.export'
    _description = 'Exportação SAF-T (AO)'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    file_type = fields.Selection(
        [
            ('C', 'Contabilidade (anual, até 10 de Abril)'),
            ('I', 'Contabilidade integrada com facturação'),
            ('F', 'Facturação'),
        ],
        string='Tipo de ficheiro',
        required=True,
        default='C',
    )
    date_from = fields.Date(string='De', required=True, compute='_compute_dates', store=True, readonly=False)
    date_to = fields.Date(string='Até', required=True, compute='_compute_dates', store=True, readonly=False)
    attachment_id = fields.Many2one('ir.attachment', readonly=True)

    @api.depends('company_id')
    def _compute_dates(self):
        today = fields.Date.context_today(self)
        for wizard in self:
            previous = wizard.company_id.compute_fiscalyear_dates(today)['date_from'] - timedelta(days=1)
            dates = wizard.company_id.compute_fiscalyear_dates(previous)
            wizard.date_from, wizard.date_to = dates['date_from'], dates['date_to']

    # ------------------------------------------------------------------
    def action_export(self):
        self.ensure_one()
        content = self._generate()
        nif = self.company_id.partner_id._l10n_ao_normalize_nif(self.company_id.vat or '')
        name = f'SAFT_AO_{self.file_type}_{nif}_{self.date_from}_{self.date_to}.xml'
        self.attachment_id = self.env['ir.attachment'].create(
            {
                'name': name,
                'raw': content,
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/xml',
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.attachment_id.id}?download=true',
            'target': 'download',
        }

    def _generate(self):
        """XML SAF-T (AO) validado pelo esquema; erro com os primeiros problemas se não validar."""
        if self.date_from > self.date_to:
            raise UserError(self.env._('A data inicial é posterior à data final.'))
        fiscal = self.company_id.compute_fiscalyear_dates(self.date_from)
        if self.date_to > fiscal['date_to']:
            raise UserError(self.env._('O ficheiro SAF-T não pode abranger mais do que um exercício.'))
        root = SaftBuilder(self, fiscal['date_from']).build()
        content = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        self._validate(content)
        return content

    def _validate(self, content):
        with open(file_path(XSD_PATH), 'rb') as handle:
            schema = etree.XMLSchema(etree.parse(handle))
        document = etree.fromstring(content)
        if not schema.validate(document):
            errors = '\n'.join(f'- linha {e.line}: {e.message}' for e in list(schema.error_log)[:10])
            raise UserError(self.env._('O ficheiro SAF-T não é válido segundo o esquema da AGT:\n%s', errors))


class SaftBuilder:
    """Constrói a árvore XML do SAF-T (AO) para o assistente de exportação."""

    def __init__(self, wizard, fiscal_start):
        self.wizard = wizard
        self.env = wizard.env
        self.company_id = wizard.company_id
        self.file_type = wizard.file_type
        self.date_from = wizard.date_from
        self.date_to = wizard.date_to
        self._fiscal_start = fiscal_start
        self._customers, self._suppliers, self._products = {}, {}, {}

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _el(self, parent, tag, value=None):
        element = etree.SubElement(parent, f'{{{NAMESPACE}}}{tag}')
        if value is not None:
            element.text = str(value)
        return element

    def _nif(self):
        company = self.company_id
        return company.partner_id._l10n_ao_normalize_nif(company.vat) if company.vat else ''

    def _period(self, day):
        """Mês do exercício (1 a 12)."""
        return (day.year - self._fiscal_start.year) * 12 + day.month - self._fiscal_start.month + 1

    def _datetime(self, value):
        if not value:
            return None
        local = fields.Datetime.context_timestamp(self.wizard.with_context(tz='Africa/Luanda'), value)
        return local.strftime('%Y-%m-%dT%H:%M:%S')

    def _source_id(self, record):
        return text(record.create_uid.login or record.create_uid.name, 30, 'Kututa')

    def _address(self, parent, tag, partner, *, supplier=False):
        address = self._el(parent, tag)
        if partner.street:
            self._el(address, 'StreetName', text(partner.street, 200))
        detail = ', '.join(p for p in (partner.street, partner.street2) if p) or UNKNOWN
        self._el(address, 'AddressDetail', text(detail, 250))
        self._el(address, 'City', text(partner.city, 50))
        if partner.zip:
            self._el(address, 'PostalCode', text(partner.zip, 20))
        if partner.state_id:
            self._el(address, 'Province', text(partner.state_id.name, 50))
        country = partner.country_id.code
        self._el(address, 'Country', country or ('AO' if supplier else UNKNOWN))

    # ------------------------------------------------------------------
    # Recolha
    # ------------------------------------------------------------------
    def _ledger_moves(self):
        return self.env['account.move'].search(
            [
                ('company_id', 'child_of', self.company_id.id),
                ('state', '=', 'posted'),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ],
            order='journal_id, date, name, id',
        )

    def _agt_documents(self):
        """Documentos AGT emitidos no período: (registo, payload) por facturas/talões e por recibos."""
        sales, receipts = [], []
        for model in self.env['l10n_ao_edi.document']._queue_fields():
            domain = [('company_id', '=', self.company_id.id), ('l10n_ao_edi_state', '!=', False)]
            if model == 'account.move':
                domain.append(('move_type', 'in', ('out_invoice', 'out_refund')))
            for record in self.env[model].sudo().search(domain, order='id'):
                # Documentos emitidos antes da fixação do payload: reconstrói-se a partir do registo.
                if record.l10n_ao_edi_payload:
                    payload = json.loads(record.l10n_ao_edi_payload)
                else:
                    payload = record._l10n_ao_edi_document_values()
                day = fields.Date.to_date(payload.get('documentDate'))
                if not day or not self.date_from <= day <= self.date_to:
                    continue
                (receipts if 'paymentReceipt' in payload else sales).append((record, payload))
        sales.sort(key=lambda item: (item[1]['documentType'], item[1]['documentNo']))
        receipts.sort(key=lambda item: item[1]['documentNo'])
        return sales, receipts

    def _purchase_moves(self):
        return self.env['account.move'].search(
            [
                ('company_id', 'child_of', self.company_id.id),
                ('state', '=', 'posted'),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('invoice_date', '>=', self.date_from),
                ('invoice_date', '<=', self.date_to),
            ],
            order='invoice_date, id',
        )

    def _customer_key(self, partner, payload=None):
        if not partner or (payload and payload.get('customerTaxID') == CONSUMER_TAX_ID):
            return CONSUMER_ID
        return str(partner.commercial_partner_id.id)

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------
    def build(self):
        tables = FILE_TABLES[self.file_type]
        root = etree.Element(f'{{{NAMESPACE}}}AuditFile', nsmap={None: NAMESPACE})
        self._build_header(root)
        moves = self._ledger_moves() if 'ledger' in tables else self.env['account.move']
        sales, receipts = self._agt_documents() if {'sales', 'payments'} & tables else ([], [])
        purchases = self._purchase_moves() if 'purchases' in tables else self.env['account.move']
        transactions = self._collect_transactions(moves)
        for record, payload in sales + receipts:
            self._customers.setdefault(self._customer_key(record.partner_id, payload), record.partner_id)
        for move in purchases:
            self._suppliers.setdefault(str(move.commercial_partner_id.id), move.commercial_partner_id)
        for _record, payload in sales:
            for line in payload['lines']:
                self._products.setdefault(line['productCode'], line)

        master = self._el(root, 'MasterFiles')
        if 'accounts' in tables:
            self._build_accounts(master)
        if 'customers' in tables:
            self._build_customers(master)
        if 'suppliers' in tables:
            self._build_suppliers(master)
        if 'products' in tables:
            self._build_products(master)
        if 'taxes' in tables:
            self._build_tax_table(master)
        if 'ledger' in tables:
            self._build_ledger(root, transactions)
        if {'sales', 'payments', 'purchases'} & tables:
            source = self._el(root, 'SourceDocuments')
            tx_ids = {move: tx['id'] for move, tx in transactions.items()}
            if 'sales' in tables:
                self._build_sales(source, sales, tx_ids)
            if 'payments' in tables:
                self._build_payments(source, receipts, tx_ids)
            if 'purchases' in tables:
                self._build_purchases(source, purchases)
        return root

    def _build_header(self, root):
        company = self.company_id
        if not company.vat:
            raise UserError(self.env._('Indique o NIF da empresa %s.', company.name))
        if not company.l10n_ao_saft_producer_tax_id:
            raise UserError(self.env._('Indique o NIF do produtor do software na ficha da empresa (separador AGT).'))
        header = self._el(root, 'Header')
        self._el(header, 'AuditFileVersion', '1.01_01')
        self._el(header, 'CompanyID', self._nif())
        self._el(header, 'TaxRegistrationNumber', self._nif())
        self._el(header, 'TaxAccountingBasis', self.file_type)
        self._el(header, 'CompanyName', text(company.name, 200))
        address = self._el(header, 'CompanyAddress')
        partner = company.partner_id
        if partner.street:
            self._el(address, 'StreetName', text(partner.street, 200))
        self._el(address, 'AddressDetail', text(', '.join(p for p in (partner.street, partner.street2) if p), 250))
        self._el(address, 'City', text(partner.city, 50))
        if partner.zip:
            self._el(address, 'PostalCode', text(partner.zip, 10))
        if partner.state_id:
            self._el(address, 'Province', text(partner.state_id.name, 50))
        self._el(address, 'Country', 'AO')
        self._el(header, 'FiscalYear', self._fiscal_start.year)
        self._el(header, 'StartDate', self.date_from)
        self._el(header, 'EndDate', self.date_to)
        self._el(header, 'CurrencyCode', 'AOA')
        self._el(header, 'DateCreated', fields.Date.context_today(self.wizard))
        self._el(header, 'TaxEntity', 'Global' if self.file_type == 'F' else 'Sede')
        self._el(header, 'ProductCompanyTaxID', text(company.l10n_ao_saft_producer_tax_id, 20))
        number = company.l10n_ao_edi_software_validation_number or ''
        self._el(header, 'SoftwareValidationNumber', number if re.fullmatch(r'\d+/AGT/\d{4}', number) else '0')
        product = text(company.l10n_ao_edi_product_id or 'Kututa ERP', 100).replace('/', '-')
        producer = text(company.l10n_ao_saft_producer_name or 'Kututa ERP', 100).replace('/', '-')
        self._el(header, 'ProductID', f'{product}/{producer}')
        self._el(header, 'ProductVersion', text(company.l10n_ao_edi_product_version or '1.0', 30))
        if company.phone:
            self._el(header, 'Telephone', text(company.phone, 20))
        if company.email:
            self._el(header, 'Email', text(company.email, 255))
        if company.website:
            self._el(header, 'Website', text(company.website, 60))

    # --- Tabelas mestras ---------------------------------------------
    def _build_accounts(self, master):
        engine = self.env['l10n_ao_reports.engine']
        company = self.company_id
        accounts = (
            self.env['account.account']
            .with_company(company)
            .with_context(active_test=False)
            .search([('company_ids', 'in', company.id)])
        )
        opening, closing = defaultdict(float), defaultdict(float)
        for (account, _p), (_d, _c, balance) in engine._account_totals(
            company, date_to=self.date_from - timedelta(days=1)
        ).items():
            opening[account.id] += balance
        for (account, _p), (_d, _c, balance) in engine._account_totals(company, date_to=self.date_to).items():
            closing[account.id] += balance
        children = defaultdict(list)
        for account in accounts:
            if account.parent_id:
                children[account.parent_id.id].append(account)

        def total(account, values):
            return values[account.id] + sum(total(child, values) for child in children[account.id])

        container = self._el(master, 'GeneralLedgerAccounts')
        for account in accounts.sorted(lambda a: engine._code_sort_key(a.code)):
            node = self._el(container, 'Account')
            self._el(node, 'AccountID', account.code)
            self._el(node, 'AccountDescription', text(account.name, 100))
            start, end = total(account, opening), total(account, closing)
            self._el(node, 'OpeningDebitBalance', amount2(max(start, 0.0)))
            self._el(node, 'OpeningCreditBalance', amount2(max(-start, 0.0)))
            self._el(node, 'ClosingDebitBalance', amount2(max(end, 0.0)))
            self._el(node, 'ClosingCreditBalance', amount2(max(-end, 0.0)))
            if not account.parent_id:
                category = 'GR'
            else:
                category = 'GA' if children[account.id] else 'GM'
            self._el(node, 'GroupingCategory', category)
            if account.parent_id:
                self._el(node, 'GroupingCode', account.parent_id.code)

    def _build_customers(self, master):
        company = self.company_id
        for key in sorted(self._customers, key=lambda k: (k != CONSUMER_ID, k)):
            partner = self._customers[key]
            node = self._el(master, 'Customer')
            self._el(node, 'CustomerID', key)
            if key == CONSUMER_ID:
                self._el(node, 'AccountID', UNKNOWN)
                self._el(node, 'CustomerTaxID', CONSUMER_TAX_ID)
                self._el(node, 'CompanyName', 'Consumidor final')
                address = self._el(node, 'BillingAddress')
                self._el(address, 'AddressDetail', UNKNOWN)
                self._el(address, 'City', UNKNOWN)
                self._el(address, 'Country', UNKNOWN)
            else:
                account = partner.with_company(company).property_account_receivable_id
                self._el(node, 'AccountID', account.code or UNKNOWN)
                self._el(node, 'CustomerTaxID', text(partner._l10n_ao_edi_customer_tax_id(), 30, CONSUMER_TAX_ID))
                self._el(node, 'CompanyName', text(partner.name, 200))
                self._address(node, 'BillingAddress', partner)
                if partner.phone:
                    self._el(node, 'Telephone', text(partner.phone, 20))
                if partner.email:
                    self._el(node, 'Email', text(partner.email, 255))
            self._el(node, 'SelfBillingIndicator', 0)

    def _build_suppliers(self, master):
        company = self.company_id
        for key in sorted(self._suppliers):
            partner = self._suppliers[key]
            node = self._el(master, 'Supplier')
            self._el(node, 'SupplierID', key)
            account = partner.with_company(company).property_account_payable_id
            self._el(node, 'AccountID', account.code or UNKNOWN)
            tax_id = partner._l10n_ao_normalize_nif(partner.vat) if partner.vat else CONSUMER_TAX_ID
            self._el(node, 'SupplierTaxID', text(tax_id, 20))
            self._el(node, 'CompanyName', text(partner.name, 200))
            self._address(node, 'BillingAddress', partner, supplier=True)
            if partner.phone:
                self._el(node, 'Telephone', text(partner.phone, 20))
            if partner.email:
                self._el(node, 'Email', text(partner.email, 255))
            self._el(node, 'SelfBillingIndicator', 0)

    def _product_record(self, code):
        Product = self.env['product.product'].with_context(active_test=False)
        product = Product.search([('default_code', '=', code)], limit=1)
        if not product and code.isdigit():
            product = Product.browse(int(code)).exists()
        return product

    def _build_products(self, master):
        for code in sorted(self._products):
            line = self._products[code]
            product = self._product_record(code)
            node = self._el(master, 'Product')
            self._el(node, 'ProductType', 'S' if not product or product.type == 'service' else 'P')
            self._el(node, 'ProductCode', text(code, 60))
            if product.categ_id:
                self._el(node, 'ProductGroup', text(product.categ_id.name, 50))
            self._el(node, 'ProductDescription', text(product.name or line.get('productDescription'), 200))
            self._el(node, 'ProductNumberCode', text(product.barcode or code, 60))

    def _build_tax_table(self, master):
        taxes = (
            self.env['account.tax']
            .with_context(active_test=False)
            .search([('company_id', '=', self.company_id.id), ('l10n_ao_tax_type', 'in', ('IVA', 'IS', 'NS'))])
        )
        entries = {}
        for tax in taxes:
            percentage = tax.amount if tax.amount_type == 'percent' else 0.0
            key = (tax.l10n_ao_tax_type, tax.l10n_ao_tax_region or 'AO', tax.l10n_ao_tax_code or 'NS', percentage)
            entries.setdefault(key, tax)
        table = self._el(master, 'TaxTable')
        for (tax_type, region, code, percentage), tax in sorted(entries.items()):
            node = self._el(table, 'TaxTableEntry')
            self._el(node, 'TaxType', tax_type)
            self._el(node, 'TaxCountryRegion', region)
            self._el(node, 'TaxCode', code)
            self._el(node, 'Description', text(tax.description or tax.name, 255))
            self._el(node, 'TaxPercentage', decimal(percentage, 2))

    # --- Contabilidade -------------------------------------------------
    def _collect_transactions(self, moves):
        """{lançamento: dados da transacção} para os lançamentos com débitos e créditos."""
        transactions = {}
        used = set()
        for move in moves:
            currency = move.company_currency_id
            lines = move.line_ids.filtered(lambda line, c=currency: not c.is_zero(line.balance))
            if not lines.filtered(lambda line: line.balance > 0) or not lines.filtered(lambda line: line.balance < 0):
                continue
            journal = nospace(move.journal_id.code, 30) or str(move.journal_id.id)
            archival = nospace(move.name, 20)
            if len(re.sub(r'\s+', '', move.name or '')) > 20 or not archival or archival == '/':
                archival = str(move.id)
            tx_id = f'{move.date} {journal} {archival}'
            if tx_id in used:
                tx_id = f'{move.date} {journal} {move.id}'
            used.add(tx_id)
            partner_tag = None
            if move.is_sale_document(include_receipts=True) and move.commercial_partner_id:
                partner_tag = ('CustomerID', self._customer_key(move.commercial_partner_id))
                self._customers.setdefault(partner_tag[1], move.commercial_partner_id)
            elif move.is_purchase_document(include_receipts=True) and move.commercial_partner_id:
                partner_tag = ('SupplierID', str(move.commercial_partner_id.id))
                self._suppliers.setdefault(partner_tag[1], move.commercial_partner_id)
            transactions[move] = {
                'id': tx_id,
                'journal': journal,
                'archival': archival,
                'lines': lines,
                'partner': partner_tag,
            }
        return transactions

    def _build_ledger(self, root, transactions):
        ledger = self._el(root, 'GeneralLedgerEntries')
        total_debit = sum(line.balance for tx in transactions.values() for line in tx['lines'] if line.balance > 0)
        total_credit = sum(-line.balance for tx in transactions.values() for line in tx['lines'] if line.balance < 0)
        self._el(ledger, 'NumberOfEntries', len(transactions))
        self._el(ledger, 'TotalDebit', amount2(total_debit))
        self._el(ledger, 'TotalCredit', amount2(total_credit))
        by_journal = defaultdict(list)
        for move, tx in transactions.items():
            by_journal[tx['journal'], move.journal_id].append((move, tx))
        for (journal_id, journal), items in by_journal.items():
            node = self._el(ledger, 'Journal')
            self._el(node, 'JournalID', journal_id)
            self._el(node, 'Description', text(journal.name, 200))
            for move, tx in items:
                self._build_transaction(node, move, tx)

    def _build_transaction(self, journal_node, move, tx):
        node = self._el(journal_node, 'Transaction')
        self._el(node, 'TransactionID', tx['id'])
        self._el(node, 'Period', self._period(move.date))
        self._el(node, 'TransactionDate', move.date)
        self._el(node, 'SourceID', self._source_id(move))
        self._el(node, 'Description', text(move.ref or move.name, 200))
        self._el(node, 'DocArchivalNumber', tx['archival'])
        self._el(node, 'TransactionType', 'A' if move.l10n_ao_closing_type else 'N')
        self._el(node, 'GLPostingDate', move.date)
        if tx['partner']:
            self._el(node, *tx['partner'])
        lines_node = self._el(node, 'Lines')
        entry_date = self._datetime(move.create_date)
        document = text(move.name, 30) if move.is_invoice(include_receipts=True) else None
        for tag, amount_tag, lines in (
            ('DebitLine', 'DebitAmount', tx['lines'].filtered(lambda line: line.balance > 0)),
            ('CreditLine', 'CreditAmount', tx['lines'].filtered(lambda line: line.balance < 0)),
        ):
            for line in lines:
                line_node = self._el(lines_node, tag)
                self._el(line_node, 'RecordID', line.id)
                self._el(line_node, 'AccountID', line.account_id.code)
                if document:
                    self._el(line_node, 'SourceDocumentID', document)
                self._el(line_node, 'SystemEntryDate', entry_date)
                self._el(line_node, 'Description', text(line.name or move.ref or move.name, 200))
                self._el(line_node, amount_tag, amount2(line.balance))

    # --- Documentos comerciais ----------------------------------------
    def _exemption_reason(self, code):
        exemption = self.env['l10n_ao.tax.exemption'].search([('code', '=', code)], limit=1)
        reason = text(exemption.name or f'Isenção {code}', 60)
        return reason if len(reason) >= 6 else f'Isenção {code}'

    def _status(self, record):
        return 'A' if getattr(record, 'l10n_ao_edi_state', False) == 'invalid' else 'N'

    def _build_sales(self, source, sales, tx_ids):
        container = self._el(source, 'SalesInvoices')
        valid = [(r, p) for r, p in sales if self._status(r) == 'N']
        debit = sum(line.get('debitAmount', 0.0) for _r, p in valid for line in p['lines'])
        credit = sum(line.get('creditAmount', 0.0) for _r, p in valid for line in p['lines'])
        self._el(container, 'NumberOfEntries', len(sales))
        self._el(container, 'TotalDebit', amount2(debit))
        self._el(container, 'TotalCredit', amount2(credit))
        for record, payload in sales:
            self._build_invoice(container, record, payload, tx_ids)

    def _build_invoice(self, container, record, payload, tx_ids):
        node = self._el(container, 'Invoice')
        day = fields.Date.to_date(payload['documentDate'])
        status = self._status(record)
        self._el(node, 'InvoiceNo', payload['documentNo'])
        doc_status = self._el(node, 'DocumentStatus')
        self._el(doc_status, 'InvoiceStatus', status)
        self._el(doc_status, 'InvoiceStatusDate', payload['systemEntryDate'])
        if status == 'A':
            self._el(doc_status, 'Reason', 'Rejeitado pela AGT')
        self._el(doc_status, 'SourceID', self._source_id(record))
        self._el(doc_status, 'SourceBilling', 'P')
        # O Hash do DE n.º 74/19 está por obter; sem programa validado a AGT aceita «0».
        self._el(node, 'Hash', '0')
        self._el(node, 'HashControl', '0')
        self._el(node, 'Period', self._period(day))
        self._el(node, 'InvoiceDate', day)
        self._el(node, 'InvoiceType', payload['documentType'])
        regimes = self._el(node, 'SpecialRegimes')
        self._el(regimes, 'SelfBillingIndicator', 0)
        self._el(regimes, 'CashVATSchemeIndicator', 0)
        self._el(regimes, 'ThirdPartiesBillingIndicator', 0)
        self._el(node, 'SourceID', self._source_id(record))
        if re.fullmatch(r'\d{5}', payload.get('eacCode') or ''):
            self._el(node, 'EACCode', payload['eacCode'])
        self._el(node, 'SystemEntryDate', payload['systemEntryDate'])
        if record._name == 'account.move' and record in tx_ids:
            self._el(node, 'TransactionID', tx_ids[record])
        self._el(node, 'CustomerID', self._customer_key(record.partner_id, payload))
        for line in payload['lines']:
            self._build_invoice_line(node, line, day)
        self._build_totals(node, payload['documentTotals'])
        self._build_withholdings(node, payload.get('withholdingTaxList') or [])

    def _build_invoice_line(self, invoice, line, day):
        node = self._el(invoice, 'Line')
        self._el(node, 'LineNumber', line['lineNumber'])
        self._el(node, 'ProductCode', text(line['productCode'], 60))
        self._el(node, 'ProductDescription', text(line.get('productDescription'), 200, '-'))
        self._el(node, 'Quantity', decimal(line.get('quantity')))
        self._el(node, 'UnitOfMeasure', text(line.get('unitOfMeasure'), 20, 'UN'))
        self._el(node, 'UnitPrice', decimal(line.get('unitPrice'), 2))
        self._el(node, 'TaxPointDate', day)
        reference = line.get('referenceInfo')
        if reference:
            ref_node = self._el(node, 'References')
            if reference.get('reference'):
                self._el(ref_node, 'Reference', text(reference['reference'], 60))
            if reference.get('reason'):
                self._el(ref_node, 'Reason', text(reference['reason'], 50))
        self._el(node, 'Description', text(line.get('productDescription'), 200, '-'))
        if 'debitAmount' in line:
            self._el(node, 'DebitAmount', amount2(line['debitAmount']))
        else:
            self._el(node, 'CreditAmount', amount2(line.get('creditAmount')))
        taxes = line.get('taxes') or []
        tax = next((t for t in taxes if t.get('taxType') == 'IVA'), taxes[0] if taxes else None)
        tax_node = self._el(node, 'Tax')
        self._el(tax_node, 'TaxType', tax['taxType'] if tax else 'NS')
        self._el(tax_node, 'TaxCountryRegion', (tax or {}).get('taxCountryRegion') or 'AO')
        self._el(tax_node, 'TaxCode', (tax or {}).get('taxCode') or 'NS')
        self._el(tax_node, 'TaxPercentage', decimal((tax or {}).get('taxPercentage'), 2))
        code = (tax or {}).get('taxExemptionCode')
        if code:
            self._el(node, 'TaxExemptionReason', self._exemption_reason(code))
            self._el(node, 'TaxExemptionCode', code)
        if line.get('settlementAmount'):
            self._el(node, 'SettlementAmount', amount2(line['settlementAmount']))

    def _build_totals(self, parent, totals, *, settlement=None):
        node = self._el(parent, 'DocumentTotals')
        self._el(node, 'TaxPayable', amount2(totals.get('taxPayable')))
        self._el(node, 'NetTotal', amount2(totals.get('netTotal')))
        self._el(node, 'GrossTotal', amount2(totals.get('grossTotal')))
        if settlement:
            settlement_node = self._el(node, 'Settlement')
            self._el(settlement_node, 'SettlementAmount', amount2(settlement))
        currency = totals.get('currency')
        if currency:
            currency_node = self._el(node, 'Currency')
            self._el(currency_node, 'CurrencyCode', currency['currencyCode'])
            self._el(currency_node, 'CurrencyAmount', amount2(currency['currencyAmount']))
            self._el(currency_node, 'ExchangeRate', decimal(currency['exchangeRate']))

    def _build_withholdings(self, parent, withholdings):
        for item in withholdings:
            kind = item.get('withholdingTaxType')
            node = self._el(parent, 'WithholdingTax')
            self._el(node, 'WithholdingTaxType', kind if kind in WITHHOLDING_TYPES else 'OU')
            if item.get('withholdingTaxDescription'):
                self._el(node, 'WithholdingTaxDescription', text(item['withholdingTaxDescription'], 60))
            self._el(node, 'WithholdingTaxAmount', amount2(item.get('withholdingTaxAmount')))

    def _payment_mechanism(self, payment):
        journal = getattr(payment, 'journal_id', False)
        if journal and journal.type == 'cash':
            return 'NU'
        return 'TB'

    def _build_payments(self, source, receipts, tx_ids):
        container = self._el(source, 'Payments')
        valid = [(r, p) for r, p in receipts if self._status(r) == 'N']
        credit = sum(s.get('creditAmount', 0.0) for _r, p in valid for s in p['paymentReceipt']['sourceDocuments'])
        debit = sum(s.get('debitAmount', 0.0) for _r, p in valid for s in p['paymentReceipt']['sourceDocuments'])
        self._el(container, 'NumberOfEntries', len(receipts))
        self._el(container, 'TotalDebit', amount2(debit))
        self._el(container, 'TotalCredit', amount2(credit))
        for record, payload in receipts:
            day = fields.Date.to_date(payload['documentDate'])
            status = self._status(record)
            node = self._el(container, 'Payment')
            self._el(node, 'PaymentRefNo', payload['documentNo'])
            self._el(node, 'Period', self._period(day))
            move = getattr(record, 'move_id', False)
            if move and move in tx_ids:
                self._el(node, 'TransactionID', tx_ids[move])
            self._el(node, 'TransactionDate', day)
            self._el(
                node, 'PaymentType', payload['documentType'] if payload['documentType'] in ('RC', 'RG', 'AR') else 'RG'
            )
            doc_status = self._el(node, 'DocumentStatus')
            self._el(doc_status, 'PaymentStatus', status)
            self._el(doc_status, 'PaymentStatusDate', payload['systemEntryDate'])
            if status == 'A':
                self._el(doc_status, 'Reason', 'Rejeitado pela AGT')
            self._el(doc_status, 'SourceID', self._source_id(record))
            self._el(doc_status, 'SourcePayment', 'P')
            method = self._el(node, 'PaymentMethod')
            self._el(method, 'PaymentMechanism', self._payment_mechanism(record))
            self._el(method, 'PaymentAmount', amount2(getattr(record, 'amount', 0.0)))
            self._el(method, 'PaymentDate', day)
            self._el(node, 'SourceID', self._source_id(record))
            self._el(node, 'SystemEntryDate', payload['systemEntryDate'])
            self._el(node, 'CustomerID', self._customer_key(record.partner_id, payload))
            for index, source_doc in enumerate(payload['paymentReceipt']['sourceDocuments'], start=1):
                line = self._el(node, 'Line')
                self._el(line, 'LineNumber', index)
                origin = source_doc.get('sourceDocumentID') or source_doc
                ref = self._el(line, 'SourceDocumentID')
                self._el(ref, 'OriginatingON', text(origin.get('OriginatingON') or origin.get('documentNo'), 60))
                self._el(ref, 'InvoiceDate', origin.get('InvoiceDate') or origin.get('documentDate'))
                if 'debitAmount' in source_doc:
                    self._el(line, 'DebitAmount', amount2(source_doc['debitAmount']))
                else:
                    self._el(line, 'CreditAmount', amount2(source_doc.get('creditAmount')))
            self._build_totals(node, payload['documentTotals'])
            self._build_withholdings(node, payload.get('withholdingTaxList') or [])

    def _build_purchases(self, source, purchases):
        container = self._el(source, 'PurchaseInvoices')
        self._el(container, 'NumberOfEntries', len(purchases))
        for move in purchases:
            node = self._el(container, 'Invoice')
            self._el(node, 'InvoiceNo', text(move.ref or move.name, 60))
            if move.move_type == 'in_refund' and move.reversed_entry_id:
                ref = self._el(node, 'References')
                self._el(ref, 'Reference', text(move.reversed_entry_id.ref or move.reversed_entry_id.name, 60))
                self._el(ref, 'InvoiceDate', move.reversed_entry_id.invoice_date)
            self._el(node, 'Hash', '0')
            self._el(node, 'SourceID', self._source_id(move))
            self._el(node, 'Period', self._period(move.invoice_date))
            self._el(node, 'InvoiceDate', move.invoice_date)
            self._el(node, 'PurchaseType', 'NC' if move.move_type == 'in_refund' else 'FT')
            self._el(node, 'SupplierID', str(move.commercial_partner_id.id))
            totals = self._el(node, 'DocumentTotals')
            self._el(totals, 'TaxPayable', amount2(move.amount_tax_signed))
            self._el(totals, 'NetTotal', amount2(move.amount_untaxed_signed))
            self._el(totals, 'GrossTotal', amount2(move.amount_total_signed))
            if move.currency_id != move.company_currency_id:
                currency = self._el(totals, 'Currency')
                self._el(currency, 'CurrencyCode', move.currency_id.name)
                self._el(currency, 'CurrencyAmount', amount2(move.amount_total))
                rate = abs(move.amount_total_signed / move.amount_total) if move.amount_total else 1.0
                self._el(currency, 'ExchangeRate', decimal(rate))
