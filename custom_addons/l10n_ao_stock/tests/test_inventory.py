import json

from lxml import etree

from odoo.addons.l10n_ao_edi.tests.common import TODAY, L10nAoEdiCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao')
class TestL10nAoStockInventory(L10nAoEdiCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['product.category'].create(
            {'name': 'Material escolar', 'property_cost_method': 'average'}
        )
        cls.notebook = cls.env['product.product'].create(
            {
                'name': 'Caderno A4',
                'default_code': 'CAD-A4',
                'is_storable': True,
                'categ_id': cls.category.id,
                'standard_price': 150.0,
            }
        )
        cls.env['product.product'].create(
            {'name': 'Esgotado', 'default_code': 'ESG', 'is_storable': True, 'categ_id': cls.category.id}
        )
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        quant = (
            cls.env['stock.quant']
            .with_context(inventory_mode=True)
            .create(
                {
                    'product_id': cls.notebook.id,
                    'location_id': cls.warehouse.lot_stock_id.id,
                    'inventory_quantity': 40,
                }
            )
        )
        quant.action_apply_inventory()

    def _export(self, file_format, year=None):
        wizard = self.env['l10n_ao_stock.inventory.export'].create(
            {'year': year or TODAY.year, 'file_format': file_format}
        )
        action = wizard.action_export()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        return wizard, attachment.raw.content

    def test_inventory_lines(self):
        wizard = self.env['l10n_ao_stock.inventory.export'].create({'year': TODAY.year})
        self.assertEqual(
            wizard._lines(),
            [
                {
                    'cost_method': 'CMP',
                    'product_type': 'M',
                    'code': 'CAD-A4',
                    'description': '[CAD-A4] Caderno A4',
                    'quantity': 40.0,
                    'uom': self.notebook.uom_id.name,
                    'value': 6000.0,
                }
            ],
        )
        self.assertFalse(wizard.warning)

    def test_json_and_xml(self):
        _wizard, content = self._export('json')
        data = json.loads(content)
        self.assertEqual(data['StockHeader']['TaxRegistrationNumber'], '5000000001')
        self.assertEqual(data['StockHeader']['AAAA'], str(TODAY.year))
        self.assertNotIn('SemOperacoes', data['StockHeader'])
        self.assertLessEqual(len(data['StockHeader']['Assinatura']), 500)
        self.assertEqual([line['ProductCode'] for line in data['Stock']], ['CAD-A4'])
        _wizard, content = self._export('xml')
        root = etree.fromstring(content)
        self.assertEqual(root.findtext('Stock/Valor'), '6000.00')
        _wizard, content = self._export('xlsx')
        self.assertEqual(content[:2], b'PK')

    def test_no_operations(self):
        _wizard, content = self._export('json', year=TODAY.year - 1)
        data = json.loads(content)
        self.assertEqual(data['StockHeader']['SemOperacoes'], 'Sim')
        self.assertEqual(data['Stock'], [])

    def test_product_type_from_account_and_standard_warning(self):
        account = self.env['account.account'].search([('code', '=', '22.1'), ('company_ids', 'in', self.company.id)])
        if not account:
            account = self.env['account.account'].search(
                [('code', '=like', '22.1%'), ('company_ids', 'in', self.company.id)], limit=1
            )
        self.category.property_stock_valuation_account_id = account
        self.assertEqual(self.category._l10n_ao_stock_product_type(self.company), 'P')
        self.category.l10n_ao_stock_product_type = 'B'
        self.assertEqual(self.category._l10n_ao_stock_product_type(self.company), 'B')
        self.category.property_cost_method = 'standard'
        wizard = self.env['l10n_ao_stock.inventory.export'].create({'year': TODAY.year})
        self.assertIn('custo padrão', wizard.warning)
