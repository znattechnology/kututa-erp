{
    'name': 'Secretaria Express - Análise de dados',
    'version': '20.0.1.0.0',
    'summary': 'Os números da escola ao longo dos anos lectivos: matrículas, resultados, percurso e aproveitamento',
    'description': """
Secretaria Express: análise de dados para a direcção e a secretaria.

* Resumo: matrículas e resultado de cada ano lado a lado, com o que mudou face ao ano anterior
* Percurso dos alunos: os que entraram num ano e onde estão em cada ano seguinte
* Aproveitamento: a média de cada trimestre, as médias finais por faixas, as disciplinas com mais negativas, os
  cursos e as turmas
* Filtros por anos, curso, classe e turno; cada número abre a lista dos alunos
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_roles'],
    'data': [
        'views/edu_analytics_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'edu_analytics/static/src/dashboard/analytics.js',
            'edu_analytics/static/src/dashboard/analytics.xml',
            'edu_analytics/static/src/dashboard/analytics.scss',
        ],
        'web.assets_web_dark': [
            'edu_analytics/static/src/dashboard/analytics.dark.scss',
        ],
    },
    'auto_install': True,
    'license': 'OPL-1',
}
