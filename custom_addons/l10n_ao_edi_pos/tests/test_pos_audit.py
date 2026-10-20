import json

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import TODAY, L10nAoEdiPosCommon

YY = TODAY.year % 100


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestL10nAoEdiPosAudit(L10nAoEdiPosCommon):
    """Casos encontrados na auditoria da fase 2."""

    def setUp(self):
        super().setUp()
        self.open_new_session()

    def test_cashier_without_accounting_rights_can_sell(self):
        cashier = self.env['res.users'].create(
            {
                'name': 'Caixa',
                'login': 'caixa_ao',
                'company_id': self.company.id,
                'company_ids': [Command.set(self.company.ids)],
                'group_ids': [Command.set(self.env.ref('point_of_sale.group_pos_user').ids)],
            }
        )
        data = self.create_ui_order_data([(self.pos_product, 1)])
        self.env['pos.order'].with_user(cashier).sync_from_ui([data])
        order = self.env['pos.order'].search([('uuid', '=', data['uuid'])])
        self.assertEqual(order.l10n_ao_edi_document_no, f'TV TV{YY}S1/1')
        self.assertTrue(order.l10n_ao_edi_payload)

    def test_session_closing_is_not_an_agt_document(self):
        order = self.sync_order([(self.pos_product, 2)])
        self.sync_refund(order)
        self.pos_session.close_session_from_ui()
        session_moves = self.env['account.move'].search(
            [('pos_session_sales_id', '=', self.pos_session.id)]
        ) | self.env['account.move'].search([('pos_session_refunds_id', '=', self.pos_session.id)])
        self.assertTrue(session_moves)
        self.assertFalse(session_moves.filtered('l10n_ao_edi_series_id'))
        self.assertFalse(session_moves.filtered('l10n_ao_edi_state'))
        self.assertEqual(self.series['FT'].next_number, 1, 'O fecho de sessão não pode consumir números AGT')

    def test_refund_after_session_closed(self):
        order = self.sync_order([(self.pos_product, 1)])
        self.pos_session.close_session_from_ui()
        self.open_new_session()
        refund = self.sync_refund(order)
        self.assertEqual(refund.l10n_ao_document_type, 'NC')
        self.assertEqual(refund._l10n_ao_edi_origin_number(), order.l10n_ao_edi_document_no)

    def test_negative_price_line_blocked(self):
        discount = self.env['product.product'].create(
            {
                'name': 'Desconto',
                'lst_price': -200.0,
                'available_in_pos': True,
                'taxes_id': [Command.set(self.vat14.ids)],
            }
        )
        with self.assertRaisesRegex(UserError, 'preço negativo'):
            self.sync_order([(self.pos_product, 2), (discount, 1)])

    def test_tip_after_payment_not_allowed(self):
        with self.assertRaises(ValidationError):
            self.config.set_tip_after_payment = True

    def test_issued_order_lines_are_locked(self):
        order = self.sync_order([(self.pos_product, 1)])
        with self.assertRaisesRegex(UserError, 'já foi emitido'):
            order.lines[0].qty = 5
        with self.assertRaisesRegex(UserError, 'já foi emitido'):
            self.env['pos.order.line'].create(
                {
                    'order_id': order.id,
                    'product_id': self.pos_product.id,
                    'qty': 1,
                    'price_unit': 100,
                    'price_subtotal': 100,
                    'price_subtotal_incl': 114,
                }
            )

    def test_resync_does_not_change_issued_order(self):
        data = self.create_ui_order_data([(self.pos_product, 1)])
        self.env['pos.order'].sync_from_ui([data])
        order = self.env['pos.order'].search([('uuid', '=', data['uuid'])])
        payload = order.l10n_ao_edi_payload
        again = self.create_ui_order_data([(self.pos_product, 3)], uuid=data['uuid'])
        self.env['pos.order'].sync_from_ui([again])
        self.assertEqual(order.lines.mapped('qty'), [1])
        self.assertEqual(order.l10n_ao_edi_payload, payload)

    def test_payload_frozen_at_issue(self):
        order = self.sync_order([(self.pos_product, 1)], customer=self.partner_ao)
        self.partner_ao.name = 'Outro nome'
        self.assertEqual(json.loads(order.l10n_ao_edi_payload)['companyName'], 'Cliente Angola, Lda')
        self.assertEqual(order._l10n_ao_edi_payload_values()['companyName'], 'Cliente Angola, Lda')

    def test_rejected_tv_is_corrected(self):
        order = self.sync_order([(self.pos_product, 1)])
        order.l10n_ao_edi_state = 'invalid'
        with self.assertRaisesRegex(UserError, 'rejeitado'):
            self.sync_refund(order)
        order.action_l10n_ao_edi_correct()
        self.assertEqual(order.l10n_ao_edi_document_no, f'TV TV{YY}S1/2')
        self.assertEqual(order.l10n_ao_edi_rejected_document_no, f'TV TV{YY}S1/1')
        values = order._l10n_ao_edi_payload_values()
        self.assertEqual(values['documentStatus'], 'C')
        self.assertEqual(values['rejectedDocumentNo'], f'TV TV{YY}S1/1')

    def test_refund_above_sold_quantity_blocked(self):
        order = self.sync_order([(self.pos_product, 1)])
        self.sync_refund(order)
        with self.assertRaisesRegex(UserError, 'acima do vendido'):
            self.sync_refund(order)

    def test_mixed_pay_later_blocked(self):
        cash = self.config.payment_method_ids.filtered(lambda m: m.type == 'cash')[:1]
        with self.assertRaisesRegex(UserError, 'Conta do Cliente'):
            self.sync_order(
                [(self.pos_product, 1)],
                customer=self.partner_ao,
                payments=[(self.pay_later_pm, 500.0), (cash, 640.0)],
            )

    def test_basic_receipt_is_not_fiscal(self):
        order = self.sync_order([(self.pos_product, 1)])
        data = order.order_receipt_generate_data(basic_receipt=True)
        self.assertFalse(data['conditions']['l10n_ao_edi'])
        self.assertFalse(data['image']['l10n_ao_edi_qr_code'])

    def test_payload_totals_match_order_with_discount(self):
        order = self.sync_order([{'product': self.pos_product, 'quantity': 3, 'discount': 7.5}])
        totals = order._l10n_ao_edi_payload_values()['documentTotals']
        self.assertAlmostEqual(totals['grossTotal'], order.amount_total, places=2)
        self.assertAlmostEqual(totals['taxPayable'], order.amount_tax, places=2)

    def test_receipt_shows_exemption_reason(self):
        book = self.pos_product.copy({'name': 'Livro', 'taxes_id': [Command.set(self.exempt_m21.ids)]})
        order = self.sync_order([(book, 1)])
        notes = order.order_receipt_generate_data()['extra_data']['l10n_ao_edi_legal_notes']
        self.assertTrue(notes and 'artigo 12' in notes[0], notes)
