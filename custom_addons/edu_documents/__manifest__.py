{
    'name': 'Secretaria Express - Documentos oficiais',
    'version': '20.0.1.0.0',
    'summary': 'Declarações, guia de transferência, termo de frequência, certificado, diploma, mini-pautas, pautas, '
    'relação nominal, horário e cartão de estudante',
    'description': """
Secretaria Express: os documentos da secretaria, com o texto e a forma dos modelos em uso nas escolas e dos anexos
do Despacho n.º 60/08.

* Registo dos documentos emitidos, com número por tipo e ano lectivo (DSN/Nº01/2026-2027), finalidade e impressões
* Declaração de frequência, declaração com notas, declaração para transferência (cabeçalho de Estado e escola de
  tutela), guia de transferência
* Termo de frequência e aproveitamento (todas as classes do curso), certificado de habilitações (técnico por
  componente, Anexo IV; ensino geral por classe), diploma (Anexo III)
* Mini-pauta e pauta da turma (mapa de aproveitamento final, A3), relação nominal, horário, cartão de estudante
* Notas por extenso (catorze, dezasseis, dezassete, dezanove), classes por extenso, positivas a azul e negativas a
  vermelho (RAA, art. 35.º)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_records', 'edu_exam', 'kututa_web'],
    'data': [
        'security/ir.access.csv',
        'report/edu_layout.xml',
        'report/edu_declarations.xml',
        'report/edu_certificates.xml',
        'report/edu_pautas.xml',
        'report/edu_teachers.xml',
        'report/edu_council.xml',
        'report/edu_listings.xml',
        'report/edu_report_actions.xml',
        'wizard/edu_pauta_print_views.xml',
        'views/edu_document_views.xml',
    ],
    'license': 'OPL-1',
}
