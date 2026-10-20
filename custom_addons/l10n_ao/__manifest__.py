{
    'name': 'Angola - Contabilidade',
    'version': '20.0.0.1.0',
    'summary': 'Localização angolana: PGC (Decreto n.º 82/01), impostos e dados mestre AGT',
    'description': """
Localização angolana para o Odoo 20.

* Plano Geral de Contabilidade (Decreto n.º 82/01, de 16 de Novembro)
* Impostos (IVA, Imposto de Selo, IEC) com os códigos da AGT (Decreto Executivo n.º 683/25)
* Motivos de isenção, CAE e validação do NIF
    """,
    'countries': ['ao'],
    'category': 'Accounting/Localizations/Account Charts',
    'depends': [
        'account',
    ],
    'auto_install': ['account'],
    'license': 'LGPL-3',
}
