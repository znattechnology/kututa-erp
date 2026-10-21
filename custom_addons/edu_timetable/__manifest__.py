{
    'name': 'Secretaria Express - Horários',
    'version': '20.0.1.0.0',
    'summary': 'Tempos lectivos, colocação de professores, director de turma, horários, faltas de aula e substituições',
    'description': """
Secretaria Express: organização pedagógica da escola.

* Tempos lectivos por turno (grelha), com intervalos
* Colocação dos professores por turma e disciplina, para o ano ou para um trimestre
* Director de turma: um por turma, e no máximo uma turma por professor em cada ano lectivo
* Horário semanal da turma com verificação de conflitos de turma, professor e sala
* Confronto dos tempos do horário com a carga semanal do plano curricular
* Aulas que não se realizam (feriados, greves) e substituições de professor numa data
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_people'],
    'data': [
        'security/ir.access.csv',
        'views/edu_time_slot_views.xml',
        'views/edu_teaching_assignment_views.xml',
        'views/edu_schedule_views.xml',
        'views/edu_class_views.xml',
    ],
    'license': 'OPL-1',
}
