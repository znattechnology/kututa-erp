{
    'name': 'Secretaria Express - Avaliação',
    'version': '20.0.1.3.0',
    'summary': 'Notas, mini-pautas e pautas, motores do ensino geral (Dec. 424/25) e técnico (Despacho 60/08), '
    'conselho de turma, exames especiais, reapreciação e decisão de transição',
    'description': """
Secretaria Express: avaliação das aprendizagens.

* Regime de avaliação por escola e nível, com os valores do RAA (Decreto Executivo n.º 424/25) e do
  Despacho n.º 60/08 (técnico-profissional): escala, aprovação, arredondamento às unidades, pesos
* Avaliações (contínuas, prova trimestral, prova global, exame nacional) e notas por aluno
* Ensino geral: MT = (MAC + NPT)/2; MT3 das classes de exame = (MT1 + MT2 + MAC3)/3; MFD = média das MT;
  MFED = 0,6 MT3 + 0,4 EN (6.ª e 9.ª) ou 0,5/0,5 (12.ª)
* Técnico: CT = (NPP + NPT)/2; CF cumulativa (CT2 = (CT1 + MT2)/2, CF = (CT2 + MT3)/2); CA = 60% CF + 40% PG nas
  disciplinas com prova global; CFD das plurianuais
* Janela de lançamento: trimestre fechado só por reapreciação; o professor lança no trimestre em curso ou com
  autorização da secretaria (até 30 dias)
* Conselho de turma: bonificação de +1/+2 dos casos limite pelo professor ou por votação nominal (+2), sem
  abstenção e com quórum de 50% no técnico
* Decisão de fim de ano: transita, conclui, transita com disciplinas em atraso (exame extraordinário), admitido a
  exame de recurso, retido; retenção por faltas; frequência mínima no primário; decisão manual da direcção
* Exames especiais: recurso, extraordinário e melhoria (prevalece a nota mais alta)
* RDEC da iniciação (avaliação qualitativa)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_attendance'],
    'data': [
        'security/ir.access.csv',
        'views/edu_evaluation_policy_views.xml',
        'views/edu_assessment_views.xml',
        'views/edu_result_views.xml',
        'views/edu_curriculum_views.xml',
        'views/edu_year_result_views.xml',
        'views/edu_council_views.xml',
        'views/edu_grade_appeal_views.xml',
        'views/edu_rdec_views.xml',
        'views/edu_class_views.xml',
        'views/menus.xml',
        'wizard/edu_enrollment_confirmation_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'edu_evaluation/static/src/council_board/*',
            'edu_evaluation/static/src/grade_grid/*',
            'edu_evaluation/static/src/grade_permissions/*',
            'edu_evaluation/static/src/rdec/*',
        ],
    },
    'license': 'OPL-1',
}
