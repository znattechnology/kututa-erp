from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduEvaluation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.t1, cls.t2, cls.t3 = cls.year.trimester_ids.sorted('number')
        cls.t1.is_current = True
        cls.next_year = cls.env['edu.academic.year'].create(
            {'name': '2027/2028', 'date_start': date(2027, 9, 1), 'date_end': date(2028, 7, 31)}
        )
        cls.sec1 = cls._course('Ensino secundário I ciclo', 'SEC1', 'level_sec1', None)
        cls.tec = cls._course('Técnico de Enfermagem', 'ENF', 'level_tecnico', 'tpl_tec_saude_enf')
        cls.class7 = cls._class(cls.sec1, 7)
        cls.class9 = cls._class(cls.sec1, 9)
        cls.class10 = cls._class(cls.tec, 10)
        cls.students = cls.env['edu.student'].create([{'name': n} for n in ('Ana', 'Bento', 'Carla', 'Domingos')])
        cls.teacher_user = cls.env['res.users'].create(
            {
                'name': 'Rita Professora',
                'login': 'rita_prof',
                'group_ids': [Command.set([cls.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        cls.teacher = cls.env['hr.employee'].create(
            {'name': 'Rita Professora', 'edu_is_teacher': True, 'user_id': cls.teacher_user.id}
        )

    @classmethod
    def _course(cls, name, code, level, template):
        vals = {'name': name, 'code': code, 'level_id': cls.env.ref(f'edu_core.{level}').id}
        if template:
            vals['curriculum_template_id'] = cls.env.ref(f'edu_core.{template}').id
        return cls.env['edu.course'].create(vals)

    @classmethod
    def _class(cls, course, number, year=None, name='A'):
        year_line = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == number)
        return cls.env['edu.class'].create(
            {
                'name': name,
                'course_id': course.id,
                'curriculum_year_id': year_line.id,
                'academic_year_id': (year or cls.year).id,
            }
        )

    def _subject(self, edu_class, code):
        return edu_class.subject_line_ids.subject_id.filtered(lambda s: s.code == code)

    def _enroll(self, edu_class, students, codes):
        subjects = edu_class.subject_line_ids.subject_id.filtered(lambda s: s.code in codes)
        enrollments = self.env['edu.enrollment']
        for student in students:
            enrollment = self.env['edu.enrollment'].create(
                {'student_id': student.id, 'class_id': edu_class.id, 'subject_ids': [Command.set(subjects.ids)]}
            )
            enrollment.action_confirm()
            enrollments |= enrollment
        return enrollments

    def _assess(self, edu_class, code, trimester, kind, scores, *, max_score=None, user=None):
        Assessment = self.env['edu.assessment'].with_user(user) if user else self.env['edu.assessment']
        vals = {
            'name': f'{kind} {trimester.number}',
            'class_id': edu_class.id,
            'subject_id': self._subject(edu_class, code).id,
            'trimester_id': trimester.id,
            'assessment_type': kind,
        }
        if max_score:
            vals['max_score'] = max_score
        assessment = Assessment.create(vals)
        assessment.action_fill_students()
        for grade in assessment.grade_ids:
            if grade.student_id in scores:
                grade.score = scores[grade.student_id]
        return assessment

    def _term(self, enrollment, code, trimester):
        return self.env['edu.term.result'].search(
            [
                ('enrollment_id', '=', enrollment.id),
                ('subject_id.code', '=', code),
                ('trimester_id', '=', trimester.id),
            ]
        )

    def _year_subject(self, enrollment, code):
        return self.env['edu.subject.result'].search(
            [('enrollment_id', '=', enrollment.id), ('subject_id.code', '=', code)]
        )

    def _full_year(self, edu_class, code, scores_by_trimester, pg=True):
        """{trimestre: {aluno: (contínua, prova)}}"""
        policy = self.env['edu.evaluation.policy']._get(edu_class.company_id, edu_class.level_id)
        exam_class = policy.regime == 'general' and policy._is_exam_class(edu_class.class_number)
        last_trimester = edu_class.academic_year_id.trimester_ids.sorted('number')[-1:]
        for trimester, scores in scores_by_trimester.items():
            self._assess(edu_class, code, trimester, 'continuous', {s: v[0] for s, v in scores.items()})
            # O último trimestre não tem prova trimestral no técnico (há a prova global) nem na classe de exame do
            # geral (há o exame nacional).
            if not ((exam_class or policy.regime == 'technical') and trimester == last_trimester):
                self._assess(edu_class, code, trimester, 'trimester_test', {s: v[1] for s, v in scores.items()})
        # Técnico: a disciplina com prova global só fica completa com a PG (lança-se a nota da última prova).
        line = edu_class.subject_line_ids.filtered(lambda line: line.subject_id.code == code)
        last = edu_class.academic_year_id.trimester_ids.sorted('number')[-1:]
        technical = edu_class.level_id.subsystem == 'technical'
        if pg and technical and line.has_global_exam and last in scores_by_trimester:
            scores = scores_by_trimester[last]
            self._assess(edu_class, code, last, 'global_exam', {s: v[1] for s, v in scores.items()})

    def test_general_trimester(self):
        ana = self.students[0]
        enrollment = self._enroll(self.class7, ana, ['LP'])
        self._assess(self.class7, 'LP', self.t1, 'continuous', {ana: 12})
        test = self._assess(self.class7, 'LP', self.t1, 'trimester_test', {ana: 16})
        # MT = (MAC + NPT) / 2 = (12 + 16) / 2 = 14 (grade.service.int-spec).
        self.assertEqual(self._term(enrollment, 'LP', self.t1).mt, 14)
        test.grade_ids.score = 12
        self.assertEqual(self._term(enrollment, 'LP', self.t1).mt, 12)
        # Avaliação cotada para 10: 8/10 vale 16.
        self._assess(self.class7, 'LP', self.t1, 'continuous', {ana: 8}, max_score=10)
        self.assertEqual(self._term(enrollment, 'LP', self.t1).mac, 14)
        with self.assertRaises(ValidationError):
            test.grade_ids.score = 25

    def test_general_decisions(self):
        ana, bento, carla, domingos = self.students
        enrollments = self._enroll(self.class7, self.students, ['LP', 'MAT'])
        # Casos do secPed (promotion-transicao.int-spec), com LP e MAT.
        plan = {ana: (8, 14), bento: (6, 14), carla: (14, 15), domingos: (9, 9)}
        for code, index in (('LP', 0), ('MAT', 1)):
            scores = {student: (values[index], values[index]) for student, values in plan.items()}
            self._full_year(self.class7, code, dict.fromkeys((self.t1, self.t2, self.t3), scores))
        self.class7.action_compute_year_results()
        status = {e.student_id: e.year_result_id.status for e in enrollments}
        self.assertEqual(status[ana], 'conditional')  # uma negativa entre 7 e 9
        self.assertEqual(status[bento], 'retained')  # negativa abaixo de 7
        self.assertEqual(status[carla], 'promoted')
        self.assertEqual(status[domingos], 'retained')  # LP e MAT negativas ao mesmo tempo
        ana_result = enrollments[0].year_result_id
        self.assertEqual(ana_result.negative_subject_ids.code, 'LP')
        requirement = ana_result.requirement_ids
        self.assertEqual((requirement.kind, requirement.subject_id.code), ('extraordinary', 'LP'))
        # Matrícula condicional na 8.ª com a LP em atraso (DE 424/25, art. 25.º); sem prazo fora da 9.ª e da 12.ª.
        eighth = self._class(self.sec1, 8, year=self.next_year)
        conditional = self._enroll(eighth, ana, ['LP'])
        self.assertIn('Matrícula condicional: 1 disciplina(s) em atraso (Língua Portuguesa)', conditional.warning)
        self.assertFalse(conditional._edu_conditional_deadline())
        requirement.score = 12
        requirement.action_record()
        # O extraordinário resolve a disciplina em atraso; a decisão da 7.ª (transitou) não muda.
        self.assertTrue(requirement.passed)
        self.assertEqual(ana_result.status, 'conditional')
        self.assertEqual(self._year_subject(enrollments[0], 'LP').final, 12)
        # Retido não se matricula numa classe acima (art. 25.º).
        with self.assertRaises(UserError):
            self._enroll(eighth, bento, ['LP'])
        # As disciplinas com notas não se retiram e a turma já não se renumera.
        with self.assertRaises(UserError):
            enrollments[2].subject_ids = [Command.set(self._subject(self.class7, 'LP').ids)]
        with self.assertRaises(UserError):
            self.class7.action_renumber_alphabetical()

    def test_national_exam_class(self):
        ana = self.students[0]
        enrollment = self._enroll(self.class9, ana, ['MAT'])
        mat = self._subject(self.class9, 'MAT')
        mat.is_national_exam = True
        self._full_year(self.class9, 'MAT', {self.t1: {ana: (14, 14)}, self.t2: {ana: (10, 10)}})
        # III trimestre da classe de exame: (MT1 + MT2 + MAC3) / 3, sem prova trimestral.
        self._assess(self.class9, 'MAT', self.t3, 'continuous', {ana: 12})
        self.assertEqual(self._term(enrollment, 'MAT', self.t3).mt, 12)
        self._assess(self.class9, 'MAT', self.t3, 'national_exam', {ana: 17})
        result = self._year_subject(enrollment, 'MAT')
        # MFED = 0,6 × 12 + 0,4 × 17 = 14.
        self.assertEqual((result.national, result.annual), (17, 14))
        with self.assertRaises(ValidationError):
            self._assess(self.class7, 'LP', self.t3, 'national_exam', {})

    def test_technical(self):
        ana, bento = self.students[:2]
        enrollments = self._enroll(self.class10, (ana, bento), ['LP'])
        # CT = (NPP + NPT) / 2: participação 8 e prova 12 → 10.
        self._full_year(
            self.class10,
            'LP',
            {
                self.t1: {ana: (8, 12), bento: (8, 8)},
                self.t2: {ana: (14, 14), bento: (9, 9)},
                self.t3: {ana: (18, 18), bento: (8, 8)},
            },
            pg=False,
        )
        self.assertEqual(self._term(enrollments[0], 'LP', self.t1).mt, 10)
        result = self._year_subject(enrollments[0], 'LP')
        # CF cumulativa 10 → 12 → 15 (a média seria 14).
        self.assertEqual(result.cf, 15)
        self.assertTrue(result.has_global_exam)  # LP com 4 tempos semanais
        self._assess(self.class10, 'LP', self.t3, 'global_exam', {ana: 16, bento: 9})
        result = self._year_subject(enrollments[0], 'LP')
        self.assertEqual((result.pg, result.annual), (16, 15))  # 0,6 × 15 + 0,4 × 16 = 15,4
        bento_result = self._year_subject(enrollments[1], 'LP')
        # CT 8, 9, 8: 8 → (8 + 9)/2 = 8,5 ≈ 9 → (9 + 8)/2 = 8,5 ≈ 9; CA = 0,6 × 9 + 0,4 × 9 = 9.
        self.assertEqual((bento_result.cf, bento_result.annual), (9, 9))
        # Caso limite: o professor bonifica +1 (9 → 10).
        self.assertTrue(bento_result.borderline)
        bento_result.action_grant_one()
        self.assertEqual((bento_result.final, bento_result.passed), (10, True))
        with self.assertRaises(UserError):
            result.action_grant_one()  # 15 não é caso limite
        # Falta injustificada à prova global vale 0.
        global_exam = self.env['edu.assessment'].search([('assessment_type', '=', 'global_exam')])
        global_exam.grade_ids.filtered(lambda g: g.student_id == ana).absent = True
        self.assertEqual(self._year_subject(enrollments[0], 'LP').pg, 0)
        # CF importada da pauta assinada vence a recomposição.
        result.write({'has_imported_cf': True, 'imported_cf': 17})
        result._recompute()
        self.assertEqual(result.cf, 17)
        # Prova global recusada numa disciplina sem prova global.
        practical = self.class10.subject_line_ids.filtered(lambda line: not line.has_global_exam)[:1]
        with self.assertRaises(ValidationError):
            self.env['edu.assessment'].create(
                {
                    'name': 'PG',
                    'class_id': self.class10.id,
                    'subject_id': practical.subject_id.id,
                    'trimester_id': self.t3.id,
                    'assessment_type': 'global_exam',
                }  # fmt: skip
            )
        # A marca da prova global é da escola: mudar os tempos da linha não a apaga nem a cria.
        lp_line = self.class10.subject_line_ids.filtered(lambda line: line.code == 'LP')
        lp_line.weekly_hours = 2
        self.assertTrue(lp_line.has_global_exam)
        practical.weekly_hours = 5
        self.assertFalse(practical.has_global_exam)

    def test_technical_last_trimester_npp_only(self):
        """No técnico, o último trimestre só tem a NPP (CF = (CT2 + NPP3)/2, como nas cadernetas e no resumo do regime);
        a prova do fim do ano é a prova global."""
        ana = self.students[0]
        enrollment = self._enroll(self.class10, ana, ['LP'])
        self._full_year(
            self.class10, 'LP', {self.t1: {ana: (10, 12)}, self.t2: {ana: (14, 14)}, self.t3: {ana: (16, 9)}}
        )
        # CT1 = 11; CT2 = (11 + 14)/2 = 12,5 ≈ 13; CT3 = CF = (13 + 16)/2 = 14,5 ≈ 15; a PG é 9.
        self.assertEqual(self._term(enrollment, 'LP', self.t3).mt, 16)
        result = self._year_subject(enrollment, 'LP')
        self.assertEqual((result.cf, result.pg, result.annual), (15, 9, 13))  # 0,6 × 15 + 0,4 × 9 = 12,6
        with self.assertRaises(ValidationError):
            self._assess(self.class10, 'LP', self.t3, 'trimester_test', {ana: 12})

    def test_review_fixes(self):
        """Revisão: CA = CF sem PG mesmo com o arredondamento único; MT3 da classe de exame com um trimestre em falta
        (conta 0); o CT acumulado do termo; nenhuma NPT no último trimestre do técnico pela grelha."""
        ana, bento = self.students[:2]
        # Disciplina do técnico sem prova global, com o arredondamento único (escolas migradas).
        practical = self.class10.subject_line_ids.filtered(lambda line: not line.has_global_exam)[:1]
        code = practical.subject_id.code
        enrollment = self._enroll(self.class10, ana, [code])
        policy = self.env['edu.evaluation.policy']._get(self.env.company, self.class10.level_id)
        policy.technical_ca_precise = True
        self._full_year(
            self.class10, code, {self.t1: {ana: (10, 10)}, self.t2: {ana: (11, 11)}, self.t3: {ana: (10, 0)}}
        )
        result = self._year_subject(enrollment, code)
        # CF: 10 → 10,5 ≈ 11 → 10,5 ≈ 11; sem arredondar seria 10,25 (CA 10, diferente da CF).
        self.assertEqual((result.cf, result.annual), (11, 11))
        self.assertEqual(result._trimester_classifications(), [10, 11, 11])
        policy.technical_ca_precise = False
        # Classe de exame do geral: sem MT1, MT3 = (0 + MT2 + MAC3)/3.
        nine = self._enroll(self.class9, bento, ['MAT'])
        self._full_year(self.class9, 'MAT', {self.t2: {bento: (12, 12)}})
        self._assess(self.class9, 'MAT', self.t3, 'continuous', {bento: 14})
        self.assertEqual(self._term(nine, 'MAT', self.t3).mt, 9)  # 26 / 3 = 8,67
        # A grelha não grava uma NPT no último trimestre do técnico.
        self.t3.is_current = True
        teacher = self.class10.assignment_ids.filtered(lambda a: a.subject_id == practical.subject_id)[:1].teacher_id
        if teacher.user_id:
            Grid = self.env['edu.grade.grid'].with_user(teacher.user_id)
            change = {'enrollment_id': enrollment.id, 'trimester_id': self.t3.id, 'column': 'npt', 'value': 12}
            done = Grid.grid_save(self.class10.id, practical.subject_id.id, [change])
            self.assertFalse(done['ok'])

    def test_technical_missing_trimester(self):
        """A CF fecha com o último trimestre e um trimestre sem classificação conta 0 (Despacho 60/08, art. 16.º): sem o
        3.º espera pela prova extraordinária; sem classificação em dois trimestres, sem aproveitamento."""
        ana, bento, carla = self.students[:3]
        enrollments = self._enroll(self.class10, (ana, bento, carla), ['LP'])
        self._full_year(
            self.class10,
            'LP',
            {
                self.t1: {ana: (10, 10), carla: (12, 12)},
                self.t2: {carla: (12, 12)},
                self.t3: {ana: (14, 14), bento: (16, 16)},
            },
            pg=False,
        )
        self._assess(self.class10, 'LP', self.t3, 'global_exam', {ana: 10, bento: 16, carla: 12})
        ana_result, bento_result, carla_result = (self._year_subject(e, 'LP') for e in enrollments)
        # O 2.º sem classificação conta 0: CT2 = (10 + 0)/2 = 5; CF = (5 + 14)/2 = 9,5 ≈ 10; CA = 0,6 × 10 + 0,4 × 10.
        self.assertEqual((ana_result.cf, ana_result.annual, ana_result.complete), (10, 10, True))
        self.assertTrue(ana_result.passed)
        # Só o 3.º: 0 → 0 → 8; CA = 0,6 × 8 + 0,4 × 16 = 11,2 ≈ 11, mas sem aproveitamento (dois trimestres sem
        # classificação).
        self.assertEqual((bento_result.cf, bento_result.annual), (8, 11))
        self.assertEqual((bento_result.complete, bento_result.passed), (True, False))
        # Sem o 3.º: a disciplina fica por fechar.
        self.assertFalse(carla_result.complete)

    def test_technical_imported(self):
        """Pauta migrada: médias trimestrais importadas não se recalculam e, com o arredondamento único, a PG entra
        na CA com as casas decimais."""
        ana = self.students[0]
        enrollment = self._enroll(self.class10, ana, ['LP'])
        policy = self.env['edu.evaluation.policy']._get(self.env.company, self.class10.level_id)
        policy.technical_ca_precise = True
        subject = self._subject(self.class10, 'LP')
        terms = self.env['edu.term.result'].create(
            [
                {
                    'enrollment_id': enrollment.id,
                    'subject_id': subject.id,
                    'trimester_id': trimester.id,
                    'mt': mt,
                    'has_mt': True,
                    'imported': True,
                }
                for trimester, mt in ((self.t1, 10.5), (self.t2, 10.75), (self.t3, 11))
            ]
        )
        self.env['edu.subject.result'].create(
            {'enrollment_id': enrollment.id, 'subject_id': subject.id, 'has_imported_cf': True, 'imported_cf': 11}
        )
        self._assess(self.class10, 'LP', self.t3, 'global_exam', {ana: 12.4})
        self.assertEqual(terms.mapped('mt'), [10.5, 10.75, 11])
        result = self._year_subject(enrollment, 'LP')
        # 0,6 × 11 + 0,4 × 12,4 = 11,56 → 12 (com a PG arredondada antes: 0,6 × 11 + 0,4 × 12 = 11,4 → 11).
        self.assertEqual((result.mt2, result.pg, result.annual, result.complete), (10.75, 12.4, 12, True))
        policy.technical_ca_precise = False
        result._recompute()
        self.assertEqual(result.annual, 11)

    def test_technical_transition_rules(self):
        """Despacho 60/08, art. 30.º: as negativas das disciplinas terminais da classe anterior contam para o máximo
        de duas; Resumo do regime, IV.7: sem classificação em dois trimestres, sem aproveitamento."""
        ana = self.students[0]
        self.next_year.action_generate_trimesters()
        class11 = self._class(self.tec, 11, year=self.next_year)
        lines = self.tec.curriculum_id.line_ids

        def span(subject):
            return set(lines.filtered(lambda line: line.subject_id == subject).mapped('year_id.class_number'))

        only10 = self.class10.subject_line_ids.subject_id.filtered(lambda s: span(s) == {10})[:1]
        self.assertTrue(only10, 'o plano de Enfermagem tem disciplinas só da 10.ª')

        def grade(enrollment, scores):
            Result = self.env['edu.subject.result']
            for subject in enrollment.subject_ids:
                result = Result.search([('enrollment_id', '=', enrollment.id), ('subject_id', '=', subject.id)])
                vals = {'has_imported_cf': True, 'imported_cf': scores.get(subject, 12)}
                result = result or Result.create({'enrollment_id': enrollment.id, 'subject_id': subject.id})
                result.write(vals)
                result._recompute()

        e10 = self._enroll(self.class10, ana, self.class10.subject_line_ids.subject_id.mapped('code'))
        grade(e10, {only10: 8})
        self.env['edu.year.result'].create({'enrollment_id': e10.id, 'status': 'conditional', 'manual': True})
        e11 = self._enroll(class11, ana, class11.subject_line_ids.subject_id.mapped('code'))
        first, second = e11.subject_ids[:2]
        grade(e11, {first: 9})
        result = self.env['edu.year.result']._compute_for_classes(class11)
        # Uma negativa da 11.ª mais a da disciplina terminal da 10.ª: duas, transita com disciplinas em atraso.
        self.assertEqual((result.status, result.negative_count), ('conditional', 2))
        grade(e11, {first: 9, second: 3})
        result.action_recompute()
        # Três negativas (sem nota mínima no técnico): recurso.
        self.assertEqual((result.status, result.negative_count), ('exam', 3))
        # Sem classificação em dois trimestres, depois de fechado o ano: sem aproveitamento.
        grade(e11, {})
        missing = self.env['edu.subject.result'].search([('enrollment_id', '=', e11.id), ('subject_id', '=', first.id)])
        missing.write({'has_imported_cf': False})
        result.action_recompute()
        self.assertEqual(result.status, 'pending')
        self.next_year.trimester_ids.sorted('number')[-1].state = 'closed'
        result.action_recompute()
        self.assertEqual((result.status, result.reason), ('retained', 'Sem classificação em dois trimestres'))

    def test_council_vote(self):
        ana = self.students[0]
        self._enroll(self.class10, ana, ['LP'])
        lp = self._subject(self.class10, 'LP')
        other = self.env['hr.employee'].create({'name': 'Outro Professor', 'edu_is_teacher': True})
        director = self.env['hr.employee'].create({'name': 'Joana Directora', 'edu_is_teacher': True})
        bio = self._subject(self.class10, 'BIO')
        self.env['edu.teaching.assignment'].create([
            {'class_id': self.class10.id, 'subject_id': lp.id, 'teacher_id': self.teacher.id},
            {'class_id': self.class10.id, 'subject_id': bio.id, 'teacher_id': other.id},
        ])  # fmt: skip
        self.class10.director_id = director
        self._full_year(self.class10, 'LP', dict.fromkeys((self.t1, self.t2, self.t3), {ana: (9, 9)}))
        result = self.env['edu.subject.result'].search([('student_id', '=', ana.id)])
        self.assertTrue(result.borderline)
        action = result.action_council_vote()
        vote = self.env['edu.council.vote'].browse(action['res_id'])
        vote.cast(self.teacher, True)
        with self.assertRaises(UserError):
            vote.cast(self.env['hr.employee'].create({'name': 'Estranho', 'edu_is_teacher': True}), True)
        vote.action_close()  # 1 de 2 professores votou: quórum de 50% cumprido
        self.assertEqual(vote.state, 'applied')
        self.assertEqual((result.council_points, result.final), (2, 11))
        session = vote.session_id
        session.action_realize()
        self.assertEqual(session.state, 'realized')
        with self.assertRaises(UserError):
            result.action_remove_points()
        self.assertEqual(result.enrollment_id.year_result_id.status, 'promoted')

    def test_grade_entry_window(self):
        ana = self.students[0]
        self._enroll(self.class7, ana, ['LP'])
        lp = self._subject(self.class7, 'LP')
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class7.id, 'subject_id': lp.id, 'teacher_id': self.teacher.id}
        )
        # O professor lança no trimestre em curso.
        assessment = self._assess(self.class7, 'LP', self.t1, 'continuous', {ana: 12}, user=self.teacher_user)
        self.assertEqual(assessment.graded_count, 1)
        # Noutro trimestre precisa de autorização.
        with self.assertRaises(AccessError):
            self._assess(self.class7, 'LP', self.t2, 'continuous', {ana: 12}, user=self.teacher_user)
        permission = self.env['edu.grade.edit.permission'].create(
            {
                'teacher_id': self.teacher.id,
                'class_id': self.class7.id,
                'subject_id': lp.id,
                'trimester_id': self.t2.id,
                'reason': 'Lançamento em atraso',
                'date_expiry': fields.Datetime.now() + timedelta(days=5),
            }
        )
        self._assess(self.class7, 'LP', self.t2, 'continuous', {ana: 13}, user=self.teacher_user)
        again = self.env['edu.grade.edit.permission'].create(
            {
                'teacher_id': self.teacher.id,
                'class_id': self.class7.id,
                'subject_id': lp.id,
                'trimester_id': self.t2.id,
                'reason': 'Renovação do prazo',
                'date_expiry': fields.Datetime.now() + timedelta(days=10),
            }
        )
        self.assertEqual(again, permission)
        with self.assertRaises(ValidationError):
            permission.date_expiry = fields.Datetime.now() + timedelta(days=45)
        with self.assertRaises(ValidationError):
            self.env['edu.grade.edit.permission'].create(
                {
                    'teacher_id': self.teacher.id,
                    'class_id': self.class7.id,
                    'subject_id': lp.id,
                    'trimester_id': self.t1.id,
                    'reason': 'Trimestre corrente',
                }  # fmt: skip
            )
        # Trimestre fechado: só por reapreciação.
        self.t1.action_close()
        grade = assessment.grade_ids
        with self.assertRaises(UserError):
            grade.score = 15
        appeal = self.env['edu.grade.appeal'].create({'grade_id': grade.id, 'reason': 'Erro de soma'})
        self.assertEqual(appeal.original_score, 12)
        with self.assertRaises(ValidationError):
            self.env['edu.grade.appeal'].create({'grade_id': grade.id, 'reason': 'Outro pedido'})
        appeal.action_admit()
        appeal.new_score = 15
        appeal.action_grant()
        self.assertEqual(grade.score, 15)

    def test_absence_exclusion_and_preschool(self):
        ana = self.students[0]
        enrollment = self._enroll(self.class7, ana, ['LP'])
        self._full_year(self.class7, 'LP', dict.fromkeys((self.t1, self.t2, self.t3), {ana: (15, 15)}))
        lp = self._subject(self.class7, 'LP')
        hours = self.class7._edu_weekly_hours(lp)
        limit = 3 if hours == 1 else 4 if hours == 2 else 5
        for offset in range(limit):
            lesson = self.env['edu.lesson'].create(
                {'class_id': self.class7.id, 'subject_id': lp.id, 'date': date(2026, 9, 7) + timedelta(days=offset)}
            )
            lesson.action_open_roll_call()
            lesson.attendance_ids.state = 'absent'
            lesson.summary = 'Matéria dada'
            lesson.action_done()
        self.class7.action_compute_year_results()
        result = enrollment.year_result_id
        self.assertEqual((result.status, result.absence_excluded), ('retained', True))
        with self.assertRaises(ValidationError):
            initiation = self._course('Iniciação', 'INI', 'level_iniciacao', None)
            edu_class = self.env['edu.class'].create({'name': 'A', 'course_id': initiation.id, 'class_number': 0})
            self.env['edu.assessment'].create(
                {'name': 'Teste', 'class_id': edu_class.id, 'subject_id': lp.id, 'trimester_id': self.t1.id}
            )

    def test_rdec(self):
        """RDEC da iniciação, como no secPed: um relatório por criança e trimestre, criado ao abrir a turma com as áreas
        (as disciplinas da matrícula); o estado segue o que está avaliado; só o(a) educador(a), director(a) da turma,
        escreve; as faltas são as do trimestre."""
        initiation = self._course('Iniciação', 'INI', 'level_iniciacao', None)
        subjects = self.env['edu.subject'].create(
            [{'name': 'Linguagem', 'code': 'LIN'}, {'name': 'Expressão Plástica', 'code': 'EXP'}]
        )
        curriculum = self.env['edu.curriculum'].create(
            {'name': 'Plano — Iniciação', 'course_id': initiation.id, 'level_id': initiation.level_id.id}
        )
        year_line = self.env['edu.curriculum.year'].create(
            {
                'curriculum_id': curriculum.id,
                'year': 1,
                'class_number': 0,
                'line_ids': [Command.create({'subject_id': s.id, 'weekly_hours': 3}) for s in subjects],
            }
        )
        edu_class = self.env['edu.class'].create(
            {
                'name': 'A',
                'course_id': initiation.id,
                'class_number': 0,
                'curriculum_id': curriculum.id,
                'curriculum_year_id': year_line.id,
                'academic_year_id': self.year.id,
            }
        )
        self.assertEqual(edu_class.complete_name, 'Iniciação A · INI · 2026/2027')
        ana, bento = self.students[:2]
        enrollments = self._enroll(edu_class, ana | bento, ['LIN', 'EXP'])
        edu_class.director_id = self.teacher
        other_user = self.env['res.users'].create(
            {
                'name': 'Outro',
                'login': 'outro_prof',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        other = self.env['hr.employee'].create({'name': 'Outro', 'edu_is_teacher': True, 'user_id': other_user.id})
        self.env['edu.teaching.assignment'].create(
            {'class_id': edu_class.id, 'subject_id': subjects[0].id, 'teacher_id': other.id}
        )

        # Abrir a turma (pelo menu ou pela grelha de notas) cria os relatórios do trimestre, com as áreas.
        Rdec = self.env['edu.rdec']
        action = Rdec.with_user(self.teacher_user).action_open_rdec()
        self.assertEqual(action['context']['searchpanel_default_class_id'], edu_class.id)
        trimester = self.env['edu.trimester'].browse(action['context']['searchpanel_default_trimester_id'])
        reports = Rdec.search([('class_id', '=', edu_class.id), ('trimester_id', '=', trimester.id)])
        self.assertEqual(reports.enrollment_id, enrollments)
        report = reports.filtered(lambda r: r.student_id == ana)
        self.assertEqual(report.line_ids.subject_id.mapped('name'), ['Expressão Plástica', 'Linguagem'])
        self.assertEqual((report.state, report.areas_label), ('todo', '0/2'))
        grid = self.env['edu.grade.grid'].with_user(self.teacher_user).class_link_action(edu_class.id, 'rdec')
        self.assertEqual(grid['domain'], [('class_id', 'in', edu_class.ids)])
        self.assertEqual(Rdec.search_count([('class_id', '=', edu_class.id)]), 2)
        # Na grelha de notas, a turma da iniciação não tem notas, mini-pauta nem conselho de turma: o RDEC.
        self.assertEqual(edu_class._editor_label(), 'Iniciação A · INI')
        row = next(
            c
            for c in self.env['edu.grade.grid'].with_user(self.teacher_user).grid_classes()['classes']
            if c['id'] == edu_class.id
        )
        self.assertTrue(row['preschool'])
        keys = [link['key'] for link in row['links']]
        self.assertIn('rdec', keys)
        self.assertFalse({'council', 'mini_pauta'} & set(keys))

        # O(a) educador(a) escreve; o outro professor da turma só lê.
        mine = report.with_user(self.teacher_user)
        self.assertTrue(mine.can_edit)
        mine.line_ids[0].level = 'good'
        self.assertEqual((report.state, report.areas_label), ('progress', '1/2'))
        mine.line_ids[1].write({'level': 'very_good', 'observations': 'Desenha com gosto.'})
        mine.appreciation = 'Criança participativa e curiosa.'
        self.assertEqual((report.state, report.progress), ('done', 100.0))
        theirs = report.with_user(other_user)
        self.assertFalse(theirs.can_edit)
        self.assertEqual(theirs.appreciation, 'Criança participativa e curiosa.')
        with self.assertRaises(AccessError):
            theirs.appreciation = 'Outra coisa'
        with self.assertRaises(AccessError):
            theirs.line_ids[0].level = 'satisfactory'
        # A secretaria consulta e imprime, mas não escreve; a Direcção pode corrigir.
        secretary = self.env['res.users'].create(
            {'name': 'Secretaria', 'login': 'secretaria_rdec',
             'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])]}
        )  # fmt: skip
        # O menu corre como acção de servidor: a secretaria, sem escrita no RDEC, também o abre.
        menu = self.env.ref('edu_evaluation.action_edu_rdec_open').with_user(secretary).run()
        self.assertEqual(menu['res_model'], 'edu.rdec')
        desk = report.with_user(secretary)
        self.assertFalse(desk.can_edit)
        self.assertEqual(desk.state, 'done')
        with self.assertRaises(AccessError):
            desk.appreciation = 'Outra coisa'
        direction = self.env['res.users'].create(
            {'name': 'Direcção', 'login': 'direccao_rdec',
             'group_ids': [Command.set([self.env.ref('edu_core.group_edu_manager').id])]}
        )  # fmt: skip
        self.assertTrue(report.with_user(direction).can_edit)
        report.with_user(direction).line_ids[0].observations = 'Revisto pela Direcção.'

        # As faltas do trimestre: justificadas e injustificadas, nas aulas dadas.
        lesson = self.env['edu.lesson'].create(
            {'class_id': edu_class.id, 'subject_id': subjects[0].id, 'date': trimester.date_start + timedelta(days=7)}
        )
        lesson.action_open_roll_call()
        lesson.attendance_ids.filtered(lambda a: a.student_id == ana).write(
            {'state': 'excused', 'justification': 'Doença'}
        )
        lesson.attendance_ids.filtered(lambda a: a.student_id == bento).state = 'absent'
        lesson.summary = 'Cores e formas'
        lesson.action_done()
        report.invalidate_recordset(['absences_justified', 'absences_unjustified'])
        self.assertEqual((report.absences_justified, report.absences_unjustified), (1, 0))
        other_report = reports - report
        self.assertEqual((other_report.absences_justified, other_report.absences_unjustified), (0, 1))

        # Fora da iniciação não há RDEC.
        seventh = self._enroll(self.class7, self.students[2], ['LP'])
        with self.assertRaises(ValidationError):
            Rdec.create({'enrollment_id': seventh.id, 'trimester_id': self.t1.id})

    def test_enrollment_confirmation(self):
        """Confirmação de matrículas pela escola: fecha o ano pelo resultado, cria as turmas do ano seguinte e
        confirma cada aluno na classe que lhe cabe; quem não pode fica pendente ou de fora, com o motivo."""
        ana, bento, carla, domingos = self.students
        enrollments = {}
        for student in self.students:
            enrollments[student] = self.env['edu.enrollment'].create(
                {'student_id': student.id, 'class_id': self.class10.id}
            )
            enrollments[student].action_confirm()
        nono = self.env['edu.student'].create({'name': 'Eva'})
        ninth = self.env['edu.enrollment'].create({'student_id': nono.id, 'class_id': self.class9.id})
        ninth.action_confirm()
        Result = self.env['edu.year.result']
        Result.create({'enrollment_id': enrollments[ana].id, 'status': 'promoted'})
        Result.create({'enrollment_id': enrollments[bento].id, 'status': 'retained'})
        Result.create({'enrollment_id': enrollments[carla].id, 'status': 'retained', 'absence_excluded': True})
        Result.create({'enrollment_id': ninth.id, 'status': 'promoted'})
        wizard = self.env['edu.enrollment.confirmation'].create(
            {'source_year_id': self.year.id, 'target_year_id': self.next_year.id}
        )
        wizard.action_prepare()
        # Matrículas fechadas pelo resultado; a de quem ainda não tem resultado fica em aberto.
        self.assertEqual(enrollments[ana].state, 'completed')
        self.assertEqual(enrollments[bento].state, 'retained')
        self.assertEqual(enrollments[domingos].state, 'active')
        # Turmas do ano seguinte: a 11.ª A (classe seguinte) e a 10.ª A (entrada e repetentes).
        new_classes = self.env['edu.class'].search([('academic_year_id', '=', self.next_year.id)])
        self.assertIn((11, 'ENF'), [(c.class_number, c.course_id.code) for c in new_classes])
        self.assertIn((10, 'ENF'), [(c.class_number, c.course_id.code) for c in new_classes])
        lines = {line.student_id: line for line in wizard.line_ids}
        self.assertEqual((lines[ana].state, lines[ana].target_class_id.class_number), ('confirm', 11))
        self.assertEqual((lines[bento].state, lines[bento].target_class_id.class_number), ('confirm', 10))
        self.assertEqual(lines[carla].state, 'excluded')
        self.assertIn('art. 24.º, n.º 4', lines[carla].reason)
        self.assertEqual(lines[domingos].state, 'pending')
        self.assertEqual(lines[nono].state, 'excluded')
        self.assertIn('II Ciclo', lines[nono].reason)
        wizard.action_confirm()
        self.assertEqual(lines[ana].state, 'done')
        self.assertEqual(
            (lines[ana].enrollment_id.enrollment_type, lines[ana].enrollment_id.state), ('renewal', 'active')
        )
        self.assertEqual(lines[bento].enrollment_id.enrollment_type, 'repeat')
        self.assertEqual(lines[domingos].state, 'pending')
        # Depois do resultado, «Tentar de novo» fecha a matrícula e confirma o aluno.
        Result.create({'enrollment_id': enrollments[domingos].id, 'status': 'conditional'})
        lines[domingos].action_retry()
        self.assertEqual((lines[domingos].state, lines[domingos].enrollment_id.class_number), ('done', 11))
        self.assertEqual(enrollments[domingos].state, 'completed')

    def test_despacho_60_08_subjects(self):
        """Técnico (Decreto Executivo n.º 60/08): anulação a uma disciplina (art. 11.º) e disciplina feita numa turma da
        classe anterior (arts. 9.º e 10.º)."""
        ana, bento = self.students[:2]
        class11 = self._class(self.tec, 11)
        shared = (self.class10.subject_line_ids.subject_id & class11.subject_line_ids.subject_id)[:2]
        subject, other = shared[0], shared[1]
        codes = shared.mapped('code')
        ana_enrollment = self._enroll(class11, ana, codes)
        bento_enrollment = self._enroll(class11, bento, codes)
        # Anulação a uma disciplina: sai das notas dessa disciplina e da decisão; as outras seguem.
        self.env['edu.enrollment.subject.drop'].create(
            {'enrollment_id': ana_enrollment.id, 'subject_id': other.id, 'reason': 'Pedido do aluno'}
        )
        Enrollment = self.env['edu.enrollment']
        self.assertNotIn(ana_enrollment, Enrollment._for_class_subject(class11, other))
        self.assertIn(ana_enrollment, Enrollment._for_class_subject(class11, subject))
        # Fora do prazo (5.º dia útil do III trimestre), só a direcção.
        secretary = self.env['res.users'].create(
            {
                'name': 'Sec',
                'login': 'sec_6008',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        late_date = ana_enrollment._drop_deadline() + timedelta(days=1)
        with self.assertRaisesRegex(UserError, 'só a direcção'):
            self.env['edu.enrollment.subject.drop'].with_user(secretary).create(
                {'enrollment_id': bento_enrollment.id, 'subject_id': other.id, 'date': late_date}
            )
        # Só no técnico.
        general = self._enroll(self.class7, self.students[2], ['LP'])
        with self.assertRaises(ValidationError):
            self.env['edu.enrollment.subject.drop'].create(
                {'enrollment_id': general.id, 'subject_id': self._subject(self.class7, 'LP').id}
            )
        # Disciplina na classe anterior: o Bento faz «subject» com a 10.ª.
        self.env['edu.enrollment.lower.subject'].create(
            {'enrollment_id': bento_enrollment.id, 'subject_id': subject.id, 'class_id': self.class10.id}
        )
        self.assertIn(bento_enrollment, Enrollment._for_class_subject(self.class10, subject))
        self.assertNotIn(bento_enrollment, Enrollment._for_class_subject(class11, subject))
        assessment = self.env['edu.assessment'].create(
            {
                'name': 'Teste',
                'class_id': self.class10.id,
                'subject_id': subject.id,
                'trimester_id': self.t1.id,
                'assessment_type': 'continuous',
            }
        )
        assessment.action_fill_students()
        self.assertIn(bento_enrollment, assessment.grade_ids.enrollment_id)
        # E na chamada das aulas dessa disciplina na 10.ª.
        lesson = self.env['edu.lesson'].create(
            {'class_id': self.class10.id, 'subject_id': subject.id, 'date': self.t1.date_start}
        )
        lesson.action_open_roll_call()
        self.assertIn(bento_enrollment, lesson.attendance_ids.enrollment_id)
        # O director da turma do Bento (11.ª) justifica-lhe a falta na aula da 10.ª; o director da 10.ª não.
        bento_line = lesson.attendance_ids.filtered(lambda line: line.enrollment_id == bento_enrollment)
        bento_line.state = 'absent'
        other_director = self.env['hr.employee'].create({'name': 'Director da 10.ª', 'edu_is_teacher': True})
        self.class10.director_id = other_director
        class11.director_id = self.teacher
        bento_line.with_user(self.teacher_user).write({'state': 'excused', 'justification': 'Doença'})
        self.assertEqual(bento_line.state, 'excused')
        bento_line.with_user(self.teacher_user).invalidate_recordset(['can_justify'])
        # Pautas (edu_documents): na 10.ª, o Bento só nessa disciplina; na 11.ª, «e)» e a disciplina anulada «c)».
        if 'edu.pauta.print' not in self.env:
            return
        wizard10 = self.env['edu.pauta.print'].create({'class_id': self.class10.id, 'trimester_id': self.t1.id})
        rows10 = {row['name']: row for row in wizard10._pauta_data()['rows']}
        self.assertEqual(rows10[bento.name]['verdict'][0], 'Da 11ª classe')
        wizard11 = self.env['edu.pauta.print'].create({'class_id': class11.id, 'trimester_id': self.t1.id})
        rows11 = {row['name']: row for row in wizard11._pauta_data()['rows']}
        self.assertEqual(rows11[bento.name]['cells'][subject.id][0][0], 'e)')
        self.assertEqual(rows11[ana.name]['cells'][other.id][0][0], 'c)')

    def test_lower_subject_proposal(self):
        """Na confirmação, a disciplina de continuação com 6 ou menos passa para uma turma da classe anterior."""
        ana = self.students[0]
        class11 = self._class(self.tec, 11, year=self.next_year)
        self._class(self.tec, 10, year=self.next_year)
        subject = (self.class10.subject_line_ids.subject_id & class11.subject_line_ids.subject_id)[:1]
        enrollment = self._enroll(self.class10, ana, subject.mapped('code'))
        self.env['edu.subject.result'].create(
            {'enrollment_id': enrollment.id, 'subject_id': subject.id, 'final': 6, 'complete': True}
        )
        self.env['edu.year.result'].create({'enrollment_id': enrollment.id, 'status': 'promoted'})
        wizard = self.env['edu.enrollment.confirmation'].create(
            {'source_year_id': self.year.id, 'target_year_id': self.next_year.id, 'create_classes': False}
        )
        wizard.action_prepare()
        wizard.action_confirm()
        line = wizard.line_ids.filtered(lambda line: line.student_id == ana)
        self.assertEqual(line.state, 'done')
        lower = line.enrollment_id.lower_subject_ids
        self.assertEqual((lower.subject_id, lower.class_id.class_number), (subject, 10))
        self.assertIn('classe anterior', line.reason)

    def test_audit_completeness_and_cfd(self):
        """Auditoria da fase 5: sem EN (classe de exame) ou sem PG (técnico) não há classificação; a CFD só conta as
        classes do mesmo nível, uma vez cada (o ano repetido substitui o anterior)."""
        ana, bento = self.students[:2]
        # 9.ª com exame nacional a MAT: sem o EN, a disciplina fica por completar e o ano pendente.
        ninth = self._enroll(self.class9, ana, ['MAT'])
        self._subject(self.class9, 'MAT').is_national_exam = True
        self._full_year(self.class9, 'MAT', dict.fromkeys((self.t1, self.t2, self.t3), {ana: (14, 14)}))
        self.assertFalse(self._year_subject(ninth, 'MAT').complete)
        self.class9.action_compute_year_results()
        self.assertEqual(ninth.year_result_id.status, 'pending')
        self._assess(self.class9, 'MAT', self.t3, 'national_exam', {ana: 12})
        self.assertTrue(self._year_subject(ninth, 'MAT').complete)
        # Técnico sem PG: incompleta.
        tenth = self._enroll(self.class10, bento, ['LP'])
        self._full_year(self.class10, 'LP', dict.fromkeys((self.t1, self.t2, self.t3), {bento: (12, 12)}), pg=False)
        self.assertFalse(self._year_subject(tenth, 'LP').complete)
        # CFD da AFH (10.ª e 11.ª): 10.ª com 4 (retido), 10.ª repetida com 14, 11.ª com 10 → (14 + 10) / 2 = 12.
        older = self.env['edu.academic.year'].create(
            {'name': '2024/2025', 'date_start': date(2024, 9, 1), 'date_end': date(2025, 7, 31)}
        )
        last = self.env['edu.academic.year'].create(
            {'name': '2025/2026', 'date_start': date(2025, 9, 1), 'date_end': date(2026, 7, 31)}
        )
        (older | last).action_generate_trimesters()
        carla = self.students[2]
        first = self._class(self.tec, 10, year=older, name='R')
        repeat = self._class(self.tec, 10, year=last, name='R')
        eleventh = self._class(self.tec, 11, name='R')
        for edu_class, score, state in ((first, 4, 'retained'), (repeat, 14, 'completed'), (eleventh, 10, None)):
            enrollment = self._enroll(edu_class, carla, ['AFH'])
            trimesters = edu_class.academic_year_id.trimester_ids.sorted('number')
            self._full_year(edu_class, 'AFH', dict.fromkeys(trimesters, {carla: (score, score)}))
            if state:
                enrollment.state = state
        result = self._year_subject(enrollment, 'AFH')
        self.assertEqual((result.final, result.cfd, result.transition_grade), (10, 12, 12))

    def test_audit_decisions_follow_grades(self):
        """Depois dos exames, de uma reapreciação ou de uma decisão manual, a decisão e a confirmação acompanham."""
        ana, bento, carla, domingos = self.students
        # Técnico: 3 negativas → exame; passa em 2 e chumba 1 → transita com 1 em atraso (como «Recalcular»).
        enrollment = self._enroll(self.class10, ana, ['LP', 'MAT', 'ING', 'FIL'])
        for code in ('LP', 'MAT', 'ING'):
            self._full_year(self.class10, code, dict.fromkeys((self.t1, self.t2, self.t3), {ana: (8, 8)}))
        self._full_year(self.class10, 'FIL', dict.fromkeys((self.t1, self.t2, self.t3), {ana: (14, 14)}))
        self.class10.action_compute_year_results()
        result = enrollment.year_result_id
        self.assertEqual(result.status, 'exam')
        for requirement, score in zip(result.requirement_ids, (12, 12, 5), strict=True):
            requirement.score = score
            requirement.action_record()
        self.assertEqual(result.status, 'conditional')
        result.action_recompute()
        self.assertEqual(result.status, 'conditional')
        # Reapreciação deferida depois da decisão: a decisão acompanha a nota.
        seventh = self._enroll(self.class7, bento, ['LP'])
        self._full_year(self.class7, 'LP', dict.fromkeys((self.t1, self.t2, self.t3), {bento: (14, 14)}))
        self.class7.action_compute_year_results()
        self.assertEqual(seventh.year_result_id.status, 'promoted')
        grades = self.env['edu.grade'].search([('enrollment_id', '=', seventh.id)])
        # A reapreciação é de pautas afixadas: os trimestres encerram primeiro.
        for trimester in (self.t1, self.t2, self.t3):
            trimester.action_close()
        for grade in grades:
            appeal = self.env['edu.grade.appeal'].create({'grade_id': grade.id, 'reason': 'Erro de soma'})
            appeal.action_admit()
            appeal.new_score = 2
            appeal.action_grant()
        self.assertEqual(seventh.year_result_id.status, 'retained')
        # Decisão manual depois do fecho: a matrícula e a confirmação seguem-na.
        seventh._edu_close_year()
        self.assertEqual(seventh.state, 'retained')
        seventh.year_result_id.action_manual_promote()
        self.assertEqual(seventh.state, 'completed')
        wizard = self.env['edu.enrollment.confirmation'].create(
            {'source_year_id': self.year.id, 'target_year_id': self.next_year.id, 'create_classes': False}
        )
        self.assertIn('8ª classe', wizard._proposal(seventh)['reason'])

    def test_council_board(self):
        """Ecrã do conselho, como no secPed: iniciar, várias votações, voto de cada professor, quórum, encerrar."""
        ana, bento = self.students[:2]
        self._enroll(self.class10, (ana, bento), ['LP'])
        lp = self._subject(self.class10, 'LP')
        director_user = self.env['res.users'].create(
            {
                'name': 'Joana Directora',
                'login': 'joana_dir',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        director = self.env['hr.employee'].create(
            {'name': 'Joana Directora', 'edu_is_teacher': True, 'user_id': director_user.id}
        )
        bio = self._subject(self.class10, 'BIO')
        self.env['edu.teaching.assignment'].create([
            {'class_id': self.class10.id, 'subject_id': lp.id, 'teacher_id': self.teacher.id},
            {'class_id': self.class10.id, 'subject_id': bio.id, 'teacher_id': director.id},
        ])  # fmt: skip
        self.class10.director_id = director
        self._full_year(self.class10, 'LP', dict.fromkeys((self.t1, self.t2, self.t3), {ana: (9, 9), bento: (8, 8)}))
        Session = self.env['edu.council.session']
        # O professor só vê as suas disciplinas e espera que o director inicie.
        data = Session.with_user(self.teacher_user).board_for_class(self.class10.id)
        self.assertEqual(data['session']['state'], 'draft')
        self.assertEqual([s['name'] for s in data['subjects']], [lp.name])
        session = Session.browse(data['session']['id'])
        with self.assertRaisesRegex(UserError, 'director'):
            session.with_user(self.teacher_user).board_start()
        board = session.with_user(director_user)
        data = board.board_start()
        self.assertEqual(data['session']['state'], 'open')
        self.assertTrue(data['is_director'])
        # Duas votações abertas ao mesmo tempo (uma por nota).
        results = self.env['edu.subject.result'].search(
            [('class_id', '=', self.class10.id), ('subject_id', '=', lp.id)]
        )
        for result in results:
            board.board_open_vote(result.id)
        with self.assertRaisesRegex(UserError, 'aberta para esta nota'):
            board.board_open_vote(results[0].id)
        data = board.board_data()
        self.assertEqual(len(data['votes']), 2)
        first, second = data['votes']
        # Técnico: quórum de metade dos 2 professores = 1; ninguém votou ainda.
        with self.assertRaisesRegex(UserError, 'Quórum não atingido'):
            board.board_close_vote(first['id'])
        session.with_user(self.teacher_user).board_cast(first['id'], True)
        data = board.board_cast(first['id'], True)
        self.assertEqual(data['votes'][0]['my_ballot'], 'favor')
        closed = board.board_close_vote(first['id'])
        self.assertIn('Aprovado (2/2)', closed['message'])
        board.board_cast(second['id'], False)
        self.assertIn('Não aprovado', board.board_close_vote(second['id'])['message'])
        # A secretaria só consulta: não sobe pontos.
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretária',
                'login': 'sec_board',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        with self.assertRaisesRegex(UserError, 'professor da disciplina'):
            results.with_user(clerk).action_grant_two()
        board.board_realize()
        self.assertEqual(session.state, 'realized')
        with self.assertRaisesRegex(UserError, 'encerrado'):
            session.with_user(self.teacher_user).board_cast(first['id'], True)
        if 'action_print_acta' in dir(session):
            board.action_print_acta()
            html = (
                self.env['ir.actions.report']
                ._render_qweb_html('edu_documents.report_council_acta', session.ids)[0]
                .decode()
            )
            for text in (
                'ACTA DO CONSELHO DE NOTAS',
                'Aproveitamento por disciplina',
                'Notas votadas pelo conselho',
                'Aprovado (+2)',
                'Não aprovado',
                'Assinaturas',
            ):
                self.assertIn(text, html)
            with self.assertRaisesRegex(UserError, 'director de turma'):
                session.with_user(self.teacher_user).action_print_acta()

    def test_audit_appeals_and_rules(self):
        """Reapreciação: sem nova nota não se defere (não grava 0), igual à anterior indefere-se, indeferir exige a
        decisão; uma só prova trimestral por trimestre; decisão manual «transita» numa classe terminal é «concluiu»."""
        ana = self.students[0]
        self._enroll(self.class7, ana, ['LP'])
        test = self._assess(self.class7, 'LP', self.t1, 'trimester_test', {ana: 12})
        with self.assertRaisesRegex(ValidationError, 'já tem esta avaliação'):
            self._assess(self.class7, 'LP', self.t1, 'trimester_test', {ana: 13})
        grade = test.grade_ids
        with self.assertRaisesRegex(ValidationError, 'pauta afixada'):
            self.env['edu.grade.appeal'].create({'grade_id': grade.id, 'reason': 'Erro de soma'})
        self.t1.action_close()
        appeal = self.env['edu.grade.appeal'].create({'grade_id': grade.id, 'reason': 'Erro de soma'})
        with self.assertRaisesRegex(UserError, 'admitida'):
            appeal.action_grant()
        appeal.action_admit()
        with self.assertRaisesRegex(UserError, 'nova nota'):
            appeal.action_grant()
        self.assertEqual(grade.score, 12)
        appeal.new_score = 12
        with self.assertRaisesRegex(UserError, 'indefira'):
            appeal.action_grant()
        with self.assertRaisesRegex(UserError, 'deliberação'):
            appeal.action_deny()
        appeal.decision = 'A nota estava certa.'
        appeal.action_deny()
        self.assertTrue(appeal.decided_date)
        # Classe terminal (13.ª do técnico): transitar à mão é concluir.
        thirteenth = self._class(self.tec, 13)
        enrollment = self._enroll(thirteenth, self.students[1], ['LP'])
        result = self.env['edu.year.result'].create({'enrollment_id': enrollment.id})
        result.action_manual_promote()
        self.assertEqual(result.status, 'graduated')

    def test_grade_grid(self):
        """Notas da turma, como a pauta por disciplina do secPed: o professor vê as suas turmas e disciplinas, lança a
        NPT no lugar (tudo ou nada) e só no trimestre que pode lançar; no técnico, a NPP escreve-se na grelha."""
        ana, bento = self.students[:2]
        enrollments = self._enroll(self.class7, (ana, bento), ['LP', 'MAT'])
        lp = self._subject(self.class7, 'LP')
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class7.id, 'subject_id': lp.id, 'teacher_id': self.teacher.id}
        )
        self._assess(self.class7, 'LP', self.t1, 'continuous', {ana: 12, bento: 8})
        Grid = self.env['edu.grade.grid'].with_user(self.teacher_user)
        self.assertEqual([c['id'] for c in Grid.grid_classes()['classes']], [self.class7.id])
        # Outro ano lectivo: as suas turmas desse ano (aqui, nenhuma).
        other = Grid.grid_classes(self.next_year.id)
        self.assertEqual((other['year_id'], other['classes']), (self.next_year.id, []))
        self.assertIn(self.year.id, [y['id'] for y in other['years']])
        self.assertEqual([s['id'] for s in Grid.grid_subjects(self.class7.id)], [lp.id])
        mat = self._subject(self.class7, 'MAT')
        with self.assertRaises(AccessError):
            Grid.grid_data(self.class7.id, mat.id)

        data = Grid.grid_data(self.class7.id, lp.id)
        t1, t2 = data['trimesters'][:2]
        self.assertTrue(t1['editable'])
        self.assertFalse(t2['editable'])
        self.assertEqual([s['enrollment_id'] for s in data['students']], enrollments.ids)
        self.assertEqual(data['students'][0]['terms'][str(self.t1.id)]['mac'], 12)

        # Uma nota fora da escala anula todo o lote.
        ana_e, bento_e = enrollments
        result = Grid.grid_save(self.class7.id, lp.id, [
            {'enrollment_id': ana_e.id, 'trimester_id': self.t1.id, 'column': 'npt', 'value': 16},
            {'enrollment_id': bento_e.id, 'trimester_id': self.t1.id, 'column': 'npt', 'value': 25},
        ])  # fmt: skip
        self.assertFalse(result['ok'])
        self.assertEqual([e['enrollment_id'] for e in result['errors']], [bento_e.id])
        self.assertFalse(self._term(ana_e, 'LP', self.t1).has_npt)

        result = Grid.grid_save(self.class7.id, lp.id, [
            {'enrollment_id': ana_e.id, 'trimester_id': self.t1.id, 'column': 'npt', 'value': 16},
            {'enrollment_id': bento_e.id, 'trimester_id': self.t1.id, 'column': 'npt', 'absent': True},
        ])  # fmt: skip
        self.assertTrue(result['ok'])
        self.assertEqual(self._term(ana_e, 'LP', self.t1).mt, 14)
        row = result['data']['students'][1]['terms'][str(self.t1.id)]
        self.assertTrue(row['npt_absent'])
        self.assertEqual(
            self.env['edu.assessment'].search_count(
                [('class_id', '=', self.class7.id), ('assessment_type', '=', 'trimester_test')]
            ),
            1,
        )
        # Apagar a nota; noutro trimestre, sem autorização, nada se grava.
        Grid.grid_save(self.class7.id, lp.id, [
            {'enrollment_id': ana_e.id, 'trimester_id': self.t1.id, 'column': 'npt', 'value': None},
        ])  # fmt: skip
        self.assertFalse(self._term(ana_e, 'LP', self.t1).has_npt)
        result = Grid.grid_save(self.class7.id, lp.id, [
            {'enrollment_id': ana_e.id, 'trimester_id': self.t2.id, 'column': 'npt', 'value': 15},
        ])  # fmt: skip
        self.assertFalse(result['ok'])

        # A secretaria consulta mas não edita a pauta.
        data = self.env['edu.grade.grid'].grid_data(self.class7.id, lp.id)
        self.assertFalse(data['can_edit'])
        with self.assertRaises(AccessError):
            self.env['edu.grade.grid'].grid_save(self.class7.id, lp.id, [])

        # Técnico: a NPP e a NPT dão a CT (a média das duas).
        enrollment = self._enroll(self.class10, self.students[2], ['LP'])
        lp10 = self._subject(self.class10, 'LP')
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class10.id, 'subject_id': lp10.id, 'teacher_id': self.teacher.id}
        )
        result = Grid.grid_save(self.class10.id, lp10.id, [
            {'enrollment_id': enrollment.id, 'trimester_id': self.t1.id, 'column': 'npp', 'value': 8},
            {'enrollment_id': enrollment.id, 'trimester_id': self.t1.id, 'column': 'npt', 'value': 12},
        ])  # fmt: skip
        self.assertTrue(result['ok'], result['errors'])
        self.assertEqual(self._term(enrollment, 'LP', self.t1).mt, 10)
        self.assertTrue(result['data']['trimesters'][0]['npp_editable'])

    def test_only_teacher_enters_grades(self):
        """Só o professor da disciplina lança as notas: a secretaria consulta (as notas corrigem-se por reapreciação e
        os exames entram pela sessão). No técnico não há MAC: uma só NPP por trimestre (Despacho 60/08, art. 13.º)."""
        ana = self.students[0]
        self._enroll(self.class7, ana, ['LP'])
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'secretaria_notas',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        with self.assertRaises(AccessError):
            self._assess(self.class7, 'LP', self.t1, 'continuous', {ana: 12}, user=clerk)
        assessment = self._assess(self.class7, 'LP', self.t1, 'continuous', {ana: 12})
        with self.assertRaises(AccessError):
            assessment.grade_ids.with_user(clerk).score = 18
        # O contexto não abre a janela (o cliente controla-o): a reapreciação deferida entra em sudo.
        with self.assertRaises(AccessError):
            assessment.grade_ids.with_user(clerk).with_context(edu_grade_appeal=True, edu_grade_exam=True).score = 13
        self.assertEqual(assessment.grade_ids.score, 12)

        # Técnico: a segunda avaliação contínua do mesmo trimestre é recusada; no geral há várias (a MAC).
        self._enroll(self.class10, self.students[1], ['LP'])
        self._assess(self.class10, 'LP', self.t1, 'continuous', {})
        with self.assertRaisesRegex(ValidationError, 'não há MAC'):
            self._assess(self.class10, 'LP', self.t1, 'continuous', {})
        self._assess(self.class10, 'LP', self.t2, 'continuous', {})
        self._assess(self.class7, 'LP', self.t1, 'continuous', {ana: 14})

    def test_grade_permissions_page(self):
        """Autorizações para alterar notas, como no secPed: formulário guiado (o professor, as turmas e disciplinas que
        dá, os trimestres que se podem autorizar), «Vale até» um dia, situação e revogar (quem e quando)."""
        lp = self._subject(self.class7, 'LP')
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class7.id, 'subject_id': lp.id, 'teacher_id': self.teacher.id}
        )
        Page = self.env['edu.grade.permission.page']
        options = Page.form_options()
        teacher = next(t for t in options['teachers'] if t['id'] == self.teacher.id)
        self.assertEqual([(o['class_id'], o['subject_id']) for o in teacher['options']], [(self.class7.id, lp.id)])
        # Nem o corrente (I) nem os encerrados se autorizam.
        self.assertEqual([t['id'] for t in options['trimesters']], (self.t2 | self.t3).ids)
        # O II passa a ser o corrente e o I fica encerrado: só o III se autoriza.
        self.t1.is_current = False
        self.t2.is_current = True
        self.t1.action_close()
        options = Page.form_options()
        self.assertEqual([t['id'] for t in options['trimesters']], self.t3.ids)

        values = {
            'teacher_id': self.teacher.id,
            'class_id': self.class7.id,
            'subject_id': lp.id,
            'trimester_id': self.t3.id,
            'until': options['max_until'],
            'reason': 'Lançamento em atraso',
        }
        too_late = fields.Date.to_string(fields.Date.from_string(options['max_until']) + timedelta(days=1))
        with self.assertRaises(UserError):
            Page.create_permission({**values, 'until': too_late})
        row = Page.create_permission(values)
        self.assertTrue(row['active'])
        self.assertTrue(row['situation'].startswith('Até '))
        data = Page.permissions(True)
        self.assertEqual((data['active_count'], [r['id'] for r in data['rows']]), (1, [row['id']]))
        # O professor já lança no III trimestre.
        self._assess(self.class7, 'LP', self.t3, 'continuous', {}, user=self.teacher_user)
        row = Page.revoke(row['id'])
        self.assertTrue(row['situation'].startswith('Revogada a '))
        permission = self.env['edu.grade.edit.permission'].browse(row['id'])
        self.assertEqual(permission.revoked_by_id, self.env.user)
        self.assertEqual(Page.permissions(True)['rows'], [])
        self.assertEqual(len(Page.permissions(False)['rows']), 1)
        with self.assertRaises(AccessError):
            self._assess(self.class7, 'LP', self.t3, 'continuous', {}, user=self.teacher_user)

    def test_appeal_law_flow(self):
        """Reapreciação no técnico (Despacho 60/08, art. 15.º): pedido até 3 dias úteis após a afixação (fora de prazo
        indefere-se liminarmente), admissão pela direcção com o conselho extraordinário até 5 dias úteis, sem
        provimento vai ao Conselho Pedagógico, deferido corrige a nota, e o interessado é informado."""
        ana, bento = self.students[:2]
        enrollments = self._enroll(self.class10, (ana, bento), ['LP'])
        lp = self._subject(self.class10, 'LP')
        npt = self._assess(self.class10, 'LP', self.t1, 'trimester_test', {ana: 9, bento: 9})
        self.t1.action_close()
        Appeal = self.env['edu.grade.appeal']
        posted = fields.Date.context_today(Appeal)
        vals = {'enrollment_id': enrollments[0].id, 'subject_id': lp.id, 'trimester_id': self.t1.id}
        appeal = Appeal.create({**vals, 'reason': 'A prova foi mal somada', 'posting_date': posted})
        self.assertEqual(appeal.regime, 'technical')
        self.assertFalse(appeal.late)
        self.assertEqual(appeal.answer_deadline, appeal.request_date + timedelta(days=30))
        with self.assertRaisesRegex(ValidationError, 'em curso'):
            Appeal.create({**vals, 'reason': 'Outro pedido'})
        # A secretaria regista mas não decide.
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'secretaria_reaprec',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        with self.assertRaisesRegex(UserError, 'direcção'):
            appeal.with_user(clerk).action_admit()
        with self.assertRaisesRegex(UserError, 'cinco dias úteis'):
            appeal.action_admit(fields.Date.to_string(posted + timedelta(days=30)))
        appeal.action_admit()
        self.assertEqual(appeal.state, 'review')
        self.assertTrue(appeal.meeting_date)
        # Sem provimento: passa ao Conselho Pedagógico, que defere e corrige a nota.
        appeal.decision = 'O conselho manteve a nota.'
        appeal.action_deny()
        self.assertEqual(appeal.state, 'appealed')
        with self.assertRaisesRegex(UserError, 'depois da decisão'):
            appeal.action_notify()
        grade = npt.grade_ids.filtered(lambda g: g.student_id == ana)
        appeal.write({'grade_id': grade.id, 'new_score': 11})
        self.assertEqual(appeal.original_score, 9)
        appeal.action_grant()
        self.assertEqual((appeal.state, grade.score), ('granted', 11))
        appeal.action_notify()
        self.assertEqual(appeal.notified_date, fields.Date.context_today(appeal))
        # Fora de prazo: indefere-se liminarmente.
        late = Appeal.create(
            {
                'enrollment_id': enrollments[1].id,
                'subject_id': lp.id,
                'trimester_id': self.t1.id,
                'reason': 'Pedido atrasado',
                'posting_date': posted - timedelta(days=20),
            }
        )
        self.assertTrue(late.late)
        with self.assertRaisesRegex(UserError, 'fora de prazo'):
            late.action_admit()
        with self.assertRaisesRegex(UserError, 'motivo'):
            late.action_reject()
        late.action_reject('Entregue fora do prazo de três dias úteis.')
        self.assertEqual(late.state, 'rejected')
