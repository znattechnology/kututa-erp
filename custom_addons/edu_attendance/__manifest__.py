{
    'name': 'Secretaria Express - Sumários e presenças',
    'version': '20.0.1.0.0',
    'summary': 'Aulas com sumário e número de lição, chamada, faltas justificadas e injustificadas, limites de faltas',
    'description': """
Secretaria Express: o dia-a-dia das aulas.

* Aulas (lições) geradas a partir do horário ou abertas pelo professor, com sumário, número de lição e
  trimestre deduzido da data; o professor efectivo é o substituto quando há substituição
* Chamada por aula: presente, atraso (conta como presença), falta injustificada, falta justificada
* Justificação de faltas com motivo, data e quem justificou, só pela secretaria e pelo director de turma,
  falta a falta ou por período (atestado de vários dias)
* Aulas geradas sem feriados nem pausas do calendário escolar; a aula dada exige sumário e data passada;
  com o trimestre fechado, as aulas e as faltas não se alteram
* Limites de faltas injustificadas: ensino secundário geral 3/4/5 por trimestre e disciplina (Dec. Exec.
  424/25, art. 25.º); técnico-profissional o triplo dos tempos semanais no ano, com exclusão de todas as
  disciplinas (Despacho 60/08, art. 7.º); no primário só a frequência de 2/3 (art. 21.º); tempos
  semanais do plano curricular
* Mapa de faltas por aluno, disciplina e trimestre, com alunos em risco e reprovados por faltas, e aviso
  ao director de turma
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_timetable', 'edu_enrollment'],
    'data': [
        'security/edu_attendance_security.xml',
        'security/ir.access.csv',
        'data/mail_activity_type_data.xml',
        'wizard/edu_lesson_generate_views.xml',
        'wizard/edu_absence_justify_views.xml',
        'views/edu_lesson_views.xml',
        'views/edu_absence_summary_views.xml',
        'views/edu_class_views.xml',
    ],
    'license': 'OPL-1',
}
