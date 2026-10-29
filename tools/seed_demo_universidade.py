# ruff: noqa
"""Base de demonstração do ensino superior (Instituto Superior Kianda, fictício).

Corre-se no shell do Odoo, numa base com o país Angola posto antes de instalar o l10n_ao e o edu_university:
    .venv/bin/python odoo/odoo-bin shell -c config/odoo.conf -d kututa_universidade --no-http < tools/seed_demo_universidade.py
Os acessos gerados ficam em EDU_DEMO_ACCESS_FILE (por omissão ACESSOS-UNIVERSIDADE.txt, ignorado pelo git), chmod 600.
"""

import os
import secrets
from datetime import date

OUT = os.environ.get('EDU_DEMO_ACCESS_FILE', 'ACESSOS-UNIVERSIDADE.txt')  # fora do repositório
ao = env.ref('base.ao')
company = env.ref('base.main_company')
company.write({'name': 'Instituto Superior Kianda', 'city': 'Luanda', 'street': 'Talatona, Luanda Sul'})
assert company.account_fiscal_country_id.code == 'AO' and company.currency_id.name == 'AOA', 'Plano AO em falta'
company.write(
    {
        'edu_is_school': True,
        'edu_school_type': 'higher',
        'edu_ownership': 'private',
        'edu_billing_mode': 'monthly',
        'edu_director_name': 'Afonso Kiala',
        'edu_director_title': 'Reitor',
        'edu_pedagogical_director_name': 'Marta Neto',
        'edu_pedagogical_director_gender': 'f',
        'edu_mescti_code': 'IES-0000 (demonstração)',
        'edu_motto': 'Saber para transformar',
        'edu_pedagogical_title': 'Vice-Reitora para os Assuntos Académicos',
    }
)
LIC = env.ref('edu_university.level_licenciatura')
MES = env.ref('edu_university.level_mestrado')
company.edu_level_ids = [(6, 0, (LIC | MES).ids)]

Year = env['edu.academic.year']
y1 = Year.create({'name': '2025/2026', 'date_start': date(2025, 10, 1), 'date_end': date(2026, 9, 30)})
y2 = Year.create(
    {'name': '2026/2027', 'date_start': date(2026, 10, 1), 'date_end': date(2027, 9, 30), 'is_current': True}
)
for year in (y1, y2):
    year.action_generate_trimesters()
y2.trimester_ids.sorted('number')[0].is_current = True

Subject = env['edu.subject']


def subjects(rows):
    return {code: Subject.create({'name': name, 'code': code}) for code, name in rows}


S = subjects(
    [
        ('AM1', 'Análise Matemática I'),
        ('ALG', 'Álgebra Linear'),
        ('PRG1', 'Programação I'),
        ('ISI', 'Introdução aos Sistemas de Informação'),
        ('AM2', 'Análise Matemática II'),
        ('PRG2', 'Programação II'),
        ('MD', 'Matemática Discreta'),
        ('LPT', 'Língua Portuguesa e Técnicas de Expressão'),
        ('ED', 'Estruturas de Dados'),
        ('BD', 'Bases de Dados'),
        ('ARQ', 'Arquitectura de Computadores'),
        ('EST', 'Probabilidades e Estatística'),
        ('SO', 'Sistemas Operativos'),
        ('RC', 'Redes de Computadores'),
        ('ES', 'Engenharia de Software'),
        ('ETI', 'Ética e Deontologia Profissional'),
        ('IA', 'Inteligência Artificial'),
        ('SD', 'Sistemas Distribuídos'),
        ('SEG', 'Segurança Informática'),
        ('GP', 'Gestão de Projectos'),
        ('CMP', 'Compiladores'),
        ('CG', 'Computação Gráfica'),
        ('EMP', 'Empreendedorismo'),
        ('TFC', 'Trabalho de Fim de Curso'),
        ('MIC', 'Metodologia da Investigação Científica'),
        ('GSI', 'Gestão Estratégica de Sistemas de Informação'),
        ('GOV', 'Governação de TI'),
        ('ANL', 'Análise de Dados para a Gestão'),
        ('DIS', 'Dissertação'),
    ]
)
S['PRG2'].prerequisite_ids = S['PRG1']
S['AM2'].prerequisite_ids = S['AM1']
S['ED'].prerequisite_ids = S['PRG2']
S['IA'].prerequisite_ids = S['EST']


def course(name, code, level, years, duration):
    c = env['edu.course'].create({'name': name, 'code': code, 'level_id': level.id, 'duration_years': duration})
    cur = env['edu.curriculum'].create({'name': f'{code} 2025', 'course_id': c.id, 'level_id': level.id})
    plans = {}
    for number, lines in years.items():
        plans[number] = env['edu.curriculum.year'].create(
            {
                'curriculum_id': cur.id,
                'year': number,
                'name': f'{number}.º ano',
                'line_ids': [
                    (
                        0,
                        0,
                        dict(
                            subject_id=S[code_].id,
                            semester=sem,
                            credits=cr,
                            contact_hours=int(cr * 10),
                            sequence=i,
                            **extra,
                        ),
                    )
                    for i, (code_, sem, cr, extra) in enumerate(lines)
                ],
            }
        )
    return c, plans


EI, EIP = course(
    'Engenharia Informática',
    'EI',
    LIC,
    {
        1: [
            ('AM1', '1', 6, {}),
            ('ALG', '1', 6, {}),
            ('PRG1', '1', 7.5, {}),
            ('ISI', '1', 4.5, {}),
            ('LPT', '1', 3, {'uc_type': 'transversal'}),
            ('AM2', '2', 6, {}),
            ('PRG2', '2', 7.5, {}),
            ('MD', '2', 6, {}),
        ],
        2: [
            ('ED', '1', 7.5, {}),
            ('BD', '1', 7.5, {}),
            ('ARQ', '1', 6, {}),
            ('EST', '2', 6, {}),
            ('SO', '2', 7.5, {}),
            ('ETI', '2', 3, {'uc_type': 'transversal'}),
        ],
        3: [
            ('RC', '1', 7.5, {}),
            ('ES', '1', 7.5, {}),
            ('IA', '2', 7.5, {}),
            ('SD', '2', 7.5, {}),
            ('CG', '2', 4.5, {'uc_type': 'optional'}),
        ],
        4: [
            ('SEG', '1', 6, {}),
            ('GP', '1', 6, {}),
            ('CMP', '1', 6, {'uc_type': 'optional'}),
            ('EMP', '2', 3, {'uc_type': 'transversal'}),
            ('TFC', 'annual', 15, {'is_final_work': True}),
        ],
    },
    4,
)
MG, MGP = course(
    'Gestão de Sistemas de Informação',
    'MGSI',
    MES,
    {
        1: [('MIC', '1', 6, {}), ('GSI', '1', 7.5, {}), ('GOV', '2', 7.5, {}), ('ANL', '2', 7.5, {})],
        2: [('DIS', 'annual', 30, {'is_final_work': True})],
    },
    2,
)

Class = env['edu.class']


def klass(year, course_, plan, name, capacity=40):
    return Class.create(
        {
            'name': name,
            'course_id': course_.id,
            'academic_year_id': year.id,
            'curriculum_year_id': plan.id,
            'capacity': capacity,
        }
    )


old = {n: klass(y1, EI, EIP[n], 'A') for n in (1, 2, 3)}
cur = {n: klass(y2, EI, EIP[n], 'A') for n in (1, 2, 3, 4)}
mg1 = klass(y2, MG, MGP[1], 'A', 25)

Employee = env['hr.employee']
teachers = Employee.create(
    [
        {'name': n, 'edu_is_teacher': True, 'company_id': company.id}
        for n in (
            'Domingos Sebastião',
            'Graça Mateus',
            'Hélder Cassoma',
            'Isabel Tchipa',
            'Joaquim Manuel',
            'Luísa Pedro',
        )
    ]
)
Assign = env['edu.teaching.assignment']
for i, (edu_class) in enumerate([*old.values(), *cur.values(), mg1]):
    for j, line in enumerate(edu_class.subject_line_ids):
        Assign.create(
            {
                'class_id': edu_class.id,
                'subject_id': line.subject_id.id,
                'teacher_id': teachers[(i + j) % len(teachers)].id,
            }
        )

Student = env['edu.student']
first_names = [
    'Adelino',
    'Benvinda',
    'Carlos',
    'Delfina',
    'Edson',
    'Feliciana',
    'Gaspar',
    'Henriqueta',
    'Ivo',
    'Josefa',
    'Kalunga',
    'Laurinda',
    'Mateus',
    'Nzinga',
    'Osvaldo',
    'Paulina',
    'Quintino',
    'Rosária',
    'Sílvio',
    'Teresa',
    'Ulisses',
    'Vitória',
    'Wilson',
    'Xénia',
    'Yuri',
    'Zulmira',
]
last_names = [
    'Kiala',
    'Manuel',
    'Domingos',
    'Sebastião',
    'Neto',
    'Cassoma',
    'Tchipa',
    'Lumbo',
    'Kassoma',
    'Mbala',
    'Paulo',
    'Fortunato',
]
_counter = [0]


def new_student():
    i = _counter[0]
    _counter[0] += 1
    return Student.create(
        {
            'name': f'{first_names[i % 26]} {last_names[(i * 5) % 12]} {last_names[(i * 7 + 3) % 12]}',
            'birth_date': date(2000 + i % 6, 1 + i % 12, 1 + i % 27),
            'gender': 'male' if i % 2 == 0 else 'female',
            'email': f'estudante{i + 1}@kianda.example',
        }
    )


def enroll(student, edu_class, day=None):
    e = env['edu.enrollment'].create(
        {'student_id': student.id, 'class_id': edu_class.id, 'date': day or edu_class.academic_year_id.date_start}
    )
    e.with_context(edu_fees_skip_generation=True).action_confirm()
    return e


import random

rnd = random.Random(2026)


def history_grades(edu_class, fails):
    """Notas reais na grelha: uma frequência e um trabalho por UC; quem tem a UC em «fails» fica excluído."""
    for line in edu_class.subject_line_ids:
        semester = edu_class.academic_year_id.trimester_ids.filtered(
            lambda t: t.number == (2 if line.semester in ('2', 'annual') else 1)
        )
        for name, kind, weight in (('1.ª Frequência', 'frequency', 1.0), ('Trabalho prático', 'coursework', 0.5)):
            a = env['edu.assessment'].create(
                {
                    'name': name,
                    'class_id': edu_class.id,
                    'subject_id': line.subject_id.id,
                    'trimester_id': semester.id,
                    'assessment_type': kind,
                    'weight': weight,
                }
            )
            a.action_fill_students()
            for g in a.grade_ids:
                if line.subject_id.code in fails.get(g.enrollment_id.id, ()):
                    g.score = rnd.choice([3, 4, 5])
                else:
                    g.score = rnd.choice([9, 10, 11, 12, 13, 14, 15, 16, 17])


# 2025/2026: três turmas com histórico (para o 2.º, o 3.º e o 4.º ano de agora).
history = {1: [], 2: [], 3: []}
for n in (1, 2, 3):
    for _k in range(6):
        s = new_student()
        e = enroll(s, old[n])
        # Entrou por transferência: as UCs dos anos anteriores creditam-se por equivalência.
        for line in old[n].curriculum_id.line_ids.filtered(lambda l: l.year_id.year < n and l.is_compulsory):
            env['edu.uc.registration']._edu_credit_equivalence(
                e, line.subject_id, rnd.choice([11, 12, 13, 14, 15]), 'Transferência (processo de equivalência)'
            )
        history[n].append((s, e))
fails = {(1, 0): ('AM2',), (1, 1): ('PRG2', 'MD', 'AM2'), (2, 0): ('SO',), (3, 2): ('SD',)}
for n, rows in history.items():
    history_grades(old[n], {e.id: fails.get((n, k), ()) for k, (s, e) in enumerate(rows)})
for sem in y1.trimester_ids.sorted('number'):
    sem.action_close()
# Época normal: os admitidos fazem exame (quase todos aprovam).
for n, rows in history.items():
    for s, e in rows:
        for r in e.uc_registration_ids.filtered(lambda r: r.frequency_status == 'admitted'):
            r.exam_normal = rnd.choice([10, 11, 12, 13, 14, 15])
Result = env['edu.year.result']
for edu_class in old.values():
    Result._compute_for_classes(edu_class)
    edu_class.enrollment_ids._edu_close_year()

# 2026/2027: os que passaram sobem; o retido repete o ano; novos no 1.º ano e no mestrado.
current = []
for n, rows in history.items():
    for s, e in rows:
        status = e.year_result_id.status
        target = cur[n] if status == 'retained' else cur[n + 1]
        current.append(enroll(s, target))
for _k in range(10):
    current.append(enroll(new_student(), cur[1]))
masters = [enroll(new_student(), mg1) for _k in range(5)]
# Optativas
for e in current:
    for line in e.class_id.subject_line_ids.filtered(lambda l: l.uc_type == 'optional'):
        if line.subject_id not in e.uc_registration_ids.subject_id:
            try:
                env['edu.uc.registration'].create({'enrollment_id': e.id, 'subject_id': line.subject_id.id})
            except Exception:
                pass

# 1.º semestre em curso: a 1.ª frequência das UCs do 1.º semestre (e das anuais com trabalho).
sem1 = y2.trimester_ids.sorted('number')[0]
for edu_class in [*cur.values(), mg1]:
    for line in edu_class.subject_line_ids.filtered(lambda l: l.semester in ('1', 'annual') and not l.is_final_work):
        a = env['edu.assessment'].create(
            {
                'name': '1.ª Frequência',
                'class_id': edu_class.id,
                'subject_id': line.subject_id.id,
                'trimester_id': sem1.id,
                'assessment_type': 'frequency',
                'date': date(2026, 10, 27),
            }
        )
        a.action_fill_students()
        for g in a.grade_ids:
            g.score = rnd.choice([6, 8, 9.5, 11, 12, 13, 14, 15, 16, 17, 18])
        w = env['edu.assessment'].create(
            {
                'name': 'Trabalho prático',
                'class_id': edu_class.id,
                'subject_id': line.subject_id.id,
                'trimester_id': sem1.id,
                'assessment_type': 'coursework',
                'weight': 0.5,
                'date': date(2026, 10, 20),
            }
        )
        w.action_fill_students()
        for g in w.grade_ids:
            g.score = rnd.choice([10, 12, 14, 15, 16, 18])

# TFC dos finalistas
for e in [x for x in current if x.class_id == cur[4]][:3]:
    p = env['edu.final.project'].create(
        {
            'name': rnd.choice(
                [
                    'Plataforma de gestão escolar para o ensino superior',
                    'Detecção de fraude em pagamentos móveis com aprendizagem automática',
                    'Sistema de informação geográfica para a recolha de resíduos em Luanda',
                ]
            ),
            'student_id': e.student_id.id,
            'enrollment_id': e.id,
            'advisor_id': teachers[0].id,
            'co_advisor_id': teachers[3].id,
        }
    )
    p.action_start()

# Plano de propinas e emolumentos
Plan = env['edu.fee.plan']
Plan.create(
    {
        'name': 'Propinas e emolumentos 2026/2027',
        'academic_year_id': y2.id,
        'line_ids': [
            (0, 0, {'name': 'Propina', 'category': 'tuition', 'recurrence': 'monthly', 'amount': 85000}),
            (
                0,
                0,
                {
                    'name': 'Inscrição em UC em atraso',
                    'category': 'service',
                    'recurrence': 'one_off',
                    'amount': 15000,
                    'uc_trigger': 'backlog',
                },
            ),
            (
                0,
                0,
                {
                    'name': 'Exame de recurso',
                    'category': 'exam',
                    'recurrence': 'one_off',
                    'amount': 7500,
                    'uc_trigger': 'uc_appeal',
                },
            ),
            (
                0,
                0,
                {
                    'name': 'Exame especial',
                    'category': 'exam',
                    'recurrence': 'one_off',
                    'amount': 12000,
                    'uc_trigger': 'uc_special',
                },
            ),
            (
                0,
                0,
                {
                    'name': 'Declaração com notas',
                    'category': 'service',
                    'recurrence': 'one_off',
                    'amount': 3000,
                    'mandatory': False,
                },
            ),
        ],
    }
)

# Utilizadores
Users = env['res.users'].with_context(no_reset_password=True)
lines = ['Base: kututa_universidade (http://universidade.localhost:8069/web/login?db=kututa_universidade)', '']


def user(login, name, groups, partner=None, employee=None):
    pwd = secrets.token_urlsafe(9)
    vals = {
        'login': login,
        'name': name,
        'password': pwd,
        'company_id': company.id,
        'company_ids': [(6, 0, company.ids)],
        'group_ids': [(6, 0, [env.ref(g).id for g in groups])],
    }
    if partner:
        vals['partner_id'] = partner.id
    u = Users.create(vals)
    if employee:
        employee.user_id = u
    lines.append(f'{name}: {login} / {pwd}')
    return u


user('secretaria.kianda', 'Secretaria Académica', ['edu_core.group_edu_manager'])
user('docente.kianda', teachers[0].name, ['edu_core.group_edu_teacher'], employee=teachers[0])
backlog_student = next(e for e in current if e.uc_registration_ids.filtered('is_backlog'))
user(
    'estudante.kianda',
    backlog_student.student_id.name,
    ['edu_portal.group_edu_student'],
    partner=backlog_student.student_id.partner_id,
)
env.cr.commit()

with open(OUT, 'w') as f:
    f.write('\n'.join(lines) + '\n')
os.chmod(OUT, 0o600)
print(
    'OK',
    len(current),
    'matrículas 2026/27;',
    len(masters),
    'mestrado; estudante com atraso:',
    backlog_student.student_id.name,
)
