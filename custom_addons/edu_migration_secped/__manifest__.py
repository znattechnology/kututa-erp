{
    'name': 'Secretaria Express - Migração do secPed-Express',
    'version': '20.0.1.0.0',
    'summary': 'Importa uma escola do secPed-Express: estrutura, alunos, matrículas, horário, notas e decisões',
    'description': """
Migração idempotente de uma escola do secPed-Express (PostgreSQL) para a Secretaria Express.

* Lê a base do secPed só para leitura e carrega por fases; correr duas vezes não duplica nada
* Escola, anos lectivos, trimestres, turnos, tempos, salas e coordenações
* Disciplinas, cursos e planos curriculares tal como estão no secPed
* Turmas (uma por oferta anual), alunos com os números de matrícula, professores e matrículas
* Contas do pessoal e dos alunos do ano em curso (Área do Estudante), sem palavra-passe
* Atribuições, horário afixado, épocas de provas, planos de propinas e multas
* Notas dos anos fechados: médias dos trimestres, CF assinada, prova global, exame nacional, MF assinada e
  bonificações do conselho (ensino técnico e ensino geral)
* Decisões de transição da pauta assinada e reconciliação nota a nota com o cálculo do secPed
* Ignora as contas de teste do secPed (endereços .test) e não envia nada a terceiros
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_roles', 'edu_portal'],
    'external_dependencies': {'python': ['psycopg2']},
    'license': 'OPL-1',
}
