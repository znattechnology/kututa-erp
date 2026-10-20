#!/usr/bin/env python3
"""Gera ``custom_addons/l10n_ao/data/template/account.account-ao.csv``.

Fontes (revistas manualmente, em ``tools/data/``):
* ``pgc_decreto_82_01.csv``: lista de contas do Decreto n.º 82/01 (§5.3), extraída por ``gen_pgc_chart.py``;
* ``pgc_correcoes.csv``: correcções aos lapsos de impressão do decreto (códigos repetidos, gralhas);
* ``pgc_extensoes.csv``: contas que o PGC de 2001 não prevê (IVA, contas técnicas do Odoo).

Regras:
* uma conta com subcontas é agregadora: fica inactiva (no Odoo 20 os grupos são contas-pai inactivas);
* as subcontas «a desenvolver» do decreto («Banco ___», «Caixa ___», «Entidade»…) não são criadas:
  as contas bancárias e de caixa são criadas pelo Odoo nos diários (43.1.x, 45.1.x);
* o tipo de conta (``account_type``) decorre da classe/conta do PGC (ver ``account_type_for``).
"""

import csv
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / 'data' / 'pgc_decreto_82_01.csv'
EXTENSIONS = ROOT / 'data' / 'pgc_extensoes.csv'
CORRECTIONS = ROOT / 'data' / 'pgc_correcoes.csv'
TARGET = ROOT.parent / 'custom_addons' / 'l10n_ao' / 'data' / 'template' / 'account.account-ao.csv'

# Subcontas-modelo do decreto, a desenvolver por cada empresa.
PLACEHOLDER_NAMES = {'Banco', 'Caixa', 'Entidade', 'Ano'}
# Contas que têm de ser agregadoras mesmo sem subcontas no template (o Odoo cria as filhas).
FORCED_PARENTS = {'43.1', '43.2', '45.1'}  # 43.1/45.1: diários em Kz; 43.2: bancos em moeda estrangeira

# (prefixo, tipo, reconciliável) — o prefixo mais longo prevalece.
TYPE_RULES = [
    ('1', 'asset_non_current', False),
    ('11', 'asset_fixed', False),
    ('14', 'asset_fixed', False),
    ('18', 'asset_fixed', False),
    ('2', 'asset_current', False),
    ('3', 'liability_current', False),
    ('31', 'asset_receivable', True),
    ('31.3', 'asset_current', False),
    ('31.9', 'liability_current', False),
    ('32', 'liability_payable', True),
    ('32.9', 'asset_current', False),
    ('33', 'liability_non_current', False),
    ('35.2', 'asset_current', False),
    ('36.3', 'asset_current', False),
    ('37.2', 'asset_current', False),
    ('37.3', 'asset_current', False),
    ('37.4', 'asset_prepayments', False),
    ('38', 'asset_current', False),
    ('39', 'liability_non_current', False),
    ('4', 'asset_current', False),
    # asset_cash só nas contas de diário (43 depósitos à ordem, 45.1 fundo fixo); o resto é activo corrente.
    ('43', 'asset_cash', False),
    ('45.1', 'asset_cash', False),
    ('45.2', 'asset_current', True),
    ('5', 'equity', False),
    ('6', 'income', False),
    ('66', 'income_other', False),
    ('67', 'income_other', False),
    ('68', 'income_other', False),
    ('69', 'income_other', False),
    ('7', 'expense', False),
    ('71', 'expense_direct_cost', False),
    ('73', 'expense_depreciation', False),
    ('76', 'expense_other', False),
    ('77', 'expense_other', False),
    ('78', 'expense_other', False),
    ('79', 'expense_other', False),
    ('8', 'equity', False),
]


def key(code):
    return [int(p) for p in code.split('.')]


def xmlid(code):
    return 'ao_' + code.replace('.', '_')


def parent_code(code):
    return '.'.join(code.split('.')[:-1]) or None


def account_type_for(code):
    best = ('', 'asset_current', False)
    for prefix, account_type, reconcile in TYPE_RULES:
        matches = (
            code == prefix
            or code.startswith(prefix + '.')
            or ('.' not in prefix and len(prefix) == 1 and code[0] == prefix)
        )
        if matches and len(prefix) >= len(best[0]):
            best = (prefix, account_type, reconcile)
    return best[1], best[2]


def main():
    with SOURCE.open(encoding='utf-8') as f:
        accounts = {row['code']: {'name': row['name']} for row in csv.DictReader(f)}
    with CORRECTIONS.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            code = row['code']
            if row['op'] == 'delete':
                for existing in [c for c in accounts if c == code or c.startswith(code + '.')]:
                    del accounts[existing]
            elif row['op'] == 'rename':
                accounts[code]['name'] = row['name']
            elif row['op'] == 'add':
                assert code not in accounts, f'{code} já existe'
                accounts[code] = {'name': row['name']}
            else:
                raise SystemExit(f'Operação desconhecida: {row["op"]}')
    accounts = {
        code: data for code, data in accounts.items() if code.count('.') < 2 or data['name'] not in PLACEHOLDER_NAMES
    }
    with EXTENSIONS.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            accounts[row['code']] = {
                'name': row['name'],
                'account_type': row['account_type'],
                'reconcile': row['reconcile'] == 'True',
            }

    missing_parents = sorted({p for c in accounts if (p := parent_code(c)) and p not in accounts}, key=key)
    if missing_parents:
        raise SystemExit(f'Contas sem conta-pai: {missing_parents}')

    has_children = {parent_code(c) for c in accounts} | FORCED_PARENTS
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['id', 'parent_id', 'active', 'name', 'code', 'account_type', 'reconcile', 'non_trade'])
        for code in sorted(accounts, key=key):
            data = accounts[code]
            account_type, reconcile = account_type_for(code)
            account_type = data.get('account_type') or account_type
            reconcile = data.get('reconcile', reconcile)
            parent = parent_code(code)
            is_group = code in has_children
            writer.writerow(
                [
                    xmlid(code),
                    xmlid(parent) if parent else '',
                    'False' if is_group else '',
                    data['name'],
                    code,
                    account_type,
                    'True' if reconcile and not is_group else '',
                    '',
                ]
            )
    groups = sum(1 for c in accounts if c in has_children)
    print(f'{len(accounts)} contas ({groups} agregadoras, {len(accounts) - groups} de movimento) -> {TARGET}')


if __name__ == '__main__':
    main()
