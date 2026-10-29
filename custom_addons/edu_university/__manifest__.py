{
    'name': 'Secretaria Express - Ensino superior',
    'version': '20.0.1.0.0',
    'summary': 'Universidades e institutos: licenciatura e mestrado, semestres, unidades curriculares e créditos',
    'description': """
Secretaria Express: o ensino superior sobre a mesma base académica.

* Subsistema «Ensino superior» na instituição e níveis Licenciatura e Mestrado
* Ano académico com dois semestres (calendário académico geral do subsistema de ensino superior)
* Unidades curriculares semestrais ou anuais, com créditos, horas de contacto e tipo (obrigatória, optativa,
  transversal), e o trabalho final (TFC ou dissertação), como nas Normas Curriculares Gerais (DP 193/18)
* Inscrição por unidade curricular: na matrícula, as UCs obrigatórias do ano e as UCs em atraso (numa turma do
  ano a que pertencem); precedências, créditos por semestre e prescrição pelo regulamento académico
* Regulamento académico por instituição e nível, com valores de origem típicos
* Encarregado de educação opcional: o estudante é o adquirente das suas facturas
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_enrollment'],
    'data': [
        'security/ir.access.csv',
        'data/edu_level_data.xml',
        'views/res_company_views.xml',
        'views/edu_academic_year_views.xml',
        'views/edu_curriculum_views.xml',
        'views/edu_student_views.xml',
        'views/edu_uc_registration_views.xml',
    ],
    'license': 'OPL-1',
}
