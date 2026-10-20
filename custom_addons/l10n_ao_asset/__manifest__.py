{
    'name': 'Kututa Mbongo - Imobilizado',
    'version': '20.0.1.0.0',
    'summary': 'Imobilizado e amortizações com as taxas legais angolanas (DP n.º 207/15)',
    'description': """
Gestão do imobilizado corpóreo e incorpóreo segundo o PGC e o Código do Imposto Industrial.

* Tabela oficial das taxas de reintegração e amortização (Decreto Presidencial n.º 207/15)
* Quotas constantes, em duodécimos ou por ano completo (CII, art. 29.º)
* Bens de reduzido valor (até Kz 30 000) amortizados no exercício (art. 36.º)
* Limite fiscal das viaturas ligeiras (Kz 20 000 000, art. 40.º)
* Fichas criadas a partir das facturas de fornecedor; lançamento automático das quotas (73 / 18)
* Alienação e abate (art. 29.º, n.º 4)
* Mapa de reintegrações e amortizações (art. 43.º) em PDF e Excel
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Accounting/Localizations',
    'depends': ['l10n_ao_reports'],
    'auto_install': True,
    'data': [
        'security/ir.access.csv',
        'data/l10n_ao_asset.rate.csv',
        'data/ir_cron.xml',
        'report/report_asset_map.xml',
        'views/l10n_ao_asset_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'license': 'OPL-1',
}
