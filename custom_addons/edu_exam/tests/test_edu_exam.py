from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduExam(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.trimesters = cls.year.trimester_ids.sorted('number')
        course = cls.env['edu.course'].create(
            {'name': 'Secundário I', 'code': 'SEC1', 'level_id': cls.env.ref('edu_core.level_sec1').id}
        )
        seventh = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 7)
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': course.id, 'curriculum_year_id': seventh.id}
        )
        cls.lp = cls.edu_class.subject_line_ids.subject_id.filtered(lambda s: s.code == 'LP')
        cls.students = cls.env['edu.student'].create([{'name': n} for n in ('Carla', 'Ana', 'Bento')])
        cls.enrollments = cls.env['edu.enrollment']
        for student in cls.students:
            enrollment = cls.env['edu.enrollment'].create(
                {'student_id': student.id, 'class_id': cls.edu_class.id, 'subject_ids': [Command.set(cls.lp.ids)]}
            )
            enrollment.action_confirm()
            cls.enrollments |= enrollment
        cls.room1 = cls.env['edu.room'].create({'name': 'Sala 1', 'code': 'S1', 'capacity': 2})
        cls.room2 = cls.env['edu.room'].create({'name': 'Sala 2', 'code': 'S2', 'capacity': 2})
        cls.teacher = cls.env['hr.employee'].create({'name': 'Vigilante', 'edu_is_teacher': True})

    def _grades(self, scores):
        """Notas do ano inteiro de LP: {aluno: nota igual nos três trimestres}."""
        for trimester in self.trimesters:
            for kind in ('continuous', 'trimester_test'):
                assessment = self.env['edu.assessment'].create(
                    {
                        'name': kind,
                        'class_id': self.edu_class.id,
                        'subject_id': self.lp.id,
                        'trimester_id': trimester.id,
                        'assessment_type': kind,
                    }  # fmt: skip
                )
                assessment.action_fill_students()
                for grade in assessment.grade_ids:
                    grade.score = scores[grade.student_id]

    def _period(self, kind):
        return self.env['edu.exam.period'].create(
            {'name': kind, 'kind': kind, 'date_start': date(2027, 7, 1), 'date_end': date(2027, 7, 20)}
        )

    def test_extraordinary_exam(self):
        carla, ana, bento = self.students
        self._grades({carla: 8, ana: 15, bento: 9})
        self.edu_class.action_compute_year_results()
        self.assertEqual(self.enrollments[0].year_result_id.status, 'conditional')
        period = self._period('extraordinary')
        session = self.env['edu.exam.session'].create(
            {'period_id': period.id, 'subject_id': self.lp.id, 'date': date(2027, 7, 5), 'hour_from': 8, 'hour_to': 10}
        )
        session.action_summon()
        self.assertEqual(session.seat_ids.student_id, carla | bento)
        session.room_ids = [
            Command.create({'room_id': self.room1.id, 'supervisor_ids': [Command.set(self.teacher.ids)]})
        ]
        session.action_distribute()
        self.assertEqual({seat.student_id: seat.seat_number for seat in session.seat_ids}, {bento: 1, carla: 2})
        seats = {seat.student_id: seat for seat in session.seat_ids}
        seats[carla].score = 13
        seats[bento].attended = False
        session.action_done()
        self.assertEqual(session.state, 'done')
        self.assertEqual(self.enrollments[0].year_result_id.status, 'promoted')
        self.assertEqual(self.enrollments[2].year_result_id.status, 'retained')  # faltou: 0 valores
        # A mesma sala e o mesmo vigilante não servem duas sessões à mesma hora.
        other = self.env['edu.exam.session'].create(
            {'period_id': period.id, 'subject_id': self.lp.id, 'date': date(2027, 7, 6), 'hour_from': 8, 'hour_to': 10}
        )
        other.room_ids = [Command.create({'room_id': self.room1.id})]
        with self.assertRaises(ValidationError):
            other.date = date(2027, 7, 5)

    def test_trimester_test_session(self):
        carla, ana, bento = self.students
        first = self.trimesters[0]
        assessment = self.env['edu.assessment'].create(
            {
                'name': 'Prova do I trimestre',
                'class_id': self.edu_class.id,
                'subject_id': self.lp.id,
                'trimester_id': first.id,
                'assessment_type': 'trimester_test',
            }  # fmt: skip
        )
        period = self.env['edu.exam.period'].create(
            {
                'name': 'Provas do I trimestre',
                'kind': 'trimester_test',
                'trimester_id': first.id,
                'date_start': date(2026, 12, 1),
                'date_end': date(2026, 12, 15),
            }  # fmt: skip
        )
        session = self.env['edu.exam.session'].create(
            {
                'period_id': period.id,
                'subject_id': self.lp.id,
                'date': date(2026, 12, 2),
                'class_ids': [Command.set(self.edu_class.ids)],
                'assessment_ids': [Command.set(assessment.ids)],
            }  # fmt: skip
        )
        session.action_summon()
        session.room_ids = [
            Command.create({'room_id': self.room1.id}),
            Command.create({'room_id': self.room2.id}),
        ]
        session.action_distribute()
        self.assertEqual(len(session.seat_ids.filtered(lambda s: s.room_id.room_id == self.room1)), 2)
        for seat in session.seat_ids:
            seat.score = 14
        session.seat_ids.filtered(lambda s: s.student_id == ana).attended = False
        with self.assertRaises(UserError):
            period.action_close()
        session.action_done()
        grades = {grade.student_id: grade for grade in assessment.grade_ids}
        self.assertEqual((grades[carla].score, grades[ana].score, grades[ana].absent), (14, 0, True))
        period.action_close()
        self.assertEqual(period.state, 'closed')
