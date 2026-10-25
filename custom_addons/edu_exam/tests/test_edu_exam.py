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
        # O extraordinário resolve a disciplina em atraso sem mudar a decisão do ano (DE 424/25, art. 25.º).
        carla_req = self.enrollments[0].year_result_id.requirement_ids
        bento_req = self.enrollments[2].year_result_id.requirement_ids
        self.assertEqual((carla_req.state, carla_req.passed), ('done', True))
        self.assertEqual((bento_req.state, bento_req.passed), ('done', False))  # faltou: 0 valores
        self.assertEqual(self.enrollments[0].year_result_id.status, 'conditional')
        # A mesma sala e o mesmo vigilante não servem duas sessões à mesma hora.
        other = self.env['edu.exam.session'].create(
            {'period_id': period.id, 'subject_id': self.lp.id, 'date': date(2027, 7, 6), 'hour_from': 8, 'hour_to': 10}
        )
        other.room_ids = [Command.create({'room_id': self.room1.id})]
        with self.assertRaises(ValidationError):
            other.date = date(2027, 7, 5)
        # Na mesma prova, o mesmo vigilante não fica em duas salas.
        with self.assertRaises(ValidationError):
            other.room_ids = [
                Command.create({'room_id': self.room2.id, 'supervisor_ids': [Command.set(self.teacher.ids)]}),
            ] + [Command.update(other.room_ids.id, {'supervisor_ids': [Command.set(self.teacher.ids)]})]

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
        # A secretaria regista o resultado da sessão; a nota entra por fora da janela do professor.
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'secretaria_exames',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        session.with_user(clerk).action_done()
        grades = {grade.student_id: grade for grade in assessment.grade_ids}
        self.assertEqual((grades[carla].score, grades[ana].score, grades[ana].absent), (14, 0, True))
        period.action_close()
        self.assertEqual(period.state, 'closed')

    def test_exam_planner(self):
        """Calendário de provas, como no secPed: época do calendário escolar, a mesma prova em várias turmas (cada uma
        na sua sala), um vigilante por turma sem choques e «Distribuir vigilantes»."""
        Period = self.env['edu.exam.period']
        event = self.env['edu.calendar.event'].create(
            {
                'name': 'Provas do I Trimestre',
                'academic_year_id': self.year.id,
                'event_type': 'exam',
                'date_start': date(2026, 12, 9),
                'date_end': date(2026, 12, 18),
            }
        )
        options = Period.planner_options()
        self.assertIn(event.id, [p['id'] for p in options['proposals']])
        period = Period.browse(Period.planner_create_from_event(event.id))
        self.assertEqual((period.kind, period.trimester_id), ('trimester_test', self.trimesters[0]))
        self.assertNotIn(event.id, [p['id'] for p in Period.planner_options()['proposals']])
        # Duas turmas da 7.ª, cada uma com a sua sala.
        self.edu_class.room_id = self.room1
        other = self.env['edu.class'].create(
            {
                'name': 'B',
                'course_id': self.edu_class.course_id.id,
                'curriculum_year_id': self.edu_class.curriculum_year_id.id,
                'room_id': self.room2.id,
            }
        )
        result = period.planner_mark(self.lp.id, '2026-12-09', 8.0, 10.0, (self.edu_class | other).ids)
        self.assertEqual((result['created'], result['failures']), (2, []))
        sessions = period.session_ids
        self.assertEqual(sessions.room_ids.room_id, self.room1 | self.room2)
        # Marcar outra vez a mesma prova à mesma hora: a sala já está ocupada, a turma fica de fora com o motivo.
        again = period.planner_mark(self.lp.id, '2026-12-09', 9.0, 11.0, self.edu_class.ids)
        self.assertEqual(again['created'], 0)
        self.assertIn('Sala 1', again['failures'][0])
        # Um vigilante por turma; o mesmo professor não vigia as duas à mesma hora.
        first, second = sessions.sorted(lambda s: s.class_ids.name)
        Period.planner_set_supervisor(first.id, self.teacher.id)
        with self.assertRaises(ValidationError):
            Period.planner_set_supervisor(second.id, self.teacher.id)
        # Distribuir: a turma que falta fica com outro professor livre.
        other_teacher = self.env['hr.employee'].create({'name': 'Outra Vigilante', 'edu_is_teacher': True})
        done = period.planner_distribute('2026-12-09', 8.0, 10.0)
        self.assertEqual(done['assigned'], 1)
        self.assertEqual(second.room_ids.supervisor_ids, other_teacher)
        self.assertFalse(second.incomplete)
        data = period.planner_data()
        self.assertEqual(len(data['sessions']), 2)
        # A secretaria não lê a ficha dos funcionários, mas vê os vigilantes; distribuir não os substitui e o mesmo
        # vigilante noutra prova à mesma hora continua a ser recusado.
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'secretaria_calendario',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        as_clerk = period.with_user(clerk)
        seen = {s['id']: [t['id'] for t in s['supervisors']] for s in as_clerk.planner_data()['sessions']}
        self.assertEqual(seen, {first.id: [self.teacher.id], second.id: [other_teacher.id]})
        self.assertEqual(as_clerk.planner_distribute('2026-12-09', 8.0, 10.0)['assigned'], 0)
        self.assertEqual(second.room_ids.supervisor_ids, other_teacher)
        with self.assertRaises(ValidationError):
            Period.with_user(clerk).planner_set_supervisor(second.id, self.teacher.id)
        # No formulário da sessão: a secretaria vê o vigilante na sala, troca-o por outro e procura pelo nome.
        room = second.room_ids.with_user(clerk)
        self.assertEqual(room.supervisor_public_ids.ids, [other_teacher.id])
        third = self.env['hr.employee'].create({'name': 'Terceira Vigilante', 'edu_is_teacher': True})
        room.supervisor_public_ids = [Command.set([third.id])]
        self.assertEqual(second.room_ids.supervisor_ids, third)
        with self.assertRaises(ValidationError):
            room.supervisor_public_ids = [Command.set([self.teacher.id])]
        found = self.env['edu.exam.session'].with_user(clerk).search([('supervisor_label', 'ilike', 'Terceira')])
        self.assertEqual(found, second)
        self.assertEqual({s['class'] for s in data['sessions']}, {'7ª A · SEC1', '7ª B · SEC1'})
        # Sem sala não há vigilante; remover uma prova sem notas.
        Period.planner_set_room(second.id, False)
        with self.assertRaisesRegex(UserError, 'sala'):
            Period.planner_set_supervisor(second.id, other_teacher.id)
        Period.planner_remove(second.id)
        self.assertEqual(period.session_ids, first)
