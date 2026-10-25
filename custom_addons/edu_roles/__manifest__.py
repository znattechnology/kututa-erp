{
    'name': 'Secretaria Express - Perfis e acessos',
    'version': '20.0.1.1.0',
    'summary': 'Cada perfil vê só o seu: secretaria, tesouraria, professor e direcção; aplicações escondidas',
    'description': """
Secretaria Express: perfis de acesso iguais aos do secPed-Express.

* Secretaria (ADMIN_SERVICOS): alunos, matrículas, turmas, horários, faltas, avaliação, exames e arquivo
* Tesouraria (ADMIN_FINANCAS): propinas, pagamentos, bolsas e devedores
* Professor (TEACHER): a secção «A minha docência» (as minhas turmas, aulas, avaliações, horário e vigilâncias),
  sumários, chamada, notas, pautas e conselhos das suas turmas
* Direcção (SCHOOL_ADMIN): tudo, mais a configuração
* RH e contabilidade: os perfis padrão do Odoo
* Aplicações sem relação com o perfil escondidas (Apps, Painéis, Funcionários, Contactos)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_fees', 'spreadsheet_dashboard'],
    'data': [
        'security/ir.access.csv',
        'views/edu_teaching_views.xml',
        'data/menu_groups.xml',
        'views/edu_secretaria_menu.xml',
        'views/edu_report_page_views.xml',
        'views/edu_secretaria_home_views.xml',
        'views/edu_academic_year_views.xml',
        'views/edu_shift_views.xml',
        'views/edu_coordination_views.xml',
        'views/edu_enrollment_document_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'edu_roles/static/src/teacher_home/*',
            'edu_roles/static/src/secretaria_home/*',
            'edu_roles/static/src/teacher_schedule/*',
            'edu_roles/static/src/teacher_supervisions/*',
            'edu_roles/static/src/academic_calendar/*',
            'edu_roles/static/src/attendance/*',
            'edu_roles/static/src/absence_report/*',
            'edu_roles/static/src/chat_contacts/*',
            'edu_roles/static/src/teacher_account/*',
            'edu_roles/static/src/guardians/*',
            'edu_roles/static/src/mobile_tabs/*',
            'edu_roles/static/src/charts/edu_charts.scss',
            'edu_roles/static/src/grade_grid_overview/*',
            'edu_roles/static/src/academic_year/*',
            'edu_roles/static/src/reports/reports.js',
            'edu_roles/static/src/reports/reports.xml',
            'edu_roles/static/src/reports/reports.scss',
        ],
        'web.assets_web_dark': [
            'edu_roles/static/src/reports/reports.dark.scss',
            'edu_roles/static/src/charts/edu_charts.dark.scss',
        ],
    },
    'auto_install': True,
    'license': 'OPL-1',
}
