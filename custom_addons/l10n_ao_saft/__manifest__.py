{
    'name': 'Kututa Mbongo - SAF-T (AO)',
    'version': '20.0.1.0.0',
    'summary': 'Ficheiro SAF-T (AO) de contabilidade e de facturação (DE n.º 317/20, DP n.º 71/25)',
    'description': """
Exportação do ficheiro normalizado SAF-T (AO), versão 1.01_01.

* Contabilidade (C): plano de contas com saldos, clientes, fornecedores, impostos e lançamentos
* Contabilidade integrada com facturação (I): também facturas, talões, recibos e facturas de fornecedor
* Facturação (F): facturas, talões e recibos, a partir dos documentos AGT emitidos
* Validação pelo esquema XSD da AGT antes da entrega
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Accounting/Localizations/Reporting',
    'depends': ['l10n_ao_edi', 'l10n_ao_reports'],
    'auto_install': True,
    'data': [
        'security/ir.access.csv',
        'views/l10n_ao_saft_views.xml',
    ],
    'license': 'OPL-1',
}
