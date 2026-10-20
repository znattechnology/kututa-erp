from odoo.tests import TransactionCase, tagged

from ..tools import canonical_json, jws_sign, jws_verify


@tagged('post_install', '-at_install', 'l10n_ao_edi')
class TestJws(TransactionCase):
    def test_sign_and_verify_rs256(self):
        key = self.env['certificate.key']._generate_rsa_private_key(self.env.company, key_size=2048)
        payload = {'productId': 'Kututa ERP', 'productVersion': '1.0.0', 'softwareValidationNumber': 'C_134'}
        token = jws_sign(payload, key)
        header, body, signature = token.split('.')
        self.assertNotIn('=', token, 'Base64URL sem padding')
        self.assertTrue(signature)
        public_pem = key._get_public_key_bytes(encoding='pem', formatting='raw')
        self.assertEqual(jws_verify(token, public_pem), payload)
        with self.assertRaises(ValueError):
            jws_verify(f'{header}.{body}.{signature[:-4]}AAAA', public_pem)

    def test_canonical_json_keeps_order_and_accents(self):
        self.assertEqual(canonical_json({'b': 1, 'a': 'Ç ã'}), '{"b":1,"a":"Ç ã"}')
