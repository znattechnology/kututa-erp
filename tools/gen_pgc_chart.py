#!/usr/bin/env python3
"""Extrai a lista de contas do PGC (Decreto n.º 82/01, §5.3) a partir do PDF oficial.

O quadro de contas está paginado a duas colunas. As palavras são lidas com as
coordenadas (``pdftotext -bbox``) e cada coluna é reconstruída separadamente.

Uso:
    python3 tools/gen_pgc_chart.py decretos/Dec-2001-82-PGC-PLANO\\ GERAL\\ CONTABILIDADE.pdf out.csv

Gera um CSV ``code,name,page`` para revisão manual. A conversão para o
template Odoo é feita por ``tools/build_l10n_ao_chart.py``.
"""

import csv
import html
import re
import subprocess
import sys
from collections import defaultdict

FIRST_PAGE, LAST_PAGE = 86, 119
# Páginas-resumo de cada classe (uma só coluna): fonte oficial dos nomes das contas de 2 dígitos.
SUMMARY_PAGES = {86, 91, 95, 101, 104, 106, 111, 117}
CODE_RE = re.compile(r'^\d{2}(?:\.\d{1,2})*\.?$')
GLUED_CODE_RE = re.compile(r'^(\d{2}(?:\.\d{1,2})+)([A-Za-zÀ-ÿ].*)$')
WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
SKIP_RE = re.compile(r'^[….·_\-–]+$')
LINE_TOLERANCE = 3.0


def read_words(pdf, page):
    out = subprocess.run(
        ['pdftotext', '-f', str(page), '-l', str(page), '-bbox', pdf, '-'],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    m = re.search(r'<page width="([\d.]+)"', out)
    width = float(m.group(1)) if m else 595.0
    words = [(float(x0), float(y0), float(x1), html.unescape(t)) for x0, y0, x1, _y1, t in WORD_RE.findall(out)]
    return width, words


def column_split(words, width):
    """Fronteira entre colunas: o maior intervalo horizontal livre no meio da página."""
    middle = [(x0, x1) for x0, _y, x1, _t in words if width * 0.3 < x0 < width * 0.75]
    occupied = sorted(middle)
    best_gap, split = 0.0, width / 2
    cursor = width * 0.3
    for x0, x1 in occupied:
        if x0 - cursor > best_gap:
            best_gap, split = x0 - cursor, (cursor + x0) / 2
        cursor = max(cursor, x1)
    return split


def group_lines(words):
    lines = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if lines and abs(lines[-1][0] - w[1]) <= LINE_TOLERANCE:
            lines[-1][1].append(w)
        else:
            lines.append([w[1], [w]])
    return [sorted(ws, key=lambda w: w[0]) for _y, ws in lines]


def tidy(name):
    name = re.sub(r'\s+', ' ', name).strip(' -–_.…')
    if name.isupper():
        name = name[0] + name[1:].lower()
    return name


def parse_column(lines, page, accounts, order):
    current = None
    for line in lines:
        tokens = [t for _x0, _y, _x1, t in line]
        text = ' '.join(tokens)
        if not text or text.startswith('PLANO GERAL DE CONTABILIDADE') or SKIP_RE.match(text.replace(' ', '')):
            current = None if SKIP_RE.match(text.replace(' ', '')) else current
            continue
        first = tokens[0]
        glued = GLUED_CODE_RE.match(first)
        if glued:
            first, rest = glued.group(1), [glued.group(2), *tokens[1:]]
        else:
            rest = tokens[1:]
        if CODE_RE.match(first):
            code = first.rstrip('.')
            name = ' '.join(t for t in rest if not SKIP_RE.match(t))
            if '.' not in code and page not in SUMMARY_PAGES:
                current = None  # título repetido na página de detalhe: o nome oficial vem do resumo
                continue
            current = code
            if code not in accounts:
                accounts[code] = {'name': name, 'page': page}
                order.append(code)
            elif name and not accounts[code]['name']:
                accounts[code]['name'] = name
            continue
        if current and re.match(r'^\d\s*–', text) is None:
            # Marcadores «75.2.39.1……» indicam subcontas a desenvolver pela empresa: não são nome.
            text = ' '.join(t for t in tokens if not re.match(r'^\d{2}(?:\.\d+)+[….]*$', t))
            if text:
                accounts[current]['name'] = f'{accounts[current]["name"]} {text}'


def main(pdf, out_csv):
    accounts, order = {}, []
    for page in range(FIRST_PAGE, LAST_PAGE + 1):
        width, words = read_words(pdf, page)
        words = [w for w in words if w[3] != str(page)]  # número de página no rodapé
        two_columns = any(CODE_RE.match(t) and x0 > width * 0.45 for x0, _y, _x1, t in words)
        split = column_split(words, width) if two_columns and page not in SUMMARY_PAGES else width
        columns = defaultdict(list)
        for w in words:
            columns[w[0] >= split].append(w)
        for key in (False, True):
            parse_column(group_lines(columns[key]), page, accounts, order)
    rows = [
        (code, tidy(accounts[code]['name']), accounts[code]['page'])
        for code in sorted(order, key=lambda c: [int(p) for p in c.split('.')])
        if tidy(accounts[code]['name'])
    ]
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['code', 'name', 'page'])
        writer.writerows(rows)
    print(f'{len(rows)} contas escritas em {out_csv}')


if __name__ == '__main__':
    main(*sys.argv[1:3])
