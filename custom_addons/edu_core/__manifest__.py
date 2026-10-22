{
    'name': 'Secretaria Express - Núcleo académico',
    'version': '20.0.1.0.0',
    'summary': 'Escolas, anos lectivos, trimestres, cursos, disciplinas, planos curriculares, turmas e instalações',
    'description': """
Secretaria Express: núcleo da gestão escolar angolana.

* Escola sobre a empresa: subsistema, natureza, modo de cobrança, códigos do MED, níveis de ensino e signatários
* Anos lectivos com três trimestres e fecho do trimestre (Decreto Executivo n.º 424/25, arts. 35.º a 38.º)
* Níveis de ensino (iniciação, primário, secundário I e II ciclos, técnico-profissional, magistério)
* Cursos, coordenações e disciplinas com componentes de formação e precedências
* Moldes curriculares nacionais (catálogo do secPed-Express) e planos curriculares por escola e curso
* Turmas por ano lectivo, com sala e turno
* Instalações (campus, edifícios, salas) e turnos
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['mail', 'hr', 'l10n_ao'],
    'data': [
        'security/edu_security.xml',
        'security/ir.access.csv',
        'data/edu_level_data.xml',
        'data/edu_curriculum_template_data.xml',
        'views/edu_menus.xml',
        'views/res_company_views.xml',
        'views/edu_academic_year_views.xml',
        'views/edu_calendar_views.xml',
        'views/edu_facility_views.xml',
        'views/edu_course_views.xml',
        'views/edu_curriculum_views.xml',
        'views/edu_class_views.xml',
    ],
    'license': 'OPL-1',
    'application': True,
}
