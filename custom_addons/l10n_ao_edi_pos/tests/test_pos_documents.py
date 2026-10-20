from datetime import timedelta

from odoo import fields
from odoo.addons.l10n_ao_edi.tools import jws_verify
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TODAY, L10nAoEdiPosCommon

YY = TODAY.year % 100


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestL10nAoEdiPosDocuments(L10nAoEdiPosCommon):
    def setUp(self):
        super().setUp()
        self.open_new_session()

    # -------------------------------------------------------------------------
    # Talão de venda
    # -------------------------------------------------------------------------

    def test_sale_issues_tv(self):
        order = self.sync_order([(self.pos_product, 2)])
        self.assertRecordValues(
            order,
            [
                {
                    'state': 'paid',
                    'l10n_ao_document_type': 'TV',
                    'l10n_ao_edi_document_no': f'TV TV{YY}S1/1',
                    'l10n_ao_edi_series_id': self.series['TV'].id,
                    'l10n_ao_edi_state': 'to_send',
                    'l10n_ao_edi_contingency': False,
                    'l10n_ao_edi_receipt_number': f'TV TV{YY}S1/1',
                    'l10n_ao_edi_receipt_title': 'Talão de Venda',
                }
            ],
        )
        self.assertIn('emissor=5000000001', order.l10n_ao_edi_receipt_qr_url)
        self.assertIn(f'document=TV%20TV{YY}S1/1', order.l10n_ao_edi_receipt_qr_url)
        second = self.sync_order([(self.pos_product, 1)])
        self.assertEqual(second.l10n_ao_edi_document_no, f'TV TV{YY}S1/2')

    def test_tv_payload(self):
        order = self.sync_order([(self.pos_product, 2)])
        values = order._l10n_ao_edi_document_values()
        self.assertEqual(values['documentType'], 'TV')
        self.assertEqual(values['documentNo'], f'TV TV{YY}S1/1')
        self.assertEqual(values['customerTaxID'], '999999999')
        self.assertEqual(values['companyName'], 'Consumidor final')
        self.assertEqual(values['documentTotals'], {'taxPayable': 280.0, 'netTotal': 2000.0, 'grossTotal': 2280.0})
        [line] = values['lines']
        self.assertEqual(line['operationType'], 'TB')
        self.assertEqual(line['quantity'], 2)
        self.assertEqual(line['unitPrice'], 1000.0)
        self.assertEqual(line['creditAmount'], 2000.0)
        self.assertEqual(line['taxes'][0]['taxType'], 'IVA')
        self.assertEqual(line['taxes'][0]['taxPercentage'], 14.0)
        self.assertEqual(line['taxes'][0]['taxContribution'], 280.0)
        self.assertNotIn('referenceInfo', line)
        signed = jws_verify(
            values['jwsDocumentSignature'], self.taxpayer_key._get_public_key_bytes(encoding='pem', formatting='raw')
        )
        self.assertEqual(signed['documentType'], 'TV')
        self.assertEqual(signed['documentTotals'], values['documentTotals'])

    def test_tv_with_customer_nif(self):
        order = self.sync_order([(self.pos_product, 1)], customer=self.partner_ao)
        values = order._l10n_ao_edi_document_values()
        self.assertEqual(values['customerTaxID'], '5000000002')
        self.assertEqual(values['companyName'], 'Cliente Angola, Lda')

    def test_send_and_validate(self):
        order = self.sync_order([(self.pos_product, 1)])
        with self.mock_agt(self.agt_accept_all()):
            self.send_and_poll()
        self.assertEqual(order.l10n_ao_edi_state, 'valid')
        self.assertEqual(order.l10n_ao_edi_document_ids.pos_order_ids, order)
        sent = [p for service, p in self.agt_calls if service == 'registarFactura']
        self.assertEqual([d['documentNo'] for d in sent[0]['documents']], [order.l10n_ao_edi_document_no])

    def test_cancel_communicated_order_blocked(self):
        order = self.sync_order([(self.pos_product, 1)])
        with self.assertRaisesRegex(UserError, 'comunicados à AGT'):
            order.action_pos_order_cancel()
        with self.assertRaises(UserError):
            order.unlink()

    def test_missing_agt_tax_blocked(self):
        product = self.pos_product.copy({'taxes_id': [(5, 0, 0)]})
        with self.assertRaisesRegex(UserError, 'classificação AGT'):
            self.sync_order([(product, 1)])

    def test_negative_sale_without_refund_blocked(self):
        with self.assertRaisesRegex(UserError, 'Reembolsar'):
            self.sync_order([(self.pos_product, -1)])

    # -------------------------------------------------------------------------
    # Devoluções: nota de crédito ao talão
    # -------------------------------------------------------------------------

    def test_refund_issues_nc(self):
        order = self.sync_order([(self.pos_product, 2)])
        refund = self.sync_refund(order, reason='Artigo com defeito')
        self.assertRecordValues(
            refund,
            [
                {
                    'l10n_ao_document_type': 'NC',
                    'l10n_ao_edi_document_no': f'NC NC{YY}S1/1',
                    'l10n_ao_edi_state': 'to_send',
                    'l10n_ao_edi_receipt_title': 'Nota de Crédito',
                    'l10n_ao_edi_receipt_reference': f'TV TV{YY}S1/1 (Artigo com defeito)',
                }
            ],
        )
        values = refund._l10n_ao_edi_document_values()
        [line] = values['lines']
        self.assertEqual(line['quantity'], 2)
        self.assertEqual(line['debitAmount'], 2000.0)
        self.assertNotIn('creditAmount', line)
        self.assertEqual(line['referenceInfo'], {'reference': f'TV TV{YY}S1/1', 'reason': 'Artigo com defeito'})
        self.assertEqual(values['documentTotals']['grossTotal'], 2280.0)

    def test_refund_waits_for_origin(self):
        order = self.sync_order([(self.pos_product, 1)])
        refund = self.sync_refund(order)
        self.assertFalse(refund._l10n_ao_edi_ready_to_send())
        self.mark_sent(order)
        self.assertTrue(refund._l10n_ao_edi_ready_to_send())

    def test_refund_requires_reason(self):
        order = self.sync_order([(self.pos_product, 1)])
        with self.assertRaisesRegex(UserError, 'motivo'):
            self.sync_refund(order, reason='')

    def test_refund_of_tv_cannot_be_invoiced(self):
        order = self.sync_order([(self.pos_product, 1)])
        with self.assertRaisesRegex(UserError, 'não pode ser facturada'):
            self.sync_refund(order, customer=self.partner_ao, is_invoiced=True)

    # -------------------------------------------------------------------------
    # Vendas facturadas: Factura/Recibo
    # -------------------------------------------------------------------------

    def test_invoiced_sale_is_fr(self):
        order = self.sync_order([(self.pos_product, 1)], customer=self.partner_ao, is_invoiced=True)
        invoice = order.account_move
        self.assertFalse(order.l10n_ao_edi_document_no)
        self.assertRecordValues(
            invoice,
            [{'l10n_ao_document_type': 'FR', 'name': f'FR FR{YY}S1/1', 'l10n_ao_edi_state': 'to_send'}],
        )
        self.assertEqual(order.l10n_ao_edi_receipt_number, invoice.name)
        self.assertEqual(order.l10n_ao_edi_receipt_title, 'Factura/Recibo')

    def test_invoiced_sale_refund_is_invoice_nc(self):
        order = self.sync_order([(self.pos_product, 1)], customer=self.partner_ao, is_invoiced=True)
        self.mark_sent(order.account_move)
        refund = self.sync_refund(order, customer=self.partner_ao, is_invoiced=True)
        credit_note = refund.account_move
        self.assertRecordValues(
            credit_note,
            [
                {
                    'move_type': 'out_refund',
                    'l10n_ao_document_type': 'NC',
                    'reversed_entry_id': order.account_move.id,
                    'l10n_ao_edi_reason': 'Devolução de artigos',
                }
            ],
        )
        self.assertEqual(refund.l10n_ao_edi_receipt_reference, f'{order.account_move.name} (Devolução de artigos)')

    def test_refund_of_invoice_must_be_invoiced(self):
        order = self.sync_order([(self.pos_product, 1)], customer=self.partner_ao, is_invoiced=True)
        self.mark_sent(order.account_move)
        with self.assertRaisesRegex(UserError, 'tem de ser facturada'):
            self.sync_refund(order)

    def test_tv_cannot_be_invoiced_later(self):
        order = self.sync_order([(self.pos_product, 1)], customer=self.partner_ao)
        with self.assertRaisesRegex(UserError, 'já têm talão AGT'):
            order.action_pos_order_invoice()

    # -------------------------------------------------------------------------
    # Impressão: «Original» / «2.ª via»
    # -------------------------------------------------------------------------

    def test_print_original_then_copy(self):
        order = self.sync_order([(self.pos_product, 1)])
        data = order.order_receipt_generate_data()
        self.assertTrue(data['conditions']['l10n_ao_edi'])
        self.assertFalse(data['conditions']['l10n_ao_edi_provisional'])
        self.assertFalse(data['conditions']['use_self_invoicing'])
        self.assertTrue(data['image']['l10n_ao_edi_qr_code'])
        self.assertEqual(data['extra_data']['l10n_ao_edi_copy_label'], 'Original')
        order.l10n_ao_edi_register_print()
        self.assertEqual(order.l10n_ao_edi_print_count, 1)
        self.assertEqual(order.order_receipt_generate_data()['extra_data']['l10n_ao_edi_copy_label'], '2.ª via')
        html = order.order_receipt_generate_html()
        self.assertIn(f'Talão de Venda TV TV{YY}S1/1', ' '.join(str(html).split()))
        self.assertIn('2.ª via', str(html))
        self.assertIn('Processado por programa validado n.º C_134/AGT', ' '.join(str(html).split()))

    # -------------------------------------------------------------------------
    # Contingência, bloqueio aos 60 dias e abertura de sessão
    # -------------------------------------------------------------------------

    def test_contingency(self):
        self.company.l10n_ao_edi_contingency = True
        order = self.sync_order([(self.pos_product, 1)])
        self.assertEqual(order.l10n_ao_edi_document_no, f'TV TV{YY}C1/1')
        self.assertTrue(order.l10n_ao_edi_receipt_contingency)
        with self.mock_agt(self.agt_accept_all()):
            self.send_and_poll()
            self.assertEqual(order.l10n_ao_edi_state, 'to_send')
            self.company.l10n_ao_edi_contingency = False
            self.send_and_poll()
        self.assertEqual(order.l10n_ao_edi_state, 'valid')
        self.assertTrue(order.l10n_ao_edi_receipt_contingency)
        self.assertFalse(order.l10n_ao_edi_receipt_pending)

    def test_communication_lock_counts_pos_orders(self):
        order = self.sync_order([(self.pos_product, 1)])
        order.l10n_ao_edi_system_entry_date = fields.Datetime.now() - timedelta(days=61)
        with self.assertRaisesRegex(UserError, 'Emissão bloqueada'):
            self.sync_order([(self.pos_product, 1)])

    def test_session_requires_series(self):
        self.pos_session.close_session_from_ui()
        self.series['TV'].action_close()
        with self.assertRaisesRegex(UserError, 'Faltam séries AGT'):
            self.config.open_ui()
