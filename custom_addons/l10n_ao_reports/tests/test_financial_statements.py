from datetime import date

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.l10n_ao_reports.models.l10n_ao_reports_engine import is_transfer_account
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao')
class TestL10nAoFinancialStatements(AccountTestInvoicingCommon):
    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.engine = cls.env['l10n_ao_reports.engine']
        cls.bank = cls.company_data['default_journal_bank'].default_account_id.code
        cls.client_a = cls.env['res.partner'].create({'name': 'Cliente A'})
        cls.client_b = cls.env['res.partner'].create({'name': 'Cliente B'})
        cls.supplier = cls.env['res.partner'].create({'name': 'Fornecedor'})
        # Exercício de 2025 (resultado: 500 000 - 100 000 - 120 000 - 84 000 = 196 000)
        cls._entry('2025-01-31', [(cls.bank, 1_000_000), ('51', -1_000_000)])
        cls._entry('2025-03-15', [('11.4', 600_000), ('32.1.2.1', -600_000, cls.supplier)])
        cls._entry('2025-06-30', [('31.1.2.1', 500_000, cls.client_a), ('62.1.1', -500_000)])
        # Adiantamento do cliente B: saldo credor na conta de clientes -> contas a pagar
        cls._entry('2025-06-30', [(cls.bank, 50_000), ('31.1.2.1', -50_000, cls.client_b)])
        cls._entry('2025-12-31', [('73.1.4', 120_000), ('18.1.4', -120_000)])
        cls._entry('2025-12-31', [('72.1', 100_000), (cls.bank, -100_000)])
        cls._entry('2025-12-31', [('87.1', 84_000), ('34.1.1', -84_000)])

    @classmethod
    def _account(cls, code):
        return cls.env['account.account'].search([('code', '=', code), ('company_ids', 'in', cls.company.id)])

    @classmethod
    def _entry(cls, move_date, lines):
        move = cls.env['account.move'].create(
            {
                'move_type': 'entry',
                'date': move_date,
                'journal_id': cls.company_data['default_journal_misc'].id,
                'line_ids': [
                    Command.create(
                        {
                            'account_id': cls._account(line[0]).id,
                            'partner_id': line[2].id if len(line) > 2 else False,
                            'debit': max(line[1], 0),
                            'credit': max(-line[1], 0),
                        }
                    )
                    for line in lines
                ],
            }
        )
        move.action_post()
        return move

    def _closing(self, operation, year):
        wizard = self.env['l10n_ao_reports.closing'].create({'operation': operation, 'year': year})
        action = wizard.action_confirm()
        return self.env['account.move'].browse(action['res_id'])

    def _bs(self, at, comparative=False):
        lines = self.engine._balance_sheet(self.company, at, comparative=comparative, hide_empty=False)['lines']
        return {line['key']: line['amounts'] for line in lines if line['amounts']}

    def _is(self, date_from, date_to):
        lines = self.engine._income_statement(self.company, date_from, date_to, comparative=False, hide_empty=False)
        return {line['key']: line['amounts'][0] for line in lines['lines']}

    # ------------------------------------------------------------------
    def test_transfer_accounts(self):
        self.assertTrue(is_transfer_account('61.9'))
        self.assertTrue(is_transfer_account('68.19'))
        self.assertTrue(is_transfer_account('82.19'))
        self.assertTrue(is_transfer_account('87.9'))
        # Rubricas com código x.9 que não são transferências
        self.assertFalse(is_transfer_account('68.9'))
        self.assertFalse(is_transfer_account('82.9'))
        self.assertFalse(is_transfer_account('61.3'))

    def test_balance_sheet(self):
        bs = self._bs(date(2025, 12, 31))
        self.assertEqual(bs['corporeo'], [480_000])
        self.assertEqual(bs['contas_receber'], [500_000])
        self.assertEqual(bs['disponibilidades'], [950_000])
        self.assertEqual(bs['t_activo'], [1_930_000])
        self.assertEqual(bs['capital'], [1_000_000])
        self.assertEqual(bs['resultado'], [196_000])
        self.assertEqual(bs['transitados'], [0])
        # Fornecedor 600 000 + adiantamento do cliente B 50 000 + imposto 84 000
        self.assertEqual(bs['contas_pagar'], [734_000])
        self.assertEqual(bs['t_cpp'], [1_930_000])

    def test_income_statement(self):
        dr = self._is(date(2025, 1, 1), date(2025, 12, 31))
        self.assertEqual(dr['servicos'], 500_000)
        self.assertEqual(dr['pessoal'], -100_000)
        self.assertEqual(dr['amortizacoes'], -120_000)
        self.assertEqual(dr['r_operacionais'], 280_000)
        self.assertEqual(dr['r_antes_impostos'], 280_000)
        self.assertEqual(dr['imposto_corrente'], -84_000)
        self.assertEqual(dr['r_liquido'], 196_000)

    def test_thousands(self):
        lines = self.engine._balance_sheet(self.company, date(2025, 12, 31), comparative=False, unit=1000)['lines']
        values = {line['key']: line['amounts'][0] for line in lines if line['amounts']}
        self.assertEqual(values['t_activo'], 1_930)
        self.assertEqual(values['resultado'], 196)

    def test_closing_and_transfer(self):
        closing = self._closing('close', 2025)
        self.assertEqual(closing.date, date(2025, 12, 31))
        self.assertEqual(closing.journal_id.code, 'APR')
        balances = {line.account_id.code: line.balance for line in closing.line_ids}
        self.assertEqual(balances['62.9'], 500_000)
        self.assertEqual(balances['82.2'], -500_000)
        self.assertEqual(balances['82.19'], 280_000)
        self.assertEqual(balances['88.1'], -280_000)
        self.assertEqual(balances['87.9'], -84_000)
        self.assertEqual(balances['88.5'], 84_000)
        # O apuramento não altera as demonstrações financeiras
        self.assertEqual(self._is(date(2025, 1, 1), date(2025, 12, 31))['r_liquido'], 196_000)
        bs = self._bs(date(2025, 12, 31))
        self.assertEqual(bs['resultado'], [196_000])
        self.assertEqual(bs['t_cpp'], [1_930_000])
        with self.assertRaisesRegex(UserError, 'já foi apurado'):
            self._closing('close', 2025)

        transfer = self._closing('transfer', 2025)
        self.assertEqual(transfer.date, date(2026, 1, 1))
        balances = {line.account_id.code: line.balance for line in transfer.line_ids}
        self.assertEqual(balances, {'88.9': 196_000, '81.1.1': -196_000})

        self._entry('2026-02-15', [(self.bank, 10_000), ('69.5', -10_000)])
        bs = self._bs(date(2026, 12, 31), comparative=True)
        self.assertEqual(bs['resultado'], [10_000, 196_000])
        self.assertEqual(bs['transitados'], [196_000, 0])
        self.assertEqual(bs['t_activo'], bs['t_cpp'])
        dr = self._is(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(dr['r_extraordinarios'], 10_000)
        self.assertEqual(dr['r_liquido'], 10_000)
        # O exercício de 2026 pode agora ser apurado
        closing_2026 = self._closing('close', 2026)
        self.assertEqual({line.account_id.code: line.balance for line in closing_2026.line_ids}['88.6'], -10_000)

    def test_trial_balance_after_closing_and_transfer(self):
        self._closing('close', 2025)
        self._closing('transfer', 2025)
        result = self.engine._trial_balance(self.company, date(2026, 1, 1), date(2026, 12, 31))
        by_code = {line['code']: line['amounts'] for line in result['lines']}
        # A 88 transita com o resultado e é saldada pela transferência (1/1/2026); não há resultados por apurar.
        self.assertEqual(by_code['88'], [-196_000, 196_000, 0, 0, 0])
        self.assertEqual(by_code['81.1.1'][2], 196_000)
        self.assertNotIn('Resultados de exercícios anteriores por apurar', [line['name'] for line in result['lines']])
        # Antes da transferência, a 88 tem o resultado como saldo inicial.
        self._entry('2026-03-01', [(self.bank, 10_000), ('69.5', -10_000)])
        self._closing('close', 2026)
        result = self.engine._trial_balance(self.company, date(2027, 1, 1), date(2027, 12, 31))
        by_code = {line['code']: line['amounts'] for line in result['lines']}
        self.assertEqual(by_code['88'][0], -10_000)

    def test_complementary_closing_and_guards(self):
        self._closing('close', 2025)
        # Um lançamento feito depois do apuramento é apurado por um lançamento complementar.
        self._entry('2025-12-28', [(self.bank, 4_000), ('69.5', -4_000)])
        complement = self._closing('close', 2025)
        balances = {line.account_id.code: line.balance for line in complement.line_ids}
        self.assertEqual(balances, {'69.9': 4_000, '86.1': -4_000, '86.9': 4_000, '88.6': -4_000})
        self.assertIn('complementar', complement.ref)
        with self.assertRaisesRegex(UserError, 'nada a apurar'):
            self._closing('close', 2025)
        # A transferência leva o resultado dos apuramentos (196 000 + 4 000) e exige o exercício seguinte.
        wizard = self.env['l10n_ao_reports.closing'].create({'operation': 'transfer', 'year': 2025})
        wizard.date = date(2025, 12, 31)
        with self.assertRaisesRegex(UserError, 'exercício seguinte'):
            wizard.action_confirm()
        transfer = self._closing('transfer', 2025)
        self.assertEqual(
            {line.account_id.code: line.balance for line in transfer.line_ids}, {'88.9': 200_000, '81.1.1': -200_000}
        )
        # Data de bloqueio: o apuramento não é empurrado para o exercício seguinte.
        self._entry('2026-02-15', [(self.bank, 10_000), ('69.5', -10_000)])
        self.company.fiscalyear_lock_date = date(2026, 12, 31)
        with self.assertRaisesRegex(UserError, 'período bloqueado'):
            self._closing('close', 2026)

    def test_overdraft_and_state_grouping(self):
        # Descoberto bancário: passivo de curto prazo, não compensa as disponibilidades.
        self._entry('2025-12-31', [('72.1', 1_200_000), (self.bank, -1_200_000)])
        bs = self._bs(date(2025, 12, 31))
        self.assertEqual(bs['disponibilidades'], [0])
        self.assertEqual(bs['emprestimos_cp'], [250_000])
        self.assertEqual(bs['t_activo'], bs['t_cpp'])
        # Estado: o imposto sobre os lucros é líquido das retenções sofridas (nota 19 a).
        self._entry('2025-12-31', [('34.1.2', 30_000), ('31.1.2.1', -30_000, self.client_a)])
        bs = self._bs(date(2025, 12, 31))
        # 34.1 = 84 000 (estimativa) − 30 000 (retenções) = 54 000 a pagar; nada em contas a receber pelo 34.
        self.assertEqual(bs['contas_pagar'], [600_000 + 50_000 + 54_000])
        self.assertEqual(bs['contas_receber'], [470_000])

    def test_previous_year_date(self):
        self.assertEqual(self.engine._previous_year_date(date(2025, 2, 28)), date(2024, 2, 29))
        self.assertEqual(self.engine._previous_year_date(date(2024, 2, 29)), date(2023, 2, 28))
        self.assertEqual(self.engine._previous_year_date(date(2026, 10, 20)), date(2025, 10, 20))

    def test_closing_requires_previous_year(self):
        self._entry('2026-02-15', [(self.bank, 10_000), ('69.5', -10_000)])
        with self.assertRaisesRegex(UserError, 'exercício anterior'):
            self._closing('close', 2026)
        with self.assertRaisesRegex(UserError, 'Faça primeiro o apuramento'):
            self._closing('transfer', 2025)

    def test_unclosed_years_go_to_retained_earnings(self):
        # Sem apuramento, o resultado de 2025 aparece em 2026 como resultados transitados.
        bs = self._bs(date(2026, 6, 30))
        self.assertEqual(bs['transitados'], [196_000])
        self.assertEqual(bs['resultado'], [0])
        self.assertEqual(bs['t_activo'], bs['t_cpp'])

    def test_trial_balance(self):
        result = self.engine._trial_balance(self.company, date(2026, 1, 1), date(2026, 12, 31))
        initial, debit, credit, final_debit, final_credit = result['totals']
        self.assertAlmostEqual(initial, 0.0)
        self.assertAlmostEqual(final_debit, final_credit)
        names = [line['name'] for line in result['lines']]
        self.assertIn('Resultados de exercícios anteriores por apurar', names)
        by_code = {line['code']: line['amounts'] for line in result['lines']}
        self.assertEqual(by_code['51'][4], 1_000_000)
        self.assertEqual(by_code['3'][0], 500_000 - 50_000 - 600_000 - 84_000)
        # Classes só
        classes = self.engine._trial_balance(self.company, date(2025, 1, 1), date(2025, 12, 31), max_depth=0)
        self.assertTrue(all(len(line['code']) == 1 for line in classes['lines']))
        self.assertAlmostEqual(classes['totals'][1], classes['totals'][2])

    def test_wizard_outputs(self):
        for report in ('balance_sheet', 'income_statement', 'trial_balance'):
            wizard = self.env['l10n_ao_reports.wizard'].create(
                {'report': report, 'date_from': '2025-01-01', 'date_to': '2025-12-31', 'unit': '1000'}
            )
            html = self.env['ir.actions.report']._render_qweb_html('l10n_ao_reports.report_financial', wizard.ids)[0]
            self.assertIn(b'Valores expressos em', html)
            action = wizard.action_export_xlsx()
            attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
            self.assertEqual(attachment.raw.content[:2], b'PK')
            if report == 'balance_sheet':
                self.assertIn(b'1 930', html)
