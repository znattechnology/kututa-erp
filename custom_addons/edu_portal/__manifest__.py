{
    'name': 'Secretaria Express - Área do estudante',
    'version': '20.0.1.0.0',
    'summary': 'A área do estudante do secPed-Express: painel, notas, horário, provas, faltas, propinas e perfil',
    'description': """
Secretaria Express: a área do estudante, como a do secPed-Express, no Odoo como o painel do professor
(perfil «Aluno»: o aluno só vê a «Área do Estudante»).

* Painel: a aula a decorrer ou a seguinte, as notas do último trimestre, a assiduidade e as próximas provas
* Minhas notas: a pauta por trimestre (NPP/MAC, NPT, CT/MT) e as classificações do ano (CF, PG, CA, CFD)
* Horário da turma, com o documento A4 da secretaria
* Provas da turma por época, com a sala e a vigilância
* Faltas pela regra que conta (Decreto Executivo 424/25 e Despacho 60/08)
* Propinas, só para ler (quem paga é o encarregado), e o aviso das propinas em atraso
* Meu perfil: matrícula, dados pessoais, encarregados e a palavra-passe
* Com propinas em atraso e a escola em modo «bloquear», as notas ficam escondidas (como no secPed)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_roles'],
    'data': [
        'security/edu_portal_security.xml',
        'security/ir.access.csv',
        'data/student_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'edu_portal/static/src/student/*',
            ('remove', 'edu_portal/static/src/student/*.dark.scss'),
        ],
        'web.assets_web_dark': [
            'edu_portal/static/src/student/*.dark.scss',
        ],
    },
    'license': 'OPL-1',
}
