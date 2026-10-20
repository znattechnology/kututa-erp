"""JSON Web Signature (JWS) compacto, algoritmo RS256, como exigido pela API de Facturação Electrónica da AGT.

A AGT assina «o objecto JSON completo» em forma canónica (sem espaços nem quebras de linha), com uma
chave RSA de pelo menos 2048 bits, e codifica em Base64URL sem padding:

    base64url(header) . base64url(payload) . base64url(RSA-SHA256(header.payload))

A assinatura RSA usa o modelo ``certificate.key`` do Odoo (PKCS#1 v1.5 + SHA-256 = RS256).
"""

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

JWS_HEADER = {'typ': 'JOSE', 'alg': 'RS256'}


def canonical_json(value):
    """JSON compacto, sem espaços, mantendo a ordem dos campos e os caracteres portugueses."""
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False)


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def jws_sign(payload, key):
    """Assina ``payload`` (dict) com ``key`` (registo ``certificate.key`` privado) e devolve o JWS compacto."""
    signing_input = f'{_b64url(canonical_json(JWS_HEADER).encode())}.{_b64url(canonical_json(payload).encode())}'
    signature = key._sign(signing_input.encode('ascii'), hashing_algorithm='sha256', formatting='raw')
    return f'{signing_input}.{_b64url(signature)}'


def jws_verify(token, public_key_pem):
    """Verifica um JWS RS256 com uma chave pública PEM. Devolve o payload (dict) ou levanta ``ValueError``."""
    header_b64, payload_b64, signature_b64 = token.split('.')
    public_key = serialization.load_pem_public_key(public_key_pem)
    try:
        public_key.verify(
            _b64url_decode(signature_b64),
            f'{header_b64}.{payload_b64}'.encode('ascii'),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as error:
        raise ValueError('Assinatura JWS inválida') from error
    return json.loads(_b64url_decode(payload_b64))
