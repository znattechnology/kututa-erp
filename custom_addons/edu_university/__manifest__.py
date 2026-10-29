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
* Avaliação: provas de frequência e trabalhos na grelha de notas; média de frequência, dispensa, admissão e
  exclusão (também pela assiduidade); exame normal, recurso, especial e melhoria; a situação na UC fecha com o
  semestre
* Exames: épocas normal, de recurso, especial e de melhoria; convocados tirados da situação de cada inscrição
  (admitidos, por aprovar, finalistas, aprovados); a pauta da sessão dá a nota na UC
* Resultado do ano pelas UCs: passa com até N UCs em atraso, senão fica no mesmo ano; conclui no último ano com
  todas aprovadas
* Trabalho final (TFC ou dissertação) sobre a PAP: orientador, co-orientador, júri, defesa; a nota é a da UC
* Conclusão do curso com a média pesada pelos créditos; certificado de habilitações e diploma
* Encarregado de educação opcional: o estudante é o adquirente das suas facturas
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_documents'],
    'data': [
        'security/ir.access.csv',
        'data/edu_level_data.xml',
        'views/res_company_views.xml',
        'views/edu_academic_year_views.xml',
        'views/edu_curriculum_views.xml',
        'views/edu_student_views.xml',
        'views/edu_uc_registration_views.xml',
        'views/edu_exam_views.xml',
        'views/edu_records_views.xml',
        'report/edu_certificate_higher.xml',
    ],
    'license': 'OPL-1',
}
