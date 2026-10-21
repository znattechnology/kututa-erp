{
    'name': 'Kututa Kazi - Salários Angola',
    'version': '20.0.1.0.0',
    'summary': 'Processamento salarial: IRT (Lei n.º 14/25), INSS (DP n.º 227/18), subsídios, horas extra e recibos',
    'description': """
Kututa Kazi: processamento de salários segundo a lei angolana, em Community.

* Folha mensal por empresa, com um recibo por trabalhador (LGT, art. 247.º)
* IRT do grupo A pela tabela em vigor (Lei n.º 14/25), com os rendimentos isentos (alimentação e transporte)
* INSS: 3% do trabalhador e 8% da entidade empregadora (DP n.º 227/18)
* Salário-hora (art. 237.º), faltas (art. 240.º), horas extra (art. 188.º), nocturno, descanso e feriados
* Subsídios de férias e de Natal (art. 238.º), proporcionais
* Adiantamentos com os limites do art. 248.º (3 salários e 25% do líquido)
* Sanções disciplinares com redução do salário (art. 87.º)
* Lançamento contabilístico no PGC (72, 36, 34), ficheiro bancário, mapas do IRT e do INSS
* Contas finais na cessação (arts. 307.º a 311.º)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Human Resources/Payroll',
    'depends': ['l10n_ao_hr', 'l10n_ao', 'account'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.access.csv',
        'data/l10n_ao_payroll.irt.bracket.csv',
        'report/report_payslip.xml',
        'views/l10n_ao_payroll_run_views.xml',
        'views/l10n_ao_payroll_advance_views.xml',
        'views/hr_version_views.xml',
        'views/res_company_views.xml',
        'wizard/l10n_ao_payroll_termination_views.xml',
    ],
    'license': 'OPL-1',
}
