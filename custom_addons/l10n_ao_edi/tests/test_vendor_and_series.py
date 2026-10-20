from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..tools import jws_verify
from .common import TODAY, L10nAoEdiCommon


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao_edi')
class TestL10nAoEdiVendorAndSeries(L10nAoEdiCommon):
    def _bill(self, tax_xmlid='ao_iva_purchase_14'):
        bill = self.env['account.move'].create(
            {
                'move_type': 'in_invoice',
                'partner_id': self.partner_ao.id,
                'invoice_date': TODAY,
                'ref': 'FT FT26X9/45',
                'invoice_line_ids': [
                    Command.create(
                        {
                            'name': 'Compra',
                            'quantity': 1,
                            'price_unit': 500.0,
                            'tax_ids': [Command.set(self._ao_tax(tax_xmlid).ids)],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def test_confirm_vendor_bill(self):
        bill = self._bill()
        result = {'confirmRejectResult': {'actionResultCode': 'C_OK', 'documentStatusCode': 'S_RG', 'errorList': []}}
        with self.mock_agt({'validarDocumento': (200, result)}):
            bill.action_l10n_ao_edi_vendor_confirm()
        self.assertEqual(bill.l10n_ao_edi_vendor_state, 'confirmed')
        payload = self.agt_calls[0][1]
        self.assertEqual(payload['documentNo'], 'FT FT26X9/45')
        self.assertEqual(payload['action'], 'C')
        self.assertEqual(payload['deductAllVAT'], 'AD')
        public_pem = self.taxpayer_key._get_public_key_bytes(encoding='pem', formatting='raw')
        self.assertEqual(
            jws_verify(payload['jwsSignature'], public_pem),
            {'taxRegistrationNumber': '5000000001', 'documentNo': 'FT FT26X9/45'},
        )

    def test_non_deductible_bill_and_rejection(self):
        bill = self._bill('ao_iva_purchase_14_nd')
        self.assertEqual(bill._l10n_ao_edi_vendor_deduct_all(), 'ND')
        refused = {
            'confirmRejectResult': {
                'actionResultCode': 'R_NOK',
                'errorList': [{'errorCode': 'E44', 'errorDescription': 'Estado'}],
            }
        }
        with self.mock_agt({'validarDocumento': (200, refused)}), self.assertRaisesRegex(UserError, 'E44'):
            bill.action_l10n_ao_edi_vendor_reject()
        self.assertFalse(bill.l10n_ao_edi_vendor_state)

    def test_sync_series_from_agt(self):
        body = {
            'seriesResultCount': 2,
            'seriesInfo': [
                {'seriesCode': 'GF26S7', 'seriesYear': 2026, 'documentType': 'GF', 'establishmentNumber': 'SEDE'},
                {
                    'seriesCode': self.series['FT'].code,
                    'seriesYear': 2026,
                    'documentType': 'FT',
                    'establishmentNumber': 'SEDE',
                },
            ],
        }
        with self.mock_agt({'listarSeries': (200, body)}):
            self.env['l10n_ao_edi.series'].action_l10n_ao_edi_sync_series()
        new = self.env['l10n_ao_edi.series'].search([('code', '=', 'GF26S7')])
        self.assertEqual(new.state, 'active')
        self.assertEqual(new.document_type, 'GF')
        self.assertEqual(self.env['l10n_ao_edi.series'].search_count([('code', '=', self.series['FT'].code)]), 1)
