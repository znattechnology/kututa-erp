# ruff: noqa: F821  (o env vem do shell do Odoo)
"""Carrega a tabela de preços do Kututa ERP (``docs/comercial/tabela-precos.csv``) na base da Vímeo.

Corre no shell do Odoo, com o CSV em ``/tmp/tabela-precos.csv`` (ou no caminho de ``TABELA_CSV``):
    odoo-bin shell -d kututa --no-http < tools/carregar_tabela_precos.py

Idempotente: cada produto é procurado pela referência interna (``default_code``) e actualizado.
Os preços são em Kz, sem IVA; o IVA de 14% vai no imposto do produto.
A lista de preços por omissão passa a Kz (vinha em USD da instalação do website_sale) se ainda não houver vendas.
"""

import csv
import os

CSV = os.environ.get('TABELA_CSV', '/tmp/tabela-precos.csv')
company = env.company
aoa = env.ref('base.AOA')
dominio_iva = [
    ('type_tax_use', '=', 'sale'),
    ('amount', '=', 14),
    ('price_include', '=', False),
    ('company_id', '=', company.id),
]
iva = env['account.tax'].search(dominio_iva, limit=1)
assert iva, 'Falta o IVA 14% de venda'

root = env['product.category'].search([('name', '=', 'Kututa ERP'), ('parent_id', '=', False)], limit=1)
root = root or env['product.category'].create({'name': 'Kututa ERP'})
uoms = {
    'Unidades': env.ref('uom.product_uom_unit'),
    'Horas': env.ref('uom.product_uom_hour'),
    'Dias': env.ref('uom.product_uom_day'),
}

criados = actualizados = 0
with open(CSV, encoding='utf-8') as f:
    for row in csv.DictReader(f):
        categ = env['product.category'].search([('name', '=', row['grupo']), ('parent_id', '=', root.id)], limit=1)
        categ = categ or env['product.category'].create({'name': row['grupo'], 'parent_id': root.id})
        uom = uoms[row['unidade']]
        vals = {
            'name': row['nome'],
            'default_code': row['referencia'],
            'type': 'service',
            'list_price': float(row['preco']),
            'categ_id': categ.id,
            'uom_id': uom.id,
            'sale_ok': True,
            'purchase_ok': False,
            'invoice_policy': 'order',
            'taxes_id': [(6, 0, iva.ids)],
            'description_sale': row['descricao'] or False,
        }
        product = (
            env['product.template']
            .with_context(active_test=False)
            .search([('default_code', '=', row['referencia'])], limit=1)
        )
        if product:
            product.write(vals)
            actualizados += 1
        else:
            env['product.template'].create(vals)
            criados += 1

pricelist = env['product.pricelist'].search([('company_id', 'in', [company.id, False])], order='sequence, id', limit=1)
if (
    pricelist
    and pricelist.currency_id != aoa
    and not env['sale.order'].search_count([('pricelist_id', '=', pricelist.id)])
):
    pricelist.write({'currency_id': aoa.id, 'name': 'Tabela Kututa ERP (Kz)'})

env.cr.commit()
print('ok', criados, 'criados,', actualizados, 'actualizados; lista', pricelist.name, pricelist.currency_id.name)
