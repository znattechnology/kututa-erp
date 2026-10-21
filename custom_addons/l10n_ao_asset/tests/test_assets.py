from datetime import date, timedelta

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
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

    def _bill(self, lines, post=True):
        bill = self.env['account.move'].create(
            {
                'move_type': 'in_invoice',
                'partner_id': self.supplier.id,
                'invoice_date': '2026-02-05',
                'invoice_line_ids': [Command.create(vals) for vals in lines],
            }
        )
        if post:
            bill.action_post()
        return bill

    def test_bill_discount_shared_account_and_reset(self):
        account = self._account('11.5')
        bill = self._bill(
            [
                {'name': 'Secretária', 'quantity': 1, 'price_unit': 500_000, 'account_id': account.id, 'tax_ids': []},
                {'name': 'Desconto', 'quantity': 1, 'price_unit': -50_000, 'account_id': account.id, 'tax_ids': []},
                {'name': 'Cadeiras', 'quantity': 10, 'price_unit': 25_000, 'account_id': account.id, 'tax_ids': []},
            ]
        )
        assets = bill.line_ids.l10n_ao_asset_ids
        self.assertEqual(len(assets), 2)
        desk = assets.filtered(lambda a: a.name == 'Secretária')
        chairs = assets.filtered(lambda a: a.name == 'Cadeiras')
        # O desconto reparte-se pelas linhas positivas: 500 000 × (1 − 50 000 / 750 000).
        self.assertEqual(desk.original_value, 466_666.67)
        self.assertEqual(chairs.original_value, 233_333.33)
        self.assertEqual(chairs.quantity, 10)
        self.assertTrue(chairs.low_value)
        # A conta 11.5 é partilhada (informática e mobiliário): a ficha avisa.
        self.assertIn('partilhada', desk.message_ids[0].body)
        # Reabrir a factura apaga as fichas em rascunho; relançar cria-as com os valores novos.
        bill.button_draft()
        self.assertFalse(bill.line_ids.l10n_ao_asset_ids.exists())
        bill.invoice_line_ids.filtered(lambda line: line.name == 'Desconto').unlink()
        bill.action_post()
        assets = bill.line_ids.l10n_ao_asset_ids
        self.assertEqual(sorted(assets.mapped('original_value')), [250_000, 500_000])
        assets[0].action_confirm()
        with self.assertRaisesRegex(UserError, 'confirmadas'):
            bill.button_draft()

    def test_vendor_refund(self):
        account = self._account('11.5')
        bill = self._bill(
            [{'name': 'Servidor', 'quantity': 1, 'price_unit': 400_000, 'account_id': account.id, 'tax_ids': []}]
        )
        asset = bill.line_ids.l10n_ao_asset_ids
        refund = bill._reverse_moves([{'invoice_date': '2026-02-20'}], cancel=False)
        refund.invoice_line_ids.price_unit = 50_000
        refund.action_post()
        # Ficha em rascunho: o valor é abatido.
        self.assertEqual(asset.original_value, 350_000)
        asset.action_confirm()
        refund2 = bill._reverse_moves([{'invoice_date': '2026-03-20'}], cancel=False)
        refund2.invoice_line_ids.price_unit = 10_000
        refund2.action_post()
        # Ficha confirmada: fica uma actividade para regularizar.
        self.assertEqual(asset.original_value, 350_000)
        self.assertTrue(asset.activity_ids)

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
        # 33,33% = vida útil de 3 anos: 36 quotas de 10 000 (a última acerta o remanescente).
        self.assertEqual(lines[0].date, date(2026, 1, 31))
        self.assertEqual(lines[0].amount, 10_000)
        self.assertEqual(len(lines), 36)
        self.assertEqual(lines[-1].date, date(2028, 12, 31))
        self.assertAlmostEqual(sum(lines.mapped('amount')), 360_000)
        asset._post_depreciation(date(2026, 3, 31))
        moves = lines.move_id
        self.assertEqual(len(moves), 3)
        self.assertEqual(set(moves.mapped('state')), {'posted'})
        balances = {line.account_id.code: line.balance for line in moves[0].line_ids}
        self.assertEqual(balances, {'73.1.5': 10_000, '18.1.5': -10_000})
        self.assertEqual(asset.depreciated_amount, 30_000)
        self.assertEqual(asset.book_value, 330_000)
        with self.assertRaises(UserError):
            asset.action_reset_draft()
        with self.assertRaisesRegex(UserError, 'só se alteram em rascunho'):
            asset.original_value = 1
        # Um lançamento cancelado volta a ser lançado; um rascunho bloqueia a alienação.
        moves[1].button_draft()
        with self.assertRaisesRegex(UserError, 'rascunho'):
            self.env['l10n_ao_asset.disposal'].create({'asset_id': asset.id, 'date': '2026-05-10'}).action_confirm()
        moves[1].button_cancel()
        self.assertEqual(len(asset._pending_lines()), 34)
        asset._post_depreciation(date(2026, 3, 31))
        self.assertEqual(len(asset._posted_lines()), 3)
        self.assertNotEqual(lines[1].move_id, moves[1])

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
        self.assertEqual(balances, {'11.5': -360_000, '18.1.5': 30_000, '78.3.3': 330_000})
        # Anular a alienação repõe o plano a seguir às quotas lançadas.
        asset.action_cancel_disposal()
        self.assertEqual(asset.state, 'open')
        self.assertEqual(move.state, 'cancel')
        self.assertEqual(len(asset.line_ids), 36)
        self.assertEqual(len(asset._posted_lines()), 3)

    def test_disposal_guards(self):
        asset = self._asset()
        asset.action_confirm()
        asset._post_depreciation(date(2026, 9, 30))
        wizard = self.env['l10n_ao_asset.disposal'].create({'asset_id': asset.id, 'date': '2026-06-15'})
        self.assertEqual((wizard.to_post_count, wizard.to_drop_count), (0, 27))
        with self.assertRaisesRegex(UserError, 'Já há quotas lançadas'):
            wizard.action_confirm()
        wizard.date = fields.Date.context_today(wizard) + timedelta(days=40)
        with self.assertRaisesRegex(UserError, 'data futura'):
            wizard.action_confirm()
        wizard.date = fields.Date.context_today(wizard)
        wizard.action_confirm()
        self.assertEqual(asset.state, 'disposed')
        self.assertEqual(len(asset._posted_lines()), 9)

    def test_lock_date_and_cron(self):
        asset = self._asset(start_date='2025-01-01', acquisition_date='2025-01-01')
        self.company.fiscalyear_lock_date = date(2025, 12, 31)
        with self.assertRaisesRegex(UserError, 'período bloqueado'):
            asset.action_confirm()
        asset.write({'opening_depreciation': 120_000, 'opening_date': '2025-12-31'})
        asset.action_confirm()
        self.assertEqual(asset.line_ids[0].date, date(2026, 1, 31))
        self.assertEqual(len(asset.line_ids), 24)
        # O cron isola os erros: a conta arquivada só trava esta ficha.
        other = self._asset(name='Outro')
        other.action_confirm()
        self.it.account_expense_id.active = False
        self.env['l10n_ao_asset.asset']._cron_post_depreciation()
        self.assertFalse(other._posted_lines())
        self.assertIn('falhou', other.message_ids[0].body)
        self.it.account_expense_id.active = True

    def test_non_depreciable_and_quantity(self):
        land = self._asset(name='Terreno', original_value=5_000_000)
        land.rate = 0
        land.action_confirm()
        self.assertEqual((land.state, len(land.line_ids)), ('open', 0))
        chairs = self._asset(name='Cadeiras', original_value=250_000, quantity=10)
        self.assertTrue(chairs.low_value)
        with self.assertRaisesRegex(ValidationError, 'reduzido valor'):
            self._asset(name='Grande', original_value=5_000_000, low_value=True)
        # Ficha já amortizada no arranque fecha ao confirmar.
        done = self._asset(name='Velho', opening_depreciation=360_000, opening_date='2026-01-10')
        done.action_confirm()
        self.assertEqual(done.state, 'close')
        # Mudar a taxa legal muda a taxa; só a taxa acima da legal é «não aceite».
        furniture = self._asset(name='Secretária', original_value=100_000)
        furniture.rate_id = self.env['l10n_ao_asset.rate'].search([('code', '=', 'G.5.5.2')])
        self.assertEqual(furniture.rate, 12.5)
        furniture.rate = 25
        self.assertAlmostEqual(furniture._fiscal_excess_ratio(), 0.5)

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
        self.assertEqual(rows['Bem']['depreciation'], 120_000)
        self.assertEqual(rows['Bem']['book_value'], 240_000)
        # Viatura de 30 M: 25% ao ano = 7,5 M; um terço (acima de 20 M) não é aceite.
        self.assertEqual(rows['Viatura']['depreciation'], 7_500_000)
        self.assertEqual(rows['Viatura']['not_accepted'], 2_500_000)
        self.assertEqual(data['totals']['depreciation'], 7_620_000)
        html = self.env['ir.actions.report']._render_qweb_html('l10n_ao_asset.report_asset_map', report.ids)[0]
        self.assertIn(b'Mapa de reintegra', html)
        action = report.action_export_xlsx()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        self.assertEqual(attachment.raw.content[:2], b'PK')
