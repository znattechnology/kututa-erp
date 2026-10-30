"""Normalização das chaves de deduplicação e de exclusão (NIF, telefone, nome e cidade)."""

import re
import unicodedata

# Palavras que não distinguem uma organização de outra na mesma cidade.
PALAVRAS_VAZIAS = {
    'lda', 'limitada', 'sa', 'su', 'colegio', 'escola', 'instituto', 'complexo', 'escolar', 'restaurante', 'loja',
    'de', 'da', 'do', 'das', 'dos', 'e', 'o', 'a',
}  # fmt: skip


def sem_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto or '') if not unicodedata.combining(c))


def nif(valor):
    """Só dígitos e letras, em maiúsculas («5000-123 456» → «5000123456»)."""
    return re.sub(r'[^0-9A-Z]', '', (valor or '').upper()) or False


def telefone(valor):
    """E.164 para números angolanos (+244 e 9 dígitos); os estrangeiros ficam com + e os dígitos."""
    if not valor:
        return False
    digitos = re.sub(r'\D', '', valor)
    if valor.strip().startswith('00'):
        digitos = digitos[2:]
    if len(digitos) == 9 and digitos[0] in '29':
        return f'+244{digitos}'
    if len(digitos) == 12 and digitos.startswith('244'):
        return f'+{digitos}'
    return f'+{digitos}' if len(digitos) >= 8 else False


def nome(valor):
    palavras = re.findall(r'[a-z0-9]+', sem_acentos(valor).lower())
    return ' '.join(p for p in palavras if p not in PALAVRAS_VAZIAS)


def chave_nome_cidade(organizacao, cidade):
    n, c = nome(organizacao), nome(cidade)
    return f'{n}|{c}' if n and c else False


def chave_dedup(nif_normalizado, telefone_normalizado, organizacao, cidade):
    if nif_normalizado:
        return f'nif:{nif_normalizado}'
    if telefone_normalizado:
        return f'tel:{telefone_normalizado}'
    chave = chave_nome_cidade(organizacao, cidade)
    return f'nc:{chave}' if chave else False
