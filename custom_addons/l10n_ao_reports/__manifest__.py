{
    'name': 'Kututa Mbongo - Demonstrações Financeiras PGC',
    'version': '20.0.1.1.0',
    'summary': 'Balanço, Demonstração de Resultados, Balancete e encerramento do exercício (Decreto n.º 82/01)',
    'description': """
Kututa Mbongo: demonstrações financeiras do Plano Geral de Contabilidade angolano.

* Balanço (modelo 4.2.3) com comparativo N-1 e referência às notas
* Demonstração de Resultados por natureza (modelo 4.3.3)
* Balancete geral por classe, conta e subconta
* Valores em Kwanzas ou em milhares de Kwanzas; PDF, pré-visualização e Excel
* Apuramento de resultados pela classe 8 (subcontas x.9 → 82 a 86 → 88)
  e transferência do resultado líquido para resultados transitados (88 → 81)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Accounting/Localizations/Reporting',
    'depends': ['l10n_ao'],
    'auto_install': True,
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.access.csv',
        'report/report_financial.xml',
        'views/l10n_ao_reports_views.xml',
    ],
    'license': 'OPL-1',
}
