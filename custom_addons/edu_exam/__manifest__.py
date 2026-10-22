{
    'name': 'Secretaria Express - Exames',
    'version': '20.0.1.0.0',
    'summary': 'Épocas e sessões de exame, salas, vigilantes, distribuição dos alunos, presenças e notas',
    'description': """
Secretaria Express: organização dos exames.

* Épocas de exame: provas trimestrais, provas globais, exame nacional, recurso, extraordinário, melhoria de nota e
  época especial de conclusão de curso
* Sessões por disciplina, com uma ou mais turmas, data e hora, salas com lotação e vigilantes
* Conflitos: a mesma sala, o mesmo vigilante ou o mesmo aluno em duas sessões à mesma hora
* Convocatória: os alunos com exame especial por fazer na disciplina entram na sessão; nas provas, os alunos
  matriculados na disciplina das turmas escolhidas
* Distribuição pelas salas por ordem alfabética e lotação, com número de lugar
* Presenças e notas na sessão: nos exames especiais actualizam a pauta e a decisão; nas provas vão para a avaliação
  ligada (falta injustificada vale 0)
* Calendário de provas, como no secPed-Express: épocas criadas a partir do calendário escolar; a mesma prova marcada
  em várias turmas de uma vez (cada uma na sua sala); vista por sessão com o vigilante de cada turma e
  «Distribuir vigilantes»; calendário de cada turma e escala de vigilância de cada professor, para imprimir
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_evaluation'],
    'data': [
        'security/ir.access.csv',
        'views/edu_exam_views.xml',
        'views/edu_exam_requirement_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'edu_exam/static/src/exam_planner/*',
        ],
    },
    'license': 'OPL-1',
}
