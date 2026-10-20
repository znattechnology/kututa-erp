from odoo.tests import tagged

from ..tools import jws_verify
from .common import L10nAoEdiCommon


@tagged('post_install', '-at_install', 'post_install_l10n', 'l10n_ao_edi')
class TestL10nAoEdiFlow(L10nAoEdiCommon):
    def _status(self, payload_by_move):
        def handler(payload):
            return 200, {
                'requestID': payload['requestID'],
                'resultCode': '1',
                'documentStatusList': [
                    {'documentNo': name, 'documentStatus': status, 'errorList': errors}
                    for name, (status, errors) in payload_by_move.items()
                ],
            }

        return handler

    def test_send_and_validate(self):
        valid = self._create_invoice()
        invalid = self._create_invoice()
        responses = {
            'registarFactura': (200, {'requestID': '202600000000001', 'errorList': []}),
            'obterEstado': self._status(
                {
                    valid.name: ('V', []),
                    invalid.name: ('I', [{'errorCode': 'E22', 'errorDescription': 'Total de impostos não coincide'}]),
                }
            ),
        }
        with self.mock_agt(responses):
            self.send_and_poll()
        self.assertEqual(valid.l10n_ao_edi_state, 'valid')
        self.assertEqual(invalid.l10n_ao_edi_state, 'invalid')
        self.assertIn('E22', invalid.l10n_ao_edi_error)
        services = [service for service, _payload in self.agt_calls]
        self.assertEqual(services, ['registarFactura', 'obterEstado'])

        register = self.agt_calls[0][1]
        self.assertEqual(register['numberOfEntries'], 2)
        self.assertEqual(register['taxRegistrationNumber'], '5000000001')
        software = register['softwareInfo']
        public_pem = self.software_key._get_public_key_bytes(encoding='pem', formatting='raw')
        self.assertEqual(jws_verify(software['jwsSoftwareSignature'], public_pem), software['softwareInfoDetail'])

        poll = self.agt_calls[1][1]
        taxpayer_pem = self.taxpayer_key._get_public_key_bytes(encoding='pem', formatting='raw')
        self.assertEqual(
            jws_verify(poll['jwsSignature'], taxpayer_pem),
            {'taxRegistrationNumber': '5000000001', 'requestID': poll['requestID']},
        )
        document = valid.l10n_ao_edi_document_ids
        self.assertEqual(document.state, 'done')
        self.assertEqual(document.request_id, '202600000000001')

    def test_still_processing_is_polled_again(self):
        invoice = self._create_invoice()
        with self.mock_agt(
            {
                'registarFactura': (200, {'requestID': '202600000000002', 'errorList': []}),
                'obterEstado': (200, {'resultCode': '8'}),
            }
        ):
            self.send_and_poll()
        self.assertEqual(invoice.l10n_ao_edi_state, 'sent')
        document = invoice.l10n_ao_edi_document_ids
        self.assertEqual(document.state, 'sent')
        self.assertEqual(document.poll_count, 1)
        self.assertTrue(document.next_poll)

    def test_structural_error_marks_document_invalid(self):
        invoice = self._create_invoice()
        other = self._create_invoice()
        error = {'idError': 'E10', 'descriptionError': 'Contribuinte incorrecto', 'documentNo': invoice.name}
        with self.mock_agt({'registarFactura': (400, {'errorList': [error]})}):
            self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._cron_send()
        self.assertEqual(invoice.l10n_ao_edi_state, 'invalid')
        self.assertEqual(other.l10n_ao_edi_state, 'to_send', 'Os restantes documentos voltam a ser enviados')

    def test_rejected_invoice_is_corrected_with_new_number(self):
        invoice = self._create_invoice()
        rejected_name = invoice.name
        with self.mock_agt(
            {
                'registarFactura': (200, {'requestID': '202600000000003', 'errorList': []}),
                'obterEstado': self._status({rejected_name: ('I', [{'errorCode': 'E10', 'errorDescription': 'NIF'}])}),
            }
        ):
            self.send_and_poll()
        self.assertEqual(invoice.l10n_ao_edi_state, 'invalid')
        invoice.button_draft()
        invoice.action_post()
        self.assertNotEqual(invoice.name, rejected_name)
        self.assertEqual(invoice.l10n_ao_edi_rejected_document_no, rejected_name)
        document = invoice._l10n_ao_edi_document_values()
        self.assertEqual(document['documentStatus'], 'C')
        self.assertEqual(document['rejectedDocumentNo'], rejected_name)

    def test_request_series(self):
        series = self.env['l10n_ao_edi.series'].create({'document_type': 'AR', 'year': 2026})
        result = {
            'resultCode': 1,
            'seriesFEResult': {'seriesCode': 'AR26S9', 'firstDocumentNo': '1', 'lastDocumentNo': '999999'},
        }
        with self.mock_agt({'solicitarSerie': (200, result)}):
            series.action_request_series()
        self.assertEqual(series.state, 'active')
        self.assertEqual(series.code, 'AR26S9')
        payload = self.agt_calls[0][1]
        self.assertEqual(payload['documentType'], 'AR')
        self.assertEqual(payload['establishmentNumber'], 'SEDE')
        self.assertEqual(payload['seriesContingencyIndicator'], 'N')

    def test_demo_environment_simulates_agt(self):
        self.company.l10n_ao_edi_environment = 'demo'
        invoice = self._create_invoice()
        self.send_and_poll()
        self.assertEqual(invoice.l10n_ao_edi_state, 'valid')
        self.assertTrue(invoice.l10n_ao_edi_document_ids.request_id.startswith('DEMO'))
        series = self.env['l10n_ao_edi.series'].create({'document_type': 'RC', 'year': 2026})
        series.action_request_series()
        self.assertEqual(series.state, 'active')
        contingency = self.env['l10n_ao_edi.series'].create({'document_type': 'RC', 'year': 2026, 'contingency': True})
        contingency.action_request_series()
        self.assertNotEqual(contingency.code, series.code, 'Séries normal e de contingência têm códigos distintos')
