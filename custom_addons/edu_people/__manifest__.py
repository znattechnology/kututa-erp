{
    'name': 'Secretaria Express - Alunos, encarregados e professores',
    'version': '20.0.1.0.0',
    'summary': 'Alunos com número de matrícula, encarregados de educação, parentescos e professores',
    'description': """
Secretaria Express: as pessoas da escola.

* Aluno sobre o contacto (res.partner), com o número de matrícula vitalício (ano-sequência, único por escola)
  e os dados dos documentos oficiais: BI, filiação, naturalidade
* Encarregado de educação sobre o contacto, com NIF (adquirente das facturas, DP 71/25, art. 10.º)
* Parentesco aluno-encarregado: encarregado principal, contacto de emergência, recolha, portal e avisos
* Professor sobre o trabalhador (hr.employee): especialidade, coordenação e disciplinas que lecciona
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_core', 'contacts'],
    'data': [
        'security/ir.access.csv',
        'views/edu_student_views.xml',
        'views/edu_guardian_views.xml',
        'views/hr_employee_views.xml',
    ],
    'license': 'OPL-1',
}
