{
    'name': 'Secretaria Express - Área do estudante e do encarregado',
    'version': '20.0.1.0.0',
    'summary': 'As áreas do estudante e do encarregado do secPed-Express: painel, notas, faltas, provas e propinas',
    'description': """
Secretaria Express: a área do estudante, como a do secPed-Express, no Odoo como o painel do professor
(perfil «Aluno»: o aluno só vê a «Área do Estudante»).

* Painel: a aula a decorrer ou a seguinte, as notas do último trimestre, a assiduidade e as próximas provas
* Minhas notas: a pauta por trimestre (NPP/MAC, NPT, CT/MT) e as classificações do ano (CF, PG, CA, CFD)
* Horário da turma, com o documento A4 da secretaria
* Provas da turma por época, com a sala e a vigilância
* Faltas pela regra que conta (Decreto Executivo 424/25 e Despacho 60/08)
* Propinas, só para ler (quem paga é o encarregado), e o aviso das propinas em atraso
* Histórico: o percurso ano a ano, com a média final e a decisão do ano
* Notificações (o que mudou nos últimos 30 dias), mensagens com os professores e a secretaria, e ajuda
* Meu perfil: matrícula, dados pessoais, encarregados e a palavra-passe
* Com propinas em atraso e a escola em modo «bloquear», as notas ficam escondidas (como no secPed)

A área do encarregado, como a do secPed (perfil «Encarregado»: só vê a «Área do Encarregado» e as mensagens):

* Painel: um cartão por educando (a média, a assiduidade e as propinas), o que pede atenção e as novidades
* Meus educandos: a turma e quem acompanha cada educando (o director de turma e os professores)
* Notas, RDEC (só com um educando na Iniciação), faltas, provas e propinas de cada educando, com as tabelas do aluno
* Calendário da escola, notificações, mensagens com os professores e a secretaria, perfil e ajuda
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_roles', 'calendar'],
    'data': [
        'security/edu_portal_security.xml',
        'security/ir.access.csv',
        'data/student_menus.xml',
        'data/student_discuss.xml',
        'data/guardian_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'edu_portal/static/src/student/*',
            'edu_portal/static/src/guardian/*',
            ('remove', 'edu_portal/static/src/student/*.dark.scss'),
        ],
        'web.assets_web_dark': [
            'edu_portal/static/src/student/*.dark.scss',
        ],
    },
    'license': 'OPL-1',
}
