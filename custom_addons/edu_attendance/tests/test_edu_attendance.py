from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduAttendance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.t1 = cls.year.trimester_ids.filtered(lambda t: t.number == 1)
        cls.secondary = cls._course('Secundário', 'SEC2', 'level_sec2', 'tpl_sec2_cfb', 10)
        cls.technical = cls._course('Técnico de Enfermagem', 'ENF', 'level_tecnico', 'tpl_tec_saude_enf', 10)
        cls.class_sec = cls.secondary['class']
        cls.class_tec = cls.technical['class']
        cls.teacher_user = cls.env['res.users'].create(
            {
                'name': 'Pedro Docente',
                'login': 'pedro_docente',
                'group_ids': [Command.set([cls.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        cls.teacher = cls.env['hr.employee'].create(
            {'name': 'Pedro Docente', 'edu_is_teacher': True, 'user_id': cls.teacher_user.id}
        )
        cls.students = cls.env['edu.student'].create([{'name': n} for n in ('Ana', 'Bento', 'Carla')])

    @classmethod
    def _course(cls, name, code, level, template, number):
        course = cls.env['edu.course'].create(
            {
                'name': name,
                'code': code,
                'level_id': cls.env.ref(f'edu_core.{level}').id,
                'curriculum_template_id': cls.env.ref(f'edu_core.{template}').id,
            }
        )
        year_line = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == number)
        edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': course.id, 'curriculum_year_id': year_line.id}
        )
        return {'course': course, 'class': edu_class}

    def _enroll(self, edu_class, students=None):
        Enrollment = self.env['edu.enrollment']
        result = Enrollment
        for student in students or self.students:
            enrollment = Enrollment.create({'student_id': student.id, 'class_id': edu_class.id})
            enrollment.action_confirm()
            result |= enrollment
        return result

    def _subject_with_hours(self, edu_class, hours):
        line = edu_class.subject_line_ids.filtered(lambda line: line.weekly_hours == hours)[:1]
        self.assertTrue(line, f'Sem disciplina com {hours} tempos no plano')
        return line.subject_id

    def _lesson(self, edu_class, subject, day, *, absent=(), state='done', late=()):
        lesson = self.env['edu.lesson'].create({'class_id': edu_class.id, 'subject_id': subject.id, 'date': day})
        lesson.action_open_roll_call()
        for line in lesson.attendance_ids:
            if line.student_id in absent:
                line.state = 'absent'
            elif line.student_id in late:
                line.state = 'late'
        if state == 'done':
            lesson.summary = 'Matéria dada'
            lesson.action_done()
        elif state == 'cancelled':
            lesson.action_cancel()
        return lesson

    def _summary(self, enrollment, subject, trimester=None):
        self.env.flush_all()
        self.env.invalidate_all()
        domain = [('enrollment_id', '=', enrollment.id), ('subject_id', '=', subject.id)]
        if trimester:
            domain.append(('trimester_id', '=', trimester.id))
        return self.env['edu.absence.summary'].search(domain, limit=1)

    def test_general_limits(self):
        ana, bento, _carla = self.students
        enrollments = self._enroll(self.class_sec)
        subject = self._subject_with_hours(self.class_sec, 2)  # limite 4 por trimestre
        days = [date(2026, 9, d) for d in (7, 8, 9, 10, 11)]
        for day in days[:3]:
            self._lesson(self.class_sec, subject, day, absent=[ana])
        summary = self._summary(enrollments[0], subject, self.t1)
        self.assertEqual((summary.limit, summary.absent, summary.status), (4, 3, 'at_risk'))
        self.assertTrue(enrollments[0].absence_alert_ids)
        self._lesson(self.class_sec, subject, days[3], absent=[ana, bento])
        summary = self._summary(enrollments[0], subject, self.t1)
        self.assertEqual(summary.status, 'failed')
        self.assertEqual(self.class_sec._edu_absence_exclusions(), enrollments[0])
        # Justificar tira a falta da contagem.
        line = self.env['edu.lesson.attendance'].search(
            [('enrollment_id', '=', enrollments[0].id), ('state', '=', 'absent')], limit=1
        )
        line.justification = 'Atestado médico'
        line.action_justify()
        self.assertEqual(line.state, 'excused')
        self.assertEqual(line.justified_by_id, self.env.user)
        self.assertEqual(self._summary(enrollments[0], subject, self.t1).status, 'at_risk')

    def test_cancelled_and_late(self):
        ana = self.students[0]
        enrollments = self._enroll(self.class_sec, ana)
        subject = self._subject_with_hours(self.class_sec, 2)
        self._lesson(self.class_sec, subject, date(2026, 9, 7))
        self._lesson(self.class_sec, subject, date(2026, 9, 8), late=[ana])
        self._lesson(self.class_sec, subject, date(2026, 9, 9), absent=[ana])
        self._lesson(self.class_sec, subject, date(2026, 9, 10), absent=[ana], state='cancelled')
        summary = self._summary(enrollments, subject, self.t1)
        # Casos do secPed: a aula não realizada não conta; o atraso conta como presença.
        self.assertEqual((summary.lessons, summary.present, summary.late, summary.absent), (3, 1, 1, 1))
        lessons = self.env['edu.lesson'].search([('class_id', '=', self.class_sec.id)], order='date')
        self.assertEqual(lessons.mapped('lesson_number'), [1, 2, 3, 0])
        self.assertEqual(lessons[0].trimester_id, self.t1)

    @freeze_time('2027-06-30')
    def test_technical_yearly_limit(self):
        enrollments = self._enroll(self.class_tec, self.students[0])
        subject = self._subject_with_hours(self.class_tec, 2)  # limite anual 6
        t2 = self.year.trimester_ids.filtered(lambda t: t.number == 2)
        for day in (date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 9)):
            self._lesson(self.class_tec, subject, day, absent=self.students[0])
        for day in (t2.date_start, t2.date_start.replace(day=t2.date_start.day + 1)):
            self._lesson(self.class_tec, subject, day, absent=self.students[0])
        summary = self._summary(enrollments, subject, t2)
        self.assertEqual((summary.limit, summary.year_absent, summary.status), (6, 5, 'ok'))
        # O máximo anual é o triplo dos tempos (6): com 6 fica em risco, com 7 reprova.
        self._lesson(self.class_tec, subject, t2.date_start.replace(day=t2.date_start.day + 2), absent=self.students[0])
        self.assertEqual(self._summary(enrollments, subject, t2).status, 'at_risk')
        self.assertFalse(self.class_tec._edu_absence_exclusions())
        self._lesson(self.class_tec, subject, t2.date_start.replace(day=t2.date_start.day + 3), absent=self.students[0])
        self.assertEqual(self._summary(enrollments, subject, t2).status, 'failed')
        self.assertEqual(self.class_tec._edu_absence_exclusions(), enrollments)

    def test_generate_from_schedule(self):
        subject = self._subject_with_hours(self.class_sec, 2)
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'teacher_id': self.teacher.id}
        )
        schedule = self.env['edu.schedule'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'weekday': '0', 'hour_from': 7.5, 'hour_to': 8.25}
        )
        self.env['edu.schedule.exception'].create({'schedule_id': schedule.id, 'date': date(2026, 9, 14)})
        wizard = self.env['edu.lesson.generate'].create(
            {'class_ids': [(6, 0, self.class_sec.ids)], 'date_from': date(2026, 9, 1), 'date_to': date(2026, 9, 30)}
        )
        wizard.action_generate()
        lessons = self.env['edu.lesson'].search([('schedule_id', '=', schedule.id)])
        # Segundas-feiras de Setembro de 2026: 7, 14 (sem aula), 21 e 28.
        self.assertEqual(lessons.mapped('date'), [date(2026, 9, 28), date(2026, 9, 21), date(2026, 9, 7)])
        self.assertEqual(lessons.mapped('teacher_id'), self.teacher)
        wizard.action_generate()
        self.assertEqual(self.env['edu.lesson'].search_count([('schedule_id', '=', schedule.id)]), 3)
        with self.assertRaises(ValidationError):
            self.env['edu.lesson'].create(
                {
                    'class_id': self.class_sec.id,
                    'subject_id': subject.id,
                    'schedule_id': schedule.id,
                    'date': date(2026, 9, 8),
                }  # fmt: skip
            )

    def test_teacher_permissions(self):
        self._enroll(self.class_sec)
        subject = self._subject_with_hours(self.class_sec, 2)
        other = self._subject_with_hours(self.class_sec, 3)
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'teacher_id': self.teacher.id}
        )
        Lesson = self.env['edu.lesson'].with_user(self.teacher_user)
        lesson = Lesson.create({'class_id': self.class_sec.id, 'subject_id': subject.id, 'date': date(2026, 9, 7)})
        lesson.action_open_roll_call()
        self.assertEqual(len(lesson.attendance_ids), 3)
        lesson.attendance_ids[0].state = 'absent'
        lesson.summary = 'Funções reais de variável real'
        lesson.action_done()
        with self.assertRaises(AccessError):
            Lesson.create({'class_id': self.class_sec.id, 'subject_id': other.id, 'date': date(2026, 9, 8)})
        with self.assertRaises(UserError):
            lesson.sudo().unlink()

    def test_primary_has_no_subject_limit(self):
        """No primário retém só a frequência inferior a 2/3 (DE 424/25, art. 21.º); os 3/4/5 são do secundário."""
        primary = self._course('Primário', 'PRI', 'level_primario', 'tpl_prim_base', 1)['class']
        ana = self.students[0]
        enrollment = self._enroll(primary, ana)
        subject = primary.subject_line_ids.filtered('weekly_hours')[:1].subject_id
        for day in (7, 8, 9, 10, 11, 14):
            self._lesson(primary, subject, date(2026, 9, day), absent=[ana])
        summary = self._summary(enrollment, subject, self.t1)
        self.assertEqual((summary.absent, summary.limit, summary.status), (6, 0, 'ok'))
        self.assertFalse(primary._edu_absence_exclusions())

    def test_lesson_rules(self):
        self._enroll(self.class_sec)
        subject = self._subject_with_hours(self.class_sec, 2)
        # Aula futura ou sem sumário não se dá por dada.
        future = self.env['edu.lesson'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'date': date(2027, 5, 3), 'summary': 'X'}
        )
        with freeze_time('2026-10-22'), self.assertRaisesRegex(UserError, 'ainda não aconteceu'):
            future.action_done()
        lesson = self._lesson(self.class_sec, subject, date(2026, 9, 7), state='scheduled')
        with self.assertRaisesRegex(UserError, 'sumário'):
            lesson.action_done()
        lesson.summary = 'Equações'
        lesson.action_done()
        # Trimestre fechado: as faltas e as aulas não mudam.
        self.t1.action_close()
        with self.assertRaisesRegex(UserError, 'fechado'):
            lesson.attendance_ids[0].state = 'absent'
        with self.assertRaisesRegex(UserError, 'fechado'):
            lesson.action_reset()
        with self.assertRaisesRegex(UserError, 'fechado'):
            self.env['edu.lesson'].create(
                {'class_id': self.class_sec.id, 'subject_id': subject.id, 'date': date(2026, 9, 8)}
            )

    def test_generate_skips_holidays(self):
        subject = self._subject_with_hours(self.class_sec, 2)
        schedule = self.env['edu.schedule'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'weekday': '0', 'hour_from': 7.5, 'hour_to': 8.25}
        )
        self.env['edu.calendar.event'].create(
            [
                {
                    'name': 'Feriado',
                    'academic_year_id': self.year.id,
                    'event_type': 'holiday',
                    'date_start': date(2026, 9, 14),
                },
                {
                    'name': 'Pausa',
                    'academic_year_id': self.year.id,
                    'event_type': 'holiday',
                    'date_start': date(2026, 9, 26),
                    'date_end': date(2026, 10, 2),
                },
                {
                    'name': 'Só no primário',
                    'academic_year_id': self.year.id,
                    'event_type': 'holiday',
                    'date_start': date(2026, 9, 21),
                    'level_ids': [Command.set(self.env.ref('edu_core.level_primario').ids)],
                },
            ]
        )
        self.env['edu.lesson']._generate(self.class_sec, date(2026, 9, 1), date(2026, 10, 6))
        lessons = self.env['edu.lesson'].search([('schedule_id', '=', schedule.id)], order='date')
        self.assertEqual(lessons.mapped('date'), [date(2026, 9, 7), date(2026, 9, 21), date(2026, 10, 5)])

    def test_replacement(self):
        subject = self._subject_with_hours(self.class_sec, 2)
        other_subject = self._subject_with_hours(self.class_tec, 2)
        substitute = self.env['hr.employee'].create({'name': 'Rita Substituta', 'edu_is_teacher': True})
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'teacher_id': self.teacher.id}
        )
        schedule = self.env['edu.schedule'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'weekday': '0', 'hour_from': 7.5, 'hour_to': 8.25}
        )
        other = self.env['edu.schedule'].create(
            {
                'class_id': self.class_tec.id,
                'subject_id': other_subject.id,
                'weekday': '0',
                'hour_from': 7.5,
                'hour_to': 8.25,
            }
        )
        day = date(2026, 9, 7)
        self.env['edu.lesson']._generate(self.class_sec, day, day)
        lesson = self.env['edu.lesson'].search([('schedule_id', '=', schedule.id), ('date', '=', day)])
        self.assertEqual(lesson.teacher_id, self.teacher)
        # A aula já gerada passa para o substituto; ao apagar a substituição, volta ao professor.
        replacement = self.env['edu.schedule.replacement'].create(
            {'schedule_id': schedule.id, 'date': day, 'replacement_teacher_id': substitute.id}
        )
        self.assertEqual(replacement.original_teacher_id, self.teacher)
        self.assertEqual(replacement.class_id, self.class_sec)
        self.assertIn(self.class_sec.display_name, replacement.display_name)
        self.assertEqual(lesson.teacher_id, substitute)
        # Não substitui duas aulas à mesma hora.
        with self.assertRaisesRegex(ValidationError, 'já substitui'):
            self.env['edu.schedule.replacement'].create(
                {'schedule_id': other.id, 'date': day, 'replacement_teacher_id': substitute.id}
            )
        replacement.unlink()
        self.assertEqual(lesson.teacher_id, self.teacher)

    def test_who_justifies(self):
        """Justificam as faltas só a secretaria e o director de turma (decisão da escola)."""
        ana = self.students[0]
        enrollment = self._enroll(self.class_sec, ana)
        subject = self._subject_with_hours(self.class_sec, 2)
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class_sec.id, 'subject_id': subject.id, 'teacher_id': self.teacher.id}
        )
        for day in (7, 8, 9):
            self._lesson(self.class_sec, subject, date(2026, 9, day), absent=[ana])
        lines = self.env['edu.lesson.attendance'].search([('enrollment_id', '=', enrollment.id)], order='date')
        # O professor da disciplina marca faltas mas não as justifica.
        line = lines[0].with_user(self.teacher_user)
        self.assertFalse(line.can_justify)
        with self.assertRaises(AccessError):
            line.write({'state': 'excused', 'justification': 'Doença'})
        wizard = (
            self.env['edu.absence.justify']
            .with_user(self.teacher_user)
            .create(
                {
                    'student_id': ana.id,
                    'date_from': date(2026, 9, 7),
                    'date_to': date(2026, 9, 8),
                    'justification': 'Doença',
                }
            )
        )
        self.assertEqual(len(wizard.line_ids), 2)
        with self.assertRaises(AccessError):
            wizard.action_justify()
        # Sem motivo, não se justifica.
        with self.assertRaisesRegex(UserError, 'motivo'):
            lines[0].state = 'excused'
        # Director de turma: justifica o período (o atestado de dois dias).
        self.class_sec.director_id = self.teacher
        self.assertTrue(lines[0].with_user(self.teacher_user).can_justify)
        wizard.action_justify()
        self.assertEqual(lines.mapped('state'), ['excused', 'excused', 'absent'])
        self.assertEqual(lines[0].justified_by_id, self.teacher_user)
        self.assertEqual(lines[0].justification, 'Doença')

    @freeze_time('2026-10-01')
    def test_audit_teacher_rights_and_moves(self):
        """Auditoria da fase 5: o professor só gere as suas aulas e chamadas; mover um tempo refaz as aulas futuras."""
        self._enroll(self.class_sec)
        lp = self._subject_with_hours(self.class_sec, 2)
        mat = self._subject_with_hours(self.class_sec, 3)
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.class_sec.id, 'subject_id': lp.id, 'teacher_id': self.teacher.id}
        )
        Lesson = self.env['edu.lesson'].with_user(self.teacher_user)
        # Pôr-se como professor de uma aula de outra disciplina não dá acesso.
        with self.assertRaises(AccessError):
            Lesson.create(
                {
                    'class_id': self.class_sec.id,
                    'subject_id': mat.id,
                    'date': date(2026, 9, 7),
                    'teacher_id': self.teacher.id,
                }
            )
        other = self.env['edu.lesson'].create(
            {'class_id': self.class_sec.id, 'subject_id': mat.id, 'date': date(2026, 9, 8)}
        )
        with self.assertRaises(AccessError):
            other.with_user(self.teacher_user).action_open_roll_call()
        other.action_open_roll_call()
        with self.assertRaises(AccessError):
            other.attendance_ids[0].with_user(self.teacher_user).unlink()
        empty = self.env['edu.lesson'].create(
            {'class_id': self.class_sec.id, 'subject_id': mat.id, 'date': date(2026, 9, 9)}
        )
        with self.assertRaises(AccessError):
            self.env['edu.lesson.attendance'].with_user(self.teacher_user).create(
                {'lesson_id': empty.id, 'enrollment_id': other.attendance_ids[0].enrollment_id.id, 'state': 'absent'}
            )
        # Trimestre fechado: nem a secretaria apaga faltas.
        other.summary = 'Dada'
        other.action_done()
        self.t1.action_close()
        with self.assertRaisesRegex(UserError, 'fechado'):
            other.attendance_ids.unlink()
        self.t1.action_reopen()
        # Mover um tempo: as aulas futuras sem chamada saem e voltam a gerar-se no dia novo.
        schedule = self.env['edu.schedule'].create(
            {'class_id': self.class_sec.id, 'subject_id': lp.id, 'weekday': '0', 'hour_from': 7.5, 'hour_to': 8.25}
        )
        self.env['edu.lesson']._generate(self.class_sec, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(
            self.env['edu.lesson'].search([('schedule_id', '=', schedule.id)]).mapped('date'),
            [date(2026, 10, 26), date(2026, 10, 19), date(2026, 10, 12), date(2026, 10, 5)],
        )
        schedule.weekday = '1'
        self.env['edu.lesson']._generate(self.class_sec, date(2026, 10, 1), date(2026, 10, 31))
        dates = self.env['edu.lesson'].search([('schedule_id', '=', schedule.id)]).mapped('date')
        self.assertTrue(all(day.weekday() == 1 for day in dates))
        self.assertEqual(len(dates), 4)
        # Trocar o professor: as aulas futuras acompanham.
        substitute = self.env['hr.employee'].create({'name': 'Novo Professor', 'edu_is_teacher': True})
        schedule.teacher_id = substitute
        lessons = self.env['edu.lesson'].search([('schedule_id', '=', schedule.id)])
        self.assertEqual(lessons.teacher_id, substitute)
