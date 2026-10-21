{
    'name': 'Secretaria Express - Matrículas',
    'version': '20.0.1.0.0',
    'summary': 'Candidaturas, matrículas com número de ordem, disciplinas, anulações, transferências e rematrícula',
    'description': """
Secretaria Express: o percurso administrativo do aluno.

* Candidaturas: rascunho, submetida, em análise, aprovada (cria o aluno, o encarregado e a matrícula), rejeitada
* Matrícula do aluno numa turma e ano lectivo: vagas, uma matrícula por aluno e ano, número de matrícula
  vitalício na primeira, número de ordem fixo no ano (o seguinte para quem entra a meio)
* Disciplinas da matrícula a partir do plano curricular da turma
* Anulação com motivo, reactivação com verificação de vagas
* Transferências: mudança de turma, de curso, interna e saída para outra escola
* Rematrícula de uma turma para o ano lectivo seguinte
* Pontos de extensão para a avaliação (retenções, disciplinas em atraso) e para as propinas (devedores)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_people'],
    'data': [
        'security/ir.access.csv',
        'wizard/edu_enrollment_drop_views.xml',
        'wizard/edu_enrollment_renewal_views.xml',
        'views/edu_enrollment_views.xml',
        'views/edu_application_views.xml',
        'views/edu_transfer_views.xml',
        'views/edu_class_views.xml',
        'views/edu_student_views.xml',
    ],
    'license': 'OPL-1',
}
