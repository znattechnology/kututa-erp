{
    'name': 'Kututa Mbongo - Inventário AGT',
    'version': '20.0.1.0.0',
    'summary': 'SAF-T de inventário anual (DP n.º 71/25, art. 24.º; Circular n.º 05/GACA/GJ/DSF/AGT/2026)',
    'description': """
Ficheiro de inventário das existências a 31 de Dezembro, a submeter até 15 de Fevereiro.

* Cabeçalho (StockHeader) e tabela de inventário (Stock) da Circular n.º 05/2026
* Excel, XML ou JSON; ficheiro «sem operações» quando não há existências
* Quantidade e valor pela valorização do Odoo à data (FIFO ou custo médio)
* Tipo de produto pela conta de existências do PGC (22 a 26)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Accounting/Localizations',
    'depends': ['stock_account', 'l10n_ao_edi', 'l10n_ao_reports'],
    'auto_install': True,
    'data': [
        'security/ir.access.csv',
        'views/l10n_ao_stock_views.xml',
    ],
    'license': 'OPL-1',
}
