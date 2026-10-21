{
    'name': 'Kututa Kazi - Recursos Humanos Angola',
    'version': '20.0.1.0.0',
    'summary': 'Lei Geral do Trabalho (Lei n.º 12/23): contratos, ausências, feriados, horas extra e sanções',
    'description': """
Kututa Kazi: recursos humanos segundo a Lei Geral do Trabalho angolana.

* Contratos: tipos e causas do contrato a termo (art. 15.º), durações máximas (art. 16.º),
  período experimental (art. 18.º)
* Tipos de ausência da LGT com os limites por evento, mês e ano (arts. 222.º a 229.º)
  e faltas injustificadas (art. 230.º)
* Feriados nacionais (Lei n.º 10/11, com a Lei n.º 11/18) com as pontes, gerados por ano
* Horário de 44 horas (art. 148.º)
* Registo de trabalho extraordinário com os limites do art. 185.º e arredondamento do art. 188.º
* Sanções disciplinares com redução de salário (art. 87.º)
* Número de segurado do INSS e antiguidade (art. 311.º)
* Motivos de cessação da LGT
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Human Resources/Localizations',
    'depends': ['hr', 'hr_holidays', 'hr_work_entry'],
    'data': [
        'security/ir.access.csv',
        'data/hr_work_entry_type_data.xml',
        'data/hr_departure_reason_data.xml',
        'data/resource_calendar_data.xml',
        'data/ir_cron.xml',
        'views/hr_employee_views.xml',
        'views/hr_version_views.xml',
        'views/hr_work_entry_type_views.xml',
        'views/l10n_ao_hr_overtime_views.xml',
        'views/l10n_ao_hr_sanction_views.xml',
        'views/res_company_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'license': 'OPL-1',
}
