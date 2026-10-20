from datetime import date

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao')
class TestL10nAoAsset(AccountTestInvoicingCommon):
    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.categories = cls.env['l10n_ao_asset.category'].search([('company_id', '=', cls.company.id)])
        cls.it = cls.categories.filtered(lambda c: c.name == 'Equipamento informático')
        cls.vehicles = cls.categories.filtered(lambda c: c.name == 'Viaturas ligeiras')
        cls.supplier = cls.env['res.partner'].create({'name': 'Fornecedor de equipamento'})

    def _account(self, code):
        return self.env['account.account'].search([('code', '=', code), ('company_ids', 'in', self.company.id)])

    def _asset(self, **vals):
        return self.env['l10n_ao_asset.asset'].create(
            {
                'name': 'Bem',
                'category_id': self.it.id,
                'acquisition_date': '2026-01-10',
                'start_date': '2026-01-10',
                'original_value': 360_000,
                **vals,
            }
        )

    def test_default_categories(self):
        self.assertEqual(len(self.categories), 11)
        self.assertEqual(self.it.rate_id.code, 'G.3.1')
        self.assertEqual(self.it.rate, 33.33)
        self.assertEqual(self.it.account_asset_id.code, '11.5')
        self.assertEqual(self.it.account_depreciation_id.code, '18.1.5')
        self.assertEqual(self.it.account_expense_id.code, '73.1.5')
        self.assertTrue(self.vehicles.vehicle_limit)
        self.assertEqual(self.env['l10n_ao_asset.rate'].search_count([]), 479)

    def test_asset_from_vendor_bill(self):
        bill = self.env['account.move'].create(
            {
                'move_type': 'in_invoice',
                'partner_id': self.supplier.id,
                'invoice_date': '2026-02-05',
                'invoice_line_ids': [
                    Command.create(
                        {
                            'name': 'Servidor',
                            'quantity': 1,
                            'price_unit': 360_000,
                            'account_id': self._account('11.5').id,
                            'tax_ids': [],
                        }
                    ),
                    Command.create({'name': 'Instalação', 'quantity': 1, 'price_unit': 10_000, 'tax_ids': []}),
                ],
            }
        )
        bill.action_post()
        asset = bill.line_ids.l10n_ao_asset_ids
        self.assertEqual(len(asset), 1)
        self.assertEqual(bill.l10n_ao_asset_count, 1)
        self.assertRecordValues(
            asset,
            [
                {
                    'name': 'Servidor',
                    'state': 'draft',
                    'category_id': self.it.id,
                    'original_value': 360_000,
                    'start_date': date(2026, 2, 5),
                    'partner_id': self.supplier.id,
                }
            ],
        )

    def test_monthly_board_and_posting(self):
        asset = self._asset()
        asset.action_confirm()
        lines = asset.line_ids
        # 360 000 × 33,33% / 12 = 9 999 por mês; a última quota acerta o remanescente.
        self.assertEqual(lines[0].date, date(2026, 1, 31))
        self.assertEqual(lines[0].amount, 9_999)
        self.assertEqual(len(lines), 37)
        self.assertEqual(lines[-1].amount, 36)
        self.assertAlmostEqual(sum(lines.mapped('amount')), 360_000)
        asset._post_depreciation(date(2026, 3, 31))
        moves = lines.move_id
        self.assertEqual(len(moves), 3)
        self.assertEqual(set(moves.mapped('state')), {'posted'})
        balances = {line.account_id.code: line.balance for line in moves[0].line_ids}
        self.assertEqual(balances, {'73.1.5': 9_999, '18.1.5': -9_999})
        self.assertEqual(asset.depreciated_amount, 29_997)
        self.assertEqual(asset.book_value, 330_003)
        with self.assertRaises(UserError):
            asset.action_reset_draft()

    def test_low_value_asset(self):
        asset = self._asset(original_value=25_000)
        self.assertTrue(asset.low_value)
        asset.action_confirm()
        self.assertEqual(len(asset.line_ids), 1)
        self.assertEqual(asset.line_ids.amount, 25_000)
        self.assertEqual(asset.line_ids.date, date(2026, 1, 31))

    def test_yearly_board(self):
        asset = self._asset(original_value=100_000, start_date='2025-06-15', acquisition_date='2025-06-15')
        asset.write({'rate': 25, 'method_period': 'year'})
        asset.action_confirm()
        self.assertEqual(asset.line_ids.mapped('date'), [date(y, 12, 31) for y in (2025, 2026, 2027, 2028)])
        self.assertEqual(set(asset.line_ids.mapped('amount')), {25_000})

    def test_opening_depreciation(self):
        asset = self._asset(
            original_value=120_000,
            start_date='2024-01-01',
            acquisition_date='2024-01-01',
            opening_depreciation=60_000,
            opening_date='2025-12-31',
        )
        asset.rate = 25
        asset.action_confirm()
        self.assertEqual(asset.line_ids[0].date, date(2026, 1, 31))
        self.assertEqual(len(asset.line_ids), 24)
        self.assertEqual(set(asset.line_ids.mapped('amount')), {2_500})
        self.assertEqual(asset._depreciated_at(date(2026, 1, 1)), 60_000)

    def test_disposal(self):
        asset = self._asset()
        asset.action_confirm()
        wizard = self.env['l10n_ao_asset.disposal'].create(
            {'asset_id': asset.id, 'disposal_type': 'scrap', 'date': '2026-04-15'}
        )
        self.assertEqual(wizard.loss_account_id.code, '78.3.3')
        action = wizard.action_confirm()
        # Quotas de Janeiro a Março; Abril (mês do abate) já não tem quota.
        self.assertEqual(len(asset.line_ids), 3)
        self.assertEqual(asset.state, 'disposed')
        move = self.env['account.move'].browse(action['res_id'])
        balances = {line.account_id.code: line.balance for line in move.line_ids}
        self.assertEqual(balances, {'11.5': -360_000, '18.1.5': 29_997, '78.3.3': 330_003})

    def test_asset_map(self):
        asset = self._asset()
        asset.action_confirm()
        asset._post_depreciation(date(2026, 12, 31))
        vehicle = self._asset(
            name='Viatura', category_id=self.vehicles.id, original_value=30_000_000, start_date='2026-01-01'
        )
        vehicle.action_confirm()
        vehicle._post_depreciation(date(2026, 12, 31))
        report = self.env['l10n_ao_asset.report'].create({'year': 2026})
        data = report._get_report_data()
        rows = {row['name']: row for group in data['groups'] for row in group['rows']}
        self.assertEqual(rows['Bem']['depreciation'], 119_988)
        self.assertEqual(rows['Bem']['book_value'], 360_000 - 119_988)
        # Viatura de 30 M: 25% ao ano = 7,5 M; um terço (acima de 20 M) não é aceite.
        self.assertEqual(rows['Viatura']['depreciation'], 7_500_000)
        self.assertEqual(rows['Viatura']['not_accepted'], 2_500_000)
        self.assertEqual(data['totals']['depreciation'], 7_619_988)
        html = self.env['ir.actions.report']._render_qweb_html('l10n_ao_asset.report_asset_map', report.ids)[0]
        self.assertIn(b'Mapa de reintegra', html)
        action = report.action_export_xlsx()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        self.assertEqual(attachment.raw.content[:2], b'PK')
