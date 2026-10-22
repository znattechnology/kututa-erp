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
    ],
    'assets': {
        'web.assets_backend': [
            'edu_roles/static/src/teacher_home/*',
        ],
    },
    'auto_install': True,
    'license': 'OPL-1',
}
