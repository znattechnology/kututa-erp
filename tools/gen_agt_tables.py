#!/usr/bin/env python3
"""Gera os dados mestre da AGT para o módulo ``l10n_ao``.

Fonte: ``docs/referencias/agt-facturacao-electronica/anexos.txt`` (anexos da documentação
oficial da API de Facturação Electrónica, equivalentes às Tabelas 1–6 do Decreto Executivo n.º 683/25).

Ficheiros gerados em ``custom_addons/l10n_ao/data/``:
* ``l10n_ao.tax.exemption.csv``: motivos de isenção IVA (M..), IS (S..) e IEC (I..);
* ``l10n_ao.cae.csv``: Códigos de Actividade Económica;
* ``l10n_ao.stamp.duty.item.csv``: verbas e taxas do Imposto de Selo;
* ``l10n_ao.iec.rate.csv``: taxas do Imposto Especial de Consumo por classificação pautal.
"""

import csv
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'docs' / 'referencias' / 'agt-facturacao-electronica' / 'anexos.txt'
TARGET = ROOT / 'custom_addons' / 'l10n_ao' / 'data'

SECTIONS = {
    'cae': ('Códigos de Actividade Económica - CAE', ['Código', 'Descrição']),
    'iec': (
        'Tabela de Taxas do Imposto Especial de Consumo',
        ['Classificação Pautal', 'Designação', 'Unidade de Medida', 'IEC (%)'],
    ),
    'is': (
        'Tabela de Verbas e Taxas de Imposto de Selo',
        ['Nº Verba', 'Actos/ Documentos/ Contratos/ Operações/ Títulos', 'Taxa'],
    ),
    'ex_iva': ('Tabela de Isenções de IVA', ['Código', 'Menção a constar no documento', 'Descrição']),
    'ex_is': ('Tabela de Isenções de IS', ['Código', 'Menção a constar no documento', 'Descrição']),
    'ex_iec': ('Tabela de Isenções de IEC', ['Código', 'Menção a constar no documento', 'Descrição']),
}


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def section_cells(text, title, header):
    """Células de uma tabela: o texto entre o cabeçalho e o título seguinte, separado por '|'."""
    start = text.index(title)
    following = [text.index(t, start + 1) for t, _h in SECTIONS.values() if t in text[start + 1 :]]
    end = min(following) if following else len(text)
    cells = [clean(c) for c in text[start + len(title) : end].split('|')]
    # Retira as células do cabeçalho e o texto introdutório que as precede.
    idx = next(i for i, c in enumerate(cells) if c.endswith(header[0]))
    cells = cells[idx + len(header) :]
    return cells


def chunk(cells, size, code_re):
    rows, i = [], 0
    while i + size <= len(cells):
        if code_re.match(cells[i]):
            rows.append(cells[i : i + size])
            i += size
        else:
            i += 1
    return rows


def parse_rate(value):
    """'0,3%' -> ('percent', 0.3); '100,00 Kz' -> ('fixed', 100.0); '' -> ('none', 0)."""
    value = value.replace(' ', '')
    if not value:
        return 'none', 0.0
    number = re.search(r'[\d.,]+', value)
    if not number:
        return 'none', 0.0
    amount = float(number.group().replace('.', '').replace(',', '.'))
    return ('percent' if '%' in value else 'fixed'), amount


def write_csv(name, header, rows):
    path = TARGET / name
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)
    print(f'{len(rows):4d} registos -> {path.relative_to(ROOT)}')


def main():
    text = SOURCE.read_text(encoding='utf-8')
    TARGET.mkdir(parents=True, exist_ok=True)

    # Isenções (IVA, IS, IEC)
    exemptions = []
    for key, tax_type in (('ex_iva', 'IVA'), ('ex_is', 'IS'), ('ex_iec', 'IEC')):
        title, header = SECTIONS[key]
        for code, mention, description in chunk(section_cells(text, title, header), 3, re.compile(r'^[MSI]\d{2}$')):
            exemptions.append([f'exemption_{code.lower()}', code, tax_type, mention, description])
    write_csv('l10n_ao.tax.exemption.csv', ['id', 'code', 'tax_type', 'name', 'description'], exemptions)

    # CAE
    title, header = SECTIONS['cae']
    cae = [[f'cae_{c}', c, n] for c, n in chunk(section_cells(text, title, header), 2, re.compile(r'^\d{5}$'))]
    write_csv('l10n_ao.cae.csv', ['id', 'code', 'name'], cae)

    # Imposto de Selo
    title, header = SECTIONS['is']
    stamp = []
    for code, name, rate in chunk(section_cells(text, title, header), 3, re.compile(r'^\d{1,2}(\.\d{1,2})*$')):
        rate_type, amount = parse_rate(rate)
        stamp.append([f'stamp_duty_{code.replace(".", "_")}', code, name, rate_type, amount])
    write_csv('l10n_ao.stamp.duty.item.csv', ['id', 'code', 'name', 'rate_type', 'rate'], stamp)

    # IEC
    title, header = SECTIONS['iec']
    iec = []
    for code, name, uom, rate in chunk(section_cells(text, title, header), 4, re.compile(r'^\d{4}\.\d{2}\.\d{2}$')):
        iec.append([f'iec_{code.replace(".", "_")}', code, name, uom, parse_rate(rate + '%')[1]])
    write_csv('l10n_ao.iec.rate.csv', ['id', 'code', 'name', 'uom', 'rate'], iec)


if __name__ == '__main__':
    main()
