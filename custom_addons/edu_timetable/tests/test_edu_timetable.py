from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduTimetable(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.course = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.env.ref('edu_core.level_tecnico').id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }
        )
        tenth = cls.course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 10)
        cls.room = cls.env['edu.room'].create({'name': 'Sala 1', 'code': 'S1'})
        cls.room2 = cls.env['edu.room'].create({'name': 'Sala 2', 'code': 'S2'})
        cls.shift = cls.env['edu.shift'].create({'name': 'Manhã', 'hour_from': 7.5, 'hour_to': 12.5})
        cls.class_a = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': cls.course.id, 'curriculum_year_id': tenth.id, 'room_id': cls.room.id}
        )
        cls.class_b = cls.env['edu.class'].create(
            {'name': 'B', 'course_id': cls.course.id, 'curriculum_year_id': tenth.id, 'room_id': cls.room2.id}
        )
        subjects = cls.class_a.subject_line_ids.subject_id
        cls.lp = subjects.filtered(lambda s: s.code == 'LP')
        cls.mat = subjects.filtered(lambda s: s.code == 'MAT')
        cls.teacher = cls.env['hr.employee'].create({'name': 'Pedro Docente', 'edu_is_teacher': True})
        cls.teacher2 = cls.env['hr.employee'].create({'name': 'Rita Professora', 'edu_is_teacher': True})

    def test_time_slots(self):
        self.shift.action_generate_slots()
        slots = self.shift.time_slot_ids
        self.assertEqual(len(slots.filtered('is_break')), 1)
        self.assertEqual(slots.sorted('hour_from')[0].hour_from, 7.5)
        self.assertLessEqual(max(slots.mapped('hour_to')), 12.5)
        with self.assertRaises(ValidationError):
            self.env['edu.time.slot'].create(
                {'name': 'Fora', 'shift_id': self.shift.id, 'hour_from': 12.0, 'hour_to': 13.0}
            )

    def test_assignments(self):
        Assignment = self.env['edu.teaching.assignment']
        year_assignment = Assignment.create(
            {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'teacher_id': self.teacher.id}
        )
        self.assertEqual(year_assignment.weekly_hours, 4)
        first = self.year.trimester_ids.filtered(lambda t: t.number == 1)
        # Um só professor por turma e disciplina em períodos que se cruzam.
        with self.assertRaises(ValidationError):
            Assignment.create(
                {
                    'class_id': self.class_a.id,
                    'subject_id': self.lp.id,
                    'teacher_id': self.teacher2.id,
                    'trimester_id': first.id,
                }
            )
        other_subject = self.env['edu.subject'].create({'name': 'Fora do plano', 'code': 'FORA'})
        with self.assertRaises(ValidationError):
            Assignment.create(
                {'class_id': self.class_a.id, 'subject_id': other_subject.id, 'teacher_id': self.teacher.id}
            )
        self.assertEqual(Assignment._teacher_for(self.class_a, self.lp), self.teacher)

    def test_director(self):
        self.class_a.director_id = self.teacher
        with self.assertRaises(ValidationError):
            self.class_b.director_id = self.teacher
        self.assertEqual(self.teacher.edu_weekly_load_max, 22)

    def test_schedule_conflicts(self):
        Schedule = self.env['edu.schedule']
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'teacher_id': self.teacher.id}
        )
        monday = Schedule.create(
            {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'weekday': '0', 'hour_from': 7.5, 'hour_to': 8.25}
        )
        self.assertEqual(monday.teacher_id, self.teacher)
        self.assertEqual(monday.room_id, self.room)
        # A turma já tem aula.
        with self.assertRaisesRegex(ValidationError, 'turma'):
            Schedule.create(
                {
                    'class_id': self.class_a.id,
                    'subject_id': self.mat.id,
                    'weekday': '0',
                    'hour_from': 8.0,
                    'hour_to': 8.75,
                    'teacher_id': self.teacher2.id,
                }  # fmt: skip
            )
        # O professor já está ocupado.
        with self.assertRaisesRegex(ValidationError, 'Pedro Docente'):
            Schedule.create(
                {
                    'class_id': self.class_b.id,
                    'subject_id': self.lp.id,
                    'weekday': '0',
                    'hour_from': 7.5,
                    'hour_to': 8.25,
                    'teacher_id': self.teacher.id,
                }  # fmt: skip
            )
        # A sala já está ocupada.
        with self.assertRaisesRegex(ValidationError, 'Sala 1'):
            Schedule.create(
                {
                    'class_id': self.class_b.id,
                    'subject_id': self.lp.id,
                    'weekday': '0',
                    'hour_from': 7.5,
                    'hour_to': 8.25,
                    'teacher_id': self.teacher2.id,
                    'room_id': self.room.id,
                }  # fmt: skip
            )
        self.assertIn('Língua Portuguesa: 1 de 4 tempos', self.class_a.schedule_check)
        self.assertIn('LP', self.class_a.schedule_grid)
        self.assertEqual(self.teacher.edu_weekly_load, 1)

    def test_exceptions_and_replacements(self):
        lesson = self.env['edu.schedule'].create(
            {
                'class_id': self.class_a.id,
                'subject_id': self.lp.id,
                'teacher_id': self.teacher.id,
                'weekday': '0',
                'hour_from': 7.5,
                'hour_to': 8.25,
            }
        )
        monday = date(2026, 9, 7)
        self.assertTrue(lesson._occurs_on(monday))
        self.assertFalse(lesson._occurs_on(date(2026, 9, 8)))
        with self.assertRaises(ValidationError):
            self.env['edu.schedule.exception'].create({'schedule_id': lesson.id, 'date': date(2026, 9, 8)})
        replacement = self.env['edu.schedule.replacement'].create(
            {'schedule_id': lesson.id, 'date': monday, 'replacement_teacher_id': self.teacher2.id}
        )
        self.assertEqual(replacement.original_teacher_id, self.teacher)
        self.assertEqual(lesson._teacher_on(monday), self.teacher2)
        with self.assertRaises(ValidationError):
            self.env['edu.schedule.replacement'].create(
                {'schedule_id': lesson.id, 'date': date(2026, 9, 14), 'replacement_teacher_id': self.teacher.id}
            )
        holiday = date(2026, 9, 21)
        self.env['edu.schedule.exception'].create({'schedule_id': lesson.id, 'date': holiday, 'reason': 'Feriado'})
        self.assertFalse(lesson._occurs_on(holiday))
