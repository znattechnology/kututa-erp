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

    def _full_year(self, edu_class, code, scores_by_trimester):
        """{trimestre: {aluno: (contínua, prova)}}"""
        for trimester, scores in scores_by_trimester.items():
            self._assess(edu_class, code, trimester, 'continuous', {s: v[0] for s, v in scores.items()})
            self._assess(edu_class, code, trimester, 'trimester_test', {s: v[1] for s, v in scores.items()})

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
        requirement.score = 12
        requirement.action_record()
        self.assertEqual(ana_result.status, 'promoted')
        self.assertEqual(self._year_subject(enrollments[0], 'LP').final, 12)
        # Retido não se matricula numa classe acima (art. 25.º).
        eighth = self._class(self.sec1, 8, year=self.next_year)
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
