from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestUcExam(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'edu_is_school': True, 'edu_school_type': 'higher'})
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 10, 1), 'date_end': date(2027, 9, 30), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.sem1 = cls.year.trimester_ids.sorted('number')[0]
        level = cls.env.ref('edu_university.level_licenciatura')
        cls.course = cls.env['edu.course'].create({'name': 'Gestão', 'code': 'GES', 'level_id': level.id})
        curriculum = cls.env['edu.curriculum'].create({'name': 'GES', 'course_id': cls.course.id, 'level_id': level.id})
        cls.accounting, cls.marketing = cls.env['edu.subject'].create(
            [{'name': 'Contabilidade', 'code': 'CTB'}, {'name': 'Marketing', 'code': 'MKT'}]
        )
        # Curso de um ano só (o 1.º é o último): todos são finalistas.
        plan = cls.env['edu.curriculum.year'].create(
            {
                'curriculum_id': curriculum.id,
                'year': 1,
                'line_ids': [
                    (0, 0, {'subject_id': cls.accounting.id, 'semester': '1', 'credits': 6}),
                    (0, 0, {'subject_id': cls.marketing.id, 'semester': '1', 'credits': 6}),
                ],
            }
        )
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': cls.course.id, 'academic_year_id': cls.year.id, 'curriculum_year_id': plan.id}
        )
        names = ('Abel', 'Beatriz', 'Celso', 'Dora', 'Elias')
        cls.students = cls.env['edu.student'].create([{'name': n} for n in names])
        cls.enrollments = cls.env['edu.enrollment']
        for student in cls.students:
            enrollment = cls.env['edu.enrollment'].create({'student_id': student.id, 'class_id': cls.edu_class.id})
            enrollment.action_confirm()
            cls.enrollments |= enrollment
        # MF: Abel 16 (dispensado), Beatriz 11, Celso 9, Dora 5 (excluída), Elias 12.
        scores = {'Abel': 16, 'Beatriz': 11, 'Celso': 9, 'Dora': 5, 'Elias': 12}
        for subject in (cls.accounting, cls.marketing):
            assessment = cls.env['edu.assessment'].create(
                {
                    'name': 'Frequência',
                    'class_id': cls.edu_class.id,
                    'subject_id': subject.id,
                    'trimester_id': cls.sem1.id,
                    'assessment_type': 'frequency',
                }
            )
            assessment.action_fill_students()
            for grade in assessment.grade_ids:
                grade.score = scores[grade.student_id.name] if subject == cls.accounting else 16
        cls.sem1.action_close()

    def _uc(self, name, subject=None):
        return self.enrollments.uc_registration_ids.filtered(
            lambda r: r.student_id.name == name and r.subject_id == (subject or self.accounting)
        )

    def _session(self, kind, day):
        period = self.env['edu.exam.period'].create(
            {
                'name': kind,
                'kind': kind,
                'academic_year_id': self.year.id,
                'date_start': date(2027, 2, 1),
                'date_end': date(2027, 9, 20),
            }
        )
        session = self.env['edu.exam.session'].create(
            {'period_id': period.id, 'subject_id': self.accounting.id, 'date': date(2027, 2, day)}
        )
        session.action_summon()
        return session

    def _sit(self, session, scores):
        for seat in session.seat_ids:
            name = seat.student_id.name
            if scores.get(name) is None:
                seat.attended = False
            else:
                seat.score = scores[name]
        session.action_done()

    def test_exam_cycle(self):
        normal = self._session('uc_normal', 2)
        self.assertEqual(sorted(normal.seat_ids.student_id.mapped('name')), ['Beatriz', 'Celso', 'Elias'])
        self.assertEqual(
            normal.seat_ids.uc_registration_id, self._uc('Beatriz') | self._uc('Celso') | self._uc('Elias')
        )
        # Beatriz 13 → 0,4 × 11 + 0,6 × 13 = 12,2 → 12; Celso 8 (abaixo do mínimo); Elias falta.
        self._sit(normal, {'Beatriz': 13, 'Celso': 8, 'Elias': None})
        self.assertEqual((self._uc('Beatriz').final_grade, self._uc('Beatriz').state), (12, 'passed'))
        self.assertEqual((self._uc('Celso').final_grade, self._uc('Celso').state), (8, 'failed'))
        self.assertFalse(self._uc('Elias').has_exam_normal)
        # Recurso: Celso (reprovou) e Elias (faltou); não a Dora (excluída) nem quem aprovou.
        appeal = self._session('uc_appeal', 20)
        self.assertEqual(sorted(appeal.seat_ids.student_id.mapped('name')), ['Celso', 'Elias'])
        # Celso 11 → 0,4 × 9 + 0,6 × 11 = 10,2 → 10.
        self._sit(appeal, {'Celso': 11, 'Elias': 6})
        self.assertEqual((self._uc('Celso').final_grade, self._uc('Celso').state), (10, 'passed'))
        self.assertEqual(self._uc('Elias').state, 'failed')
        # Época especial (finalistas com até 2 UCs por aprovar): Dora e Elias.
        special = self._session('uc_special', 25)
        self.assertEqual(sorted(special.seat_ids.student_id.mapped('name')), ['Dora', 'Elias'])
        self._sit(special, {'Dora': 15, 'Elias': 9})
        self.assertEqual((self._uc('Dora').final_grade, self._uc('Dora').state), (10, 'passed'))
        self.assertEqual(self._uc('Elias').state, 'failed')
        # Melhoria: os aprovados; quem falta fica com a nota que tinha.
        improvement = self._session('uc_improvement', 27)
        self.assertIn('Abel', improvement.seat_ids.student_id.mapped('name'))
        self.assertNotIn('Elias', improvement.seat_ids.student_id.mapped('name'))
        scores = dict.fromkeys(improvement.seat_ids.student_id.mapped('name'))
        scores['Beatriz'] = 17
        self._sit(improvement, scores)
        self.assertEqual((self._uc('Beatriz').final_grade, self._uc('Beatriz').result_source), (17, 'improvement'))
        self.assertEqual((self._uc('Abel').final_grade, self._uc('Abel').result_source), (16, 'frequency'))

    def test_special_limits(self):
        regulation = self.env['edu.university.regulation']._get(self.env.company, self.course.level_id)
        regulation.special_max_ucs = 0
        self.assertFalse(self._session('uc_special', 25).seat_ids, 'Ninguém tem 0 UCs por aprovar.')
        regulation.write({'special_max_ucs': 2, 'special_final_year_only': True})
        # Num curso de dois anos, o 1.º ano não é o último: sem época especial.
        self.env['edu.curriculum.year'].create({'curriculum_id': self.edu_class.curriculum_id.id, 'year': 2})
        self.enrollments.invalidate_recordset()
        self.assertFalse(self._session('uc_special', 26).seat_ids)
