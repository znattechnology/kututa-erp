"""Gera custom_addons/l10n_ao_asset/data/l10n_ao_asset.rate.csv a partir de docs/referencias/amortizacoes/taxas.csv.

Tabela anexa ao Decreto Presidencial n.º 207/15 (477 linhas conferidas com o PDF oficial), mais as taxas
do Código do Imposto Industrial para o imobilizado incorpóreo (art. 39.º, n.os 3 e 4).
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'docs/referencias/amortizacoes/taxas.csv'
TARGET = ROOT / 'custom_addons/l10n_ao_asset/data/l10n_ao_asset.rate.csv'

EXTRA = [
    (
        'CII.39.3',
        'N - Activo incorpóreo',
        'Incorpóreo com período de utilidade não determinável (CII, art. 39.º, n.º 3)',
        '20',
        '5',
    ),
    ('CII.39.4', 'N - Activo incorpóreo', 'Programas informáticos (CII, art. 39.º, n.º 4)', '33.33', '3'),
]


def xmlid(code):
    return 'rate_' + re.sub(r'[^0-9a-z]+', '_', code.lower()).strip('_')


def main():
    rows = []
    for row in csv.DictReader(SOURCE.open(encoding='utf-8')):
        rows.append((row['code'], row['group'], row['name'], row['rate'], row['life_years']))
    rows.extend(EXTRA)
    with TARGET.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['id', 'code', 'group', 'name', 'rate', 'life_years'])
        for code, group, name, rate, life in rows:
            writer.writerow([xmlid(code), code, group, name, rate, life or 0])
    print(f'{len(rows)} taxas escritas em {TARGET.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
