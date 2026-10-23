{
    'name': 'Secretaria Express - Arquivo académico',
    'version': '20.0.1.0.0',
    'summary': 'Estágio curricular, PAP, conclusão de curso com diploma e livro de termos, histórico escolar',
    'description': """
Secretaria Express: o arquivo do percurso do aluno.

* Estágio curricular (ensino técnico): entidade, supervisor, tutor, horas, relatórios entregues e classificação;
  páginas «Estágios» e «Trabalho de fim de curso» como no secPed (novo por turma da classe final)
* Prova de Aptidão Profissional (PAP): tema, orientador, júri, defesa e classificação
* Conclusão de curso ou de nível: classificação final do plano curricular (média das CFD), estágio e PAP, com a
  fórmula da escola ((2 × PC + PAP)/3 ou (4 × PC + EC + PAP)/6); número de diploma sequencial, livro e folha de
  termos; só para quem concluiu
* Número de processo individual do aluno e histórico escolar por ano lectivo e disciplina
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_evaluation'],
    'data': [
        'security/ir.access.csv',
        'views/edu_records_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'edu_records/static/src/training/*',
        ],
    },
    'license': 'OPL-1',
}
