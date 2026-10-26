from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.edu_migration_secped import secped_final, secped_general_final
from ..models.secped_source import MemorySource

SCHOOL = {
    'id': 'sch',
    'name': 'Instituto Técnico de Teste',
    'slug': 'teste',
    'type': 'TECNICO_PROFISSIONAL',
    'schoolOwnership': 'PRIVADA',
    'billingMode': 'MONTHLY_TUITION',
    'municipality': 'Sumbe',
    'province': 'Cuanza Sul',
    'directorName': 'Maria Directora',
    'pedagogicalDirectorName': 'João Pedagógico',
}


def _row(**values):
    return {'schoolId': 'sch', 'deletedAt': None, **values}


def _calendar():
    """2025/26 fechado e 2026/27 em curso, com o I Trimestre aberto."""
    years = [
        _row(id='y25', name='2025/2026', startDate=datetime(2025, 9, 1), endDate=datetime(2026, 7, 31), current=False),
        _row(id='y26', name='2026/2027', startDate=datetime(2026, 9, 1), endDate=datetime(2027, 7, 31), current=True),
    ]
    trimesters = []
    for year, start in (('y25', 2025), ('y26', 2026)):
        bounds = [
            (datetime(start, 9, 1), datetime(start, 12, 20)),
            (datetime(start + 1, 1, 5), datetime(start + 1, 4, 10)),
            (datetime(start + 1, 4, 13), datetime(start + 1, 7, 31)),
        ]
        for number, (begin, end) in enumerate(bounds, 1):
            trimesters.append(
                _row(
                    id=f'{year}t{number}',
                    academicYearId=year,
                    name=f'{number}.º Trimestre',
                    number=number,
                    startDate=begin,
                    endDate=end,
                    current=year == 'y26' and number == 1,
                    closedAt=datetime(start + 1, 7, 31) if year == 'y25' else None,
                )
            )
    return years, trimesters


def _tables():
    """Uma escola técnica com um ano fechado (2025/26, 10.ª) e o ano em curso (2026/27, 11.ª)."""
    years, trimesters = _calendar()
    users = [
        _row(id='u1', role='STUDENT', email='ana@escola.aluno', firstName='Ana', lastName='Lopes'),
        _row(id='u2', role='STUDENT', email='bento@escola.aluno', firstName='Bento', lastName='Sousa'),
        _row(id='u9', role='STUDENT', email='teste@escola.test', firstName='Aluno', lastName='(teste)'),
        _row(id='t1', role='TEACHER', email='rita@escola.ao', firstName='Rita', lastName='Professora'),
        _row(id='d1', role='SCHOOL_ADMIN', email='direccao@escola.ao', firstName='Maria', lastName='Directora'),
        _row(id='s1', role='ADMIN_SERVICOS', email='secretaria@escola.ao', firstName='Secretaria', lastName=''),
        _row(id='f1', role='STAFF', email='Financas@escola.ao', firstName='Gestão', lastName='Financeira'),
        _row(id='b1', role='ADMIN_BIBLIOTECA', email='biblioteca@escola.ao', firstName='Biblioteca', lastName=''),
    ]
    profiles = [
        _row(id='p1', userId='u1', matriculaNumber='2025-0001', matriculaYear=2025, matriculaSeq=1, gender='F'),
        _row(id='p2', userId='u2', matriculaNumber='2025-0002', matriculaYear=2025, matriculaSeq=2, gender='M'),
        _row(id='p9', userId='u9', matriculaNumber='2025-0003', matriculaYear=2025, matriculaSeq=3),
    ]
    subjects = [
        _row(id='lp', name='Língua Portuguesa', code='LP', component='SOCIO_CULTURAL'),
        _row(id='ef', name='Educação Física', code='EF', component='SOCIO_CULTURAL'),
        _row(id='qm', name='Química', code='QM', component='CIENTIFICA'),
    ]
    curriculum_subjects = []
    for year_id in ('cy10', 'cy11'):
        curriculum_subjects += [
            _row(id=f'{year_id}lp', curriculumYearId=year_id, subjectId='lp', weeklyHours=4, isCompulsory=True),
            _row(id=f'{year_id}ef', curriculumYearId=year_id, subjectId='ef', weeklyHours=2, isCompulsory=True),
        ]
    enrollments = [
        _row(id='e1', userId='u1', classId='c10', academicYearId='y25', status='ACTIVE', orderNumber=1),
        _row(id='e2', userId='u2', classId='c10', academicYearId='y25', status='ACTIVE', orderNumber=2),
        _row(id='e9', userId='u9', classId='c10', academicYearId='y25', status='ACTIVE', orderNumber=3),
        _row(id='e3', userId='u1', classId='c11', academicYearId='y26', status='ACTIVE', orderNumber=1),
    ]
    for enrollment in enrollments:
        enrollment['createdAt'] = datetime(2025, 9, 1)

    def grades(enrollment, user, subject, scores, pg=None):
        ct1, ct2, cf = scores
        rows = [
            _row(id=f'{enrollment}{subject}1', enrollmentId=enrollment, userId=user, subjectId=subject,
                 trimesterId='y25t1', type='TRIMESTRAL', score=ct1),
            _row(id=f'{enrollment}{subject}2', enrollmentId=enrollment, userId=user, subjectId=subject,
                 trimesterId='y25t2', type='TRIMESTRAL', score=ct2),
            _row(id=f'{enrollment}{subject}3', enrollmentId=enrollment, userId=user, subjectId=subject,
                 trimesterId='y25t3', type='TRIMESTRAL', score=cf),
            _row(id=f'{enrollment}{subject}a', enrollmentId=enrollment, userId=user, subjectId=subject,
                 trimesterId=None, type='ANUAL', score=cf),
        ]  # fmt: skip
        if pg is not None:
            rows.append(
                _row(id=f'{enrollment}{subject}g', enrollmentId=enrollment, userId=user, subjectId=subject,
                     trimesterId=None, type='GLOBAL', score=pg)
            )  # fmt: skip
        return rows

    return {
        'users': users,
        'academic_years': years,
        'trimesters': trimesters,
        'departments': [_row(id='dep', name='Coordenação de Enfermagem', code='ENF', type='CURSO', headId='t1')],
        'school_shifts': [_row(id='sh1', name='Manhã', type='MORNING', startTime=420, endTime=725, isActive=True)],
        'time_slots': [
            _row(id='ts1', shiftId='sh1', name='1.º tempo', startTime=420, endTime=465, orderIndex=1, isBreak=False),
            _row(id='ts2', shiftId='sh1', name='Sobreposto', startTime=440, endTime=480, orderIndex=2, isBreak=False),
        ],
        'rooms': [_row(id='r1', name='Sala 01', code='S01', type='CLASSROOM', capacity=40)],
        'subjects': subjects,
        'courses': [_row(id='enf', name='Enfermagem Geral', code='ENF', level='TECNICO', duration=4)],
        'curricula': [
            _row(id='k1', courseId='enf', name='Plano — Enfermagem', level='TECNICO', isActive=True),
        ],
        'curriculum_years': [
            _row(id='cy10', curriculumId='k1', year=1, classNumber=10, name='1.º ano'),
            _row(id='cy11', curriculumId='k1', year=2, classNumber=11, name='2.º ano'),
        ],
        'curriculum_subjects': curriculum_subjects,
        'evaluation_policies': [
            _row(
                id='pol',
                level='TECNICO',
                minPassGrade=10,
                minAttendanceRate=0.667,
                maxRetentions=2,
                roundingMode='INTEGER',
                isActive=True,
            )
        ],  # fmt: skip
        'promotion_rules': [_row(id='pr', level='TECNICO', maxNegatives=2)],
        'school_classes': [
            _row(id='c10', courseId='enf', name='10ª A', classNumber=10, capacity=40, shiftId='sh1', roomId='r1'),
            _row(id='c11', courseId='enf', name='11ª A', classNumber=11, capacity=40, shiftId='sh1', roomId='r1'),
        ],
        'class_offerings': [
            _row(id='o10', classId='c10', academicYearId='y25', isActive=True, capacity=40),
            _row(id='o11', classId='c11', academicYearId='y26', isActive=True, capacity=40),
        ],
        'student_profiles': profiles,
        'staff_profiles': [_row(id='sp1', userId='f1', position='Gestão Financeira')],
        'teacher_profiles': [_row(id='tp1', userId='t1', specialization='Enfermagem', departmentId='dep')],
        'enrollments': enrollments,
        'enrollment_subjects': [
            _row(id=f'{e}{s}', enrollmentId=e, subjectId=s) for e in ('e1', 'e2', 'e9', 'e3') for s in ('lp', 'ef')
        ],
        'subject_teachers': [
            _row(id=f'st{n}', teacherId='t1', subjectId='lp', classId='c11', trimesterId=f'y26t{n}') for n in (1, 2, 3)
        ]
        + [_row(id='stq', teacherId='t1', subjectId='qm', classId='c11', trimesterId='y26t1')],
        'schedules': [
            _row(
                id='s1',
                classId='c11',
                subjectId='lp',
                teacherId='t1',
                roomId='r1',
                dayOfWeek=1,
                startTime=420,
                endTime=465,
            ),
        ],  # fmt: skip
        'grades': (
            # Ana: CF 12,8958 e PG 15,5 → 0,6 × 12,8958 + 0,4 × 15,5 = 13,94 → 14.
            grades('e1', 'u1', 'lp', (14.3333, 14.2917, 12.8958), 15.5)
            # A PG na Educação Física (2 tempos) conta, como no secPed: 0,6 × 11 + 0,4 × 13 = 11,8 → 12.
            + grades('e1', 'u1', 'ef', (11, 11, 11), 13)
            # Bento: CF 8,6 sem PG → 9, mais 1 do conselho → 10; Educação Física 7.
            + grades('e2', 'u2', 'lp', (8, 9, 8.6))
            + grades('e2', 'u2', 'ef', (7, 7, 7))
            + grades('e9', 'u9', 'lp', (10, 10, 10))
        ),
        'grade_council_adjustments': [
            _row(
                id='adj',
                classId='c10',
                academicYearId='y25',
                studentId='u2',
                subjectId='lp',
                points=1,
                source='COUNCIL',
            )
        ],  # fmt: skip
        'academic_records': [
            _row(
                id='ar1', userId='u1', academicYearId='y25', classId='c10', status='ACTIVE', promotionStatus='PROMOTED'
            ),
            _row(
                id='ar2', userId='u2', academicYearId='y25', classId='c10', status='ACTIVE', promotionStatus='RETAINED'
            ),
        ],  # fmt: skip
        'exam_periods': [
            _row(
                id='ep',
                academicYearId='y26',
                trimesterId='y26t1',
                name='Provas do I Trimestre',
                startDate=datetime(2026, 12, 9),
                endDate=datetime(2026, 12, 18),
            )
        ],  # fmt: skip
        'exam_sessions': [
            _row(
                id='es1',
                academicYearId='y26',
                examPeriodId='ep',
                subjectId='lp',
                classId='c11',
                name='Língua Portuguesa',
                date=datetime(2026, 12, 9),
                startTime=480,
                endTime=600,
            ),
        ],  # fmt: skip
        'exam_rooms': [_row(id='er1', examSessionId='es1', roomId='r1', capacity=40)],
        'exam_supervisors': [_row(id='esv', examSessionId='es1', examRoomId='er1', supervisorId='t1')],
        'tuition_plans': [_row(id='tpl', academicYearId='y26', courseId='enf', name='Propinas — Enfermagem')],
        'tuition_fees': [
            _row(
                id='fee',
                tuitionPlanId='tpl',
                name='Propina Mensal',
                amount=22936,
                dueDay=8,
                category='PROPINA',
                recurrence='MONTHLY',
                mandatory=True,
                taxRate=0,
            ),
            _row(
                id='bata',
                tuitionPlanId='tpl',
                name='Batas',
                amount=21400,
                dueDay=8,
                category='SERVICO',
                recurrence='ONE_OFF',
                mandatory=False,
                taxRate=14,
            ),
        ],  # fmt: skip
        'late_fee_configs': [
            _row(
                id='lf',
                name='Multa de atraso',
                graceDays=15,
                feeType='FIXED',
                feeValue=5734,
                tuitionFeeId='fee',
                isActive=True,
            )
        ],  # fmt: skip
        'tuition_invoices': [_row(id='inv')],
    }


@tagged('post_install', '-at_install', 'edu')
class TestEduMigrationSecped(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create(
            {'name': 'Escola por migrar', 'country_id': cls.env.ref('base.ao').id}
        )
        cls.env.user.company_ids |= cls.company
        cls.env['account.chart.template'].try_loading('ao', cls.company, install_demo=False)
        cls.source = MemorySource(SCHOOL, _tables())
        cls.report = cls.env['edu.migration.secped']._run(cls.source, company=cls.company)
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))

    def _student(self, matricula):
        return self.env['edu.student'].search(
            [('matricula_number', '=', matricula), ('company_id', '=', self.company.id)]
        )

    def _result(self, matricula, code, year='2025/2026'):
        return self.env['edu.subject.result'].search(
            [
                ('student_id', '=', self._student(matricula).id),
                ('subject_id.code', '=', code),
                ('academic_year_id.name', '=', year),
            ]
        )

    def test_secped_formula(self):
        self.assertEqual(secped_final(12.8958, 15.5, 0), 14)
        self.assertEqual(secped_final(8.6, None, 1), 10)
        self.assertEqual(secped_final(19.6, None, 2), 20)
        self.assertIsNone(secped_final(None, 12, 0))

    def test_structure(self):
        company = self.company
        self.assertEqual(company.edu_school_type, 'technical')
        self.assertEqual(company.edu_director_name, 'Maria Directora')
        classes = self.env['edu.class'].search([('company_id', '=', company.id)])
        self.assertEqual(
            sorted(classes.mapped('complete_name')), ['10ª A · ENF · 2025/2026', '11ª A · ENF · 2026/2027']
        )
        self.assertTrue(all(classes.mapped('curriculum_year_id')))
        year = self.env['edu.academic.year'].search([('company_id', '=', company.id), ('is_current', '=', True)])
        self.assertEqual(year.name, '2026/2027')
        closed = self.env['edu.trimester'].search(
            [('academic_year_id.name', '=', '2025/2026'), ('company_id', '=', company.id)]
        )
        self.assertEqual(set(closed.mapped('state')), {'closed'})
        # Tempos sobrepostos ficam de fora; o resto entra.
        self.assertEqual(self.env['edu.time.slot'].search_count([('company_id', '=', company.id)]), 1)
        policy = self.env['edu.evaluation.policy']._get(company, classes[0].level_id)
        self.assertTrue(policy.technical_ca_precise)

    def test_people_and_enrollments(self):
        company = self.company
        students = self.env['edu.student'].search([('company_id', '=', company.id)])
        # O aluno de teste (endereço .test) não migra.
        self.assertEqual(sorted(students.mapped('matricula_number')), ['2025-0001', '2025-0002'])
        ana = self._student('2025-0001')
        self.assertEqual((ana.name, ana.gender), ('Ana Lopes', 'female'))
        enrollments = ana.enrollment_ids.sorted('date')
        self.assertEqual(enrollments.mapped('enrollment_type'), ['new', 'renewal'])
        self.assertEqual(enrollments[1].previous_enrollment_id, enrollments[0])
        self.assertEqual(set(enrollments[1].subject_ids.mapped('code')), {'LP', 'EF'})
        teacher = self.env['hr.employee'].search([('company_id', '=', company.id), ('edu_is_teacher', '=', True)])
        self.assertEqual(teacher.name, 'Rita Professora')
        self.assertEqual(self.env['edu.coordination'].search([('company_id', '=', company.id)]).head_id, teacher)
        # O mesmo professor nos três trimestres: uma atribuição do ano.
        assignments = self.env['edu.teaching.assignment'].search([('company_id', '=', company.id)])
        self.assertEqual((len(assignments), assignments.trimester_id), (1, self.env['edu.trimester']))
        self.assertIn(('atribuições', 'Química na 11ª A · ENF · 2026/2027: fora do plano da turma, ficou de fora'),
                      self.report['issues'])  # fmt: skip
        schedule = self.env['edu.schedule'].search([('company_id', '=', company.id)])
        self.assertEqual((schedule.weekday, schedule.hour_from, schedule.teacher_id), ('0', 7.0, teacher))
        self.assertTrue(schedule.time_slot_id)

    def test_users(self):
        users = self.env['res.users'].search([('company_ids', 'in', self.company.id), ('login', 'like', '@escola.ao')])
        by_login = {user.login: user for user in users}
        self.assertEqual(
            sorted(by_login), ['direccao@escola.ao', 'financas@escola.ao', 'rita@escola.ao', 'secretaria@escola.ao']
        )
        teacher = by_login['rita@escola.ao']
        self.assertTrue(teacher.has_group('edu_core.group_edu_teacher'))
        self.assertFalse(teacher.has_group('edu_core.group_edu_user'))
        self.assertEqual(teacher.employee_id.name, 'Rita Professora')
        self.assertTrue(by_login['direccao@escola.ao'].has_group('edu_core.group_edu_manager'))
        self.assertEqual(by_login['direccao@escola.ao'].employee_id.job_title, 'Director(a) geral')
        self.assertTrue(by_login['secretaria@escola.ao'].has_group('edu_core.group_edu_user'))
        self.assertTrue(by_login['financas@escola.ao'].has_group('edu_fees.group_edu_finance'))
        self.assertIn(('contas', 'Sem perfil na Secretaria Express, ficaram sem conta: biblioteca@escola.ao'),
                      self.report['issues'])  # fmt: skip

    def test_grades_and_decisions(self):
        lp = self._result('2025-0001', 'LP')
        self.assertEqual((lp.mt1, lp.mt2, lp.mt3), (14.33, 14.29, 12.9))
        self.assertEqual(lp.imported_cf, 12.8958)
        # A CF importada fica com as casas decimais (no técnico só a CA e a CFD se arredondam): 0,6 × 12,8958 + 0,4 ×
        # 15,5 = 13,94 → 14.
        self.assertEqual((lp.cf, lp.pg, lp.annual, lp.final), (12.9, 15.5, 14, 14))
        self.assertEqual(self._result('2025-0001', 'EF').final, 12)
        bento = self._result('2025-0002', 'LP')
        self.assertEqual((bento.annual, bento.council_points, bento.final), (9, 1, 10))
        pauta = self.report['metrics']['pauta']
        self.assertEqual((pauta['iguais'], pauta['diferentes']), (4, 0))
        decisions = self.env['edu.year.result'].search([('company_id', '=', self.company.id)])
        by_name = {d.student_id.name: d for d in decisions}
        self.assertEqual(by_name['Ana Lopes'].status, 'promoted')
        self.assertEqual(by_name['Ana Lopes'].enrollment_id.state, 'completed')
        # O Bento só tem uma negativa (EF): o cálculo transitava-o, a pauta assinada diz que não transita.
        self.assertEqual((by_name['Bento Sousa'].status, by_name['Bento Sousa'].manual), ('retained', True))
        self.assertEqual(by_name['Bento Sousa'].enrollment_id.state, 'retained')

    def test_exams_and_fees(self):
        session = self.env['edu.exam.session'].search([('company_id', '=', self.company.id)])
        self.assertEqual((session.hour_from, session.hour_to, len(session.class_ids)), (8.0, 10.0, 1))
        self.assertEqual(session.room_ids.supervisor_ids.name, 'Rita Professora')
        plan = self.env['edu.fee.plan'].search([('company_id', '=', self.company.id)])
        self.assertEqual(sorted(plan.line_ids.mapped('category')), ['service', 'tuition'])
        bata = plan.line_ids.filtered(lambda line: line.name == 'Batas')
        self.assertEqual(bata.tax_id.amount, 14)
        rule = self.env['edu.late.fee.rule'].search([('company_id', '=', self.company.id)])
        self.assertEqual((rule.fee_type, rule.amount), ('fixed', 5734))
        self.assertTrue(any(kind == 'propinas' for kind, _detail in self.report['issues']))

    def test_idempotent(self):
        def counts():
            return {
                model: self.env[model].search_count([('company_id', '=', self.company.id)])
                for model in ('res.users', 'edu.student', 'edu.enrollment', 'edu.class', 'edu.grade',
                              'edu.subject.result', 'edu.term.result', 'edu.schedule', 'edu.year.result',
                              'edu.fee.plan.line')
            }  # fmt: skip

        before = counts()
        with self.assertRaisesRegex(UserError, 'já correu'):
            self.env['edu.migration.secped']._run(self.source, company=self.company)
        report = (
            self.env['edu.migration.secped']
            .with_context(edu_migration_rerun=True)
            ._run(self.source, company=self.company)
        )
        self.assertEqual(counts(), before)
        self.assertEqual(report['metrics']['pauta']['diferentes'], 0)
        self.assertEqual(self._result('2025-0001', 'LP').final, 14)
        self.assertEqual(self._student('2025-0001').enrollment_ids.sorted('date')[0].state, 'completed')


GENERAL_SCHOOL = {
    **SCHOOL,
    'name': 'Complexo Escolar de Teste',
    'type': 'GERAL',
    'educationLevels': ['INICIACAO', 'SECUNDARIO_I_CICLO'],
    'tutelaSchoolName': 'Escola Pública N.º 1',
    'tutelaDirectorName': 'Directora da Tutela',
}


def _general_tables():
    """Uma escola do geral: a 9.ª (classe de exame) em 2025/26, fechada, e a Iniciação em 2026/27."""
    years, trimesters = _calendar()

    def grades(subject, mts, anual, national, final):
        rows = [
            _row(id=f'{subject}{n}', enrollmentId='e1', userId='u1', subjectId=subject, trimesterId=f'y25t{n}',
                 type='TRIMESTRAL', score=mt)
            for n, mt in enumerate(mts, 1)
        ]  # fmt: skip
        for kind, score in (('ANUAL', anual), ('NACIONAL', national), ('FINAL', final)):
            rows.append(
                _row(id=f'{subject}{kind}', enrollmentId='e1', userId='u1', subjectId=subject, trimesterId=None,
                     type=kind, score=score)
            )  # fmt: skip
        return rows

    return {
        'users': [
            _row(id='u1', role='STUDENT', status='PENDING', email='lbd-1@escola.aluno', firstName='Ana', lastName='G'),
            _row(id='u2', role='STUDENT', status='ACTIVE', email='lbd-2@escola.aluno', firstName='Rui', lastName='P'),
        ],
        'academic_years': years,
        'trimesters': trimesters,
        'subjects': [
            _row(id='lp', name='Língua Portuguesa', code='LP'),
            _row(id='mat', name='Matemática', code='MAT'),
            _row(id='exp', name='Expressão Plástica', code='EXP'),
            _row(id='emc', name='Educação Moral e Cívica', code='EMC'),
        ],
        'courses': [
            _row(
                id='sec1',
                name='I Ciclo do Ensino Secundário Geral',
                code='SEC1',
                level='SECUNDARIO_I_CICLO',
                duration=3,
            ),
            _row(id='inic', name='Iniciação', code='INIC', level='INICIACAO', duration=1),
        ],  # fmt: skip
        'curricula': [
            _row(id='k1', courseId='sec1', name='Plano — I Ciclo', level='SECUNDARIO_I_CICLO', isActive=True),
            _row(id='k0', courseId='inic', name='Plano — Iniciação', level='INICIACAO', isActive=True),
        ],
        'curriculum_years': [
            _row(id='cy9', curriculumId='k1', year=3, classNumber=9, name='9.ª classe'),
            _row(id='cy0', curriculumId='k0', year=1, classNumber=0, name='Iniciação'),
        ],
        'curriculum_subjects': [
            _row(id='l9lp', curriculumYearId='cy9', subjectId='lp', weeklyHours=5, isCompulsory=True),
            _row(id='l9mat', curriculumYearId='cy9', subjectId='mat', weeklyHours=5, isCompulsory=True),
            _row(id='l0exp', curriculumYearId='cy0', subjectId='exp', weeklyHours=3, isCompulsory=True),
        ],
        'evaluation_policies': [
            _row(
                id='pol',
                level='SECUNDARIO_I_CICLO',
                minPassGrade=10,
                minAttendanceRate=0.667,
                maxRetentions=2,
                roundingMode='INTEGER',
                isActive=True,
            ),
        ],  # fmt: skip
        'promotion_rules': [_row(id='pr', level='SECUNDARIO_I_CICLO', maxNegatives=0)],
        'school_classes': [
            _row(id='c9', courseId='sec1', name='9ª A', classNumber=9, capacity=40),
            _row(id='c0', courseId='inic', name='Iniciação A', classNumber=0, capacity=25),
        ],
        'class_offerings': [
            _row(id='o9', classId='c9', academicYearId='y25', isActive=True),
            _row(id='o0', classId='c0', academicYearId='y26', isActive=True),
        ],
        'student_profiles': [
            _row(id='p1', userId='u1', matriculaNumber='LBD-0001', matriculaYear=2025, matriculaSeq=1),
            _row(id='p2', userId='u2', matriculaNumber='LBD-0002', matriculaYear=2026, matriculaSeq=2),
        ],
        'enrollments': [
            _row(
                id='e1',
                userId='u1',
                classId='c9',
                academicYearId='y25',
                status='ACTIVE',
                orderNumber=1,
                createdAt=datetime(2025, 9, 1),
            ),
            _row(
                id='e2',
                userId='u2',
                classId='c0',
                academicYearId='y26',
                status='ACTIVE',
                orderNumber=1,
                createdAt=datetime(2026, 9, 1),
            ),
        ],  # fmt: skip
        'enrollment_subjects': [
            _row(id='e1lp', enrollmentId='e1', subjectId='lp'),
            _row(id='e1mat', enrollmentId='e1', subjectId='mat'),
            # Do plano antigo: a pauta de 2025/26 tem-na, o plano actual da escola já não.
            _row(id='e1emc', enrollmentId='e1', subjectId='emc'),
            _row(id='e2exp', enrollmentId='e2', subjectId='exp'),
        ],
        'grades': (
            # A MF da escola é 0,4 × MFD + 0,6 × NE (13 e 18,5 → 16,4; a pauta diz 16,7): vale a assinada, 17. Pelo
            # Dec. 424/25 seria 0,6 × MT3 + 0,4 × EN = 15,8 → 16.
            grades('lp', (12, 13, 14), 13, 18.5, 16.7)
            + grades('mat', (10, 11, 12), 11, 9, 10.2)
            + grades('emc', (14, 14, 15), 14, 15, 14.6)
        ),
        'academic_records': [
            _row(id='ar1', userId='u1', academicYearId='y25', classId='c9', promotionStatus='GRADUATED'),
        ],
    }


@tagged('post_install', '-at_install', 'edu')
class TestEduMigrationGeneral(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create(
            {'name': 'Escola geral por migrar', 'country_id': cls.env.ref('base.ao').id}
        )
        cls.env.user.company_ids |= cls.company
        cls.env['account.chart.template'].try_loading('ao', cls.company, install_demo=False)
        cls.report = cls.env['edu.migration.secped']._run(MemorySource(GENERAL_SCHOOL, _general_tables()),
                                                          company=cls.company)  # fmt: skip

    def test_general_formula(self):
        self.assertEqual(secped_general_final(13, 16.7, 0), 17)
        self.assertEqual(secped_general_final(9.5, None, 0), 10)
        self.assertEqual(secped_general_final(19, None, 2), 20)
        self.assertIsNone(secped_general_final(None, None, 0))

    def test_school(self):
        company = self.company
        self.assertEqual(company.edu_school_type, 'general')
        self.assertEqual(sorted(company.edu_level_ids.mapped('code')), ['INICIACAO', 'SECUNDARIO_I_CICLO'])
        self.assertEqual(company.edu_supervisor_school, 'Escola Pública N.º 1')
        classes = self.env['edu.class'].search([('company_id', '=', company.id)])
        self.assertEqual(
            sorted(classes.mapped('complete_name')), ['9ª A · SEC1 · 2025/2026', 'Iniciação A · INIC · 2026/2027']
        )
        # A tolerância de negativas do geral fica a do RAA (2), não o 0 do secPed.
        policy = self.env['edu.evaluation.policy']._get(
            company, classes.level_id.filtered(lambda level: level.class_to == 9)
        )
        self.assertEqual(policy.conditional_max, 2)
        # A 9.ª de 2025/26 fica com uma cópia arquivada do plano, com a disciplina do plano antigo.
        ninth = classes.filtered(lambda c: c.class_number == 9)
        self.assertFalse(ninth.curriculum_id.active)
        self.assertEqual(ninth.curriculum_id.name, 'Plano — I Ciclo (2025/2026)')
        self.assertEqual(sorted(ninth.subject_line_ids.subject_id.mapped('code')), ['EMC', 'LP', 'MAT'])
        # O plano do curso (o das turmas novas) continua a ser o actual.
        self.assertEqual(ninth.course_id.curriculum_id.name, 'Plano — I Ciclo')

    def test_exam_class(self):
        results = self.env['edu.subject.result'].search([('company_id', '=', self.company.id)])
        lp = results.filtered(lambda r: r.subject_id.code == 'LP')
        self.assertEqual((lp.cf, lp.national, lp.imported_final, lp.annual, lp.final), (13, 18.5, 16.7, 17, 17))
        self.assertTrue(lp.complete and lp.passed)
        self.assertEqual(results.filtered(lambda r: r.subject_id.code == 'MAT').final, 10)
        exams = self.env['edu.assessment'].search(
            [('class_id.company_id', '=', self.company.id), ('assessment_type', '=', 'national_exam')]
        )
        self.assertEqual(len(exams), 3)
        pauta = self.report['metrics']['pauta']
        self.assertEqual((pauta['iguais'], pauta['diferentes']), (3, 0))
        self.assertEqual(results.filtered(lambda r: r.subject_id.code == 'EMC').final, 15)
        decision = self.env['edu.year.result'].search([('company_id', '=', self.company.id)])
        self.assertEqual(decision.status, 'graduated')

    def test_student_accounts(self):
        # Só o aluno com acesso no secPed (o do ano em curso) tem conta, na Área do Estudante.
        users = self.env['res.users'].search([('login', 'like', '@escola.aluno')])
        self.assertEqual(users.mapped('login'), ['lbd-2@escola.aluno'])
        self.assertEqual(
            users.partner_id, self.env['edu.student'].search([('matricula_number', '=', 'LBD-0002')]).partner_id
        )
        self.assertTrue(users._edu_student_only())
