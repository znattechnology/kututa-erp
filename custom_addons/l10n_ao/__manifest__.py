{
    'name': 'Kututa Kwanza - Contabilidade Angola',
    'version': '20.0.1.0.0',
    'summary': 'Plano Geral de Contabilidade (Decreto n.º 82/01), IVA e dados mestre da AGT',
    'description': """
Kututa Kwanza: localização angolana do Kututa ERP.

* Plano Geral de Contabilidade (Decreto n.º 82/01, de 16 de Novembro), com as extensões para o IVA
* Impostos com os códigos da AGT (taxType / taxCode / motivo de isenção - DE n.º 683/25)
* Tabelas oficiais da AGT: isenções (IVA, IS, IEC), CAE, Imposto de Selo, IEC
* Declaração periódica de IVA
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Accounting/Localizations/Account Charts',
    'depends': [
        'account',
    ],
    'auto_install': ['account'],
    'data': [
        'security/ir.access.csv',
        'data/res_currency_data.xml',
        'data/res_country_data.xml',
        'data/l10n_ao.tax.exemption.csv',
        'data/l10n_ao.cae.csv',
        'data/l10n_ao.stamp.duty.item.csv',
        'data/l10n_ao.iec.rate.csv',
        'data/tax_report.xml',
        'views/l10n_ao_master_data_views.xml',
        'views/account_tax_views.xml',
        'views/res_company_views.xml',
    ],
    'license': 'OPL-1',
}
