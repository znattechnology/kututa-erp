from datetime import date

from odoo.exceptions import AccessError, ValidationError
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
        # Grelha semanal no estilo da pauta: tempos × dias e, em cada aula, a disciplina, o professor e a sala.
        grid = self.class_a.schedule_grid
        self.assertIn('o_edu_schedule_grid', grid)
        self.assertIn('Língua Portuguesa', grid)
        self.assertIn('07:30 – 08:15', grid)
        self.assertIn(self.teacher.name, grid)
        self.assertIn('Segunda-feira', grid)
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
        # Para escolher o substituto: só os livres a essa hora. A Rita já substitui às 7:30 de segunda; o Pedro é o
        # professor da turma; quem tem aula noutra turma à mesma hora também fica de fora.
        teacher3 = self.env['hr.employee'].create({'name': 'Sara Livre', 'edu_is_teacher': True})
        busy = self.env['hr.employee'].create({'name': 'Tomé Ocupado', 'edu_is_teacher': True})
        busy_lesson = self.env['edu.schedule'].create(
            {
                'class_id': self.class_b.id,
                'subject_id': self.mat.id,
                'teacher_id': busy.id,
                'weekday': '0',
                'hour_from': 7.5,
                'hour_to': 8.25,
            }
        )
        # O Pedro falta às 7:30 de segunda (a aula dele tem substituto): não é livre para substituir outra a essa hora.
        self.assertNotIn(
            self.teacher.id,
            self.env['edu.schedule.replacement']
            .new({'schedule_id': busy_lesson.id, 'date': monday})
            .free_teacher_ids._origin.ids,
        )
        with self.assertRaises(ValidationError):
            self.env['edu.schedule.replacement'].create(
                {'schedule_id': busy_lesson.id, 'date': monday, 'replacement_teacher_id': self.teacher.id}
            )
        other = self.env['edu.schedule'].create(
            {
                'class_id': self.class_b.id,
                'subject_id': self.lp.id,
                'teacher_id': teacher3.id,
                'weekday': '0',
                'hour_from': 8.25,
                'hour_to': 9.0,
            }
        )
        draft = self.env['edu.schedule.replacement'].new({'schedule_id': lesson.id, 'date': monday})
        free = set(draft.free_teacher_ids._origin.ids)
        self.assertIn(teacher3.id, free)
        self.assertFalse({self.teacher.id, self.teacher2.id, busy.id} & free)
        # A própria substituição não tira o seu substituto da lista (ao editar).
        self.assertIn(self.teacher2.id, replacement.free_teacher_ids.ids)
        self.assertNotIn(teacher3.id, self.env['edu.schedule.replacement'].new(
            {'schedule_id': other.id, 'date': monday}
        ).free_teacher_ids._origin.ids)  # fmt: skip
        with self.assertRaises(ValidationError):
            self.env['edu.schedule.replacement'].create(
                {'schedule_id': lesson.id, 'date': date(2026, 9, 14), 'replacement_teacher_id': self.teacher.id}
            )
        holiday = date(2026, 9, 21)
        self.env['edu.schedule.exception'].create({'schedule_id': lesson.id, 'date': holiday, 'reason': 'Feriado'})
        self.assertFalse(lesson._occurs_on(holiday))

    def test_schedule_editor(self):
        """Editor de horários: os dados da turma, colocar, mover e os choques que se vêem antes de colocar."""
        Schedule = self.env['edu.schedule']
        Assignment = self.env['edu.teaching.assignment']
        Assignment.create({'class_id': self.class_a.id, 'subject_id': self.lp.id, 'teacher_id': self.teacher.id})
        Assignment.create({'class_id': self.class_b.id, 'subject_id': self.mat.id, 'teacher_id': self.teacher.id})
        self.class_a.shift_id = self.shift
        self.shift.action_generate_slots()
        options = Schedule.editor_options()
        self.assertIn(self.class_a.id, [c['id'] for c in options['classes']])
        self.assertIn('10ª A · ENF', [c['name'] for c in options['classes']])

        # A outra turma tem o mesmo professor à segunda às 07:30: a célula aparece ocupada para LP na turma A.
        Schedule.create(
            {'class_id': self.class_b.id, 'subject_id': self.mat.id, 'weekday': '0', 'hour_from': 7.5, 'hour_to': 8.25}
        )
        data = Schedule.editor_class_data(self.class_a.id)
        lp = next(s for s in data['subjects'] if s['id'] == self.lp.id)
        self.assertEqual((lp['planned'], lp['placed'], lp['teacher']), (4, 0, self.teacher.name))
        self.assertEqual(data['teacher_busy'][str(self.teacher.id)][0]['label'], '10ª B · ENF · Matemática')
        self.assertEqual(data['periods'][0]['label'], '07:30 – 08:15')
        self.assertEqual([d['name'] for d in data['days']][-1], 'Sexta-feira')

        # Colocar onde o professor está ocupado é recusado; noutra célula entra, e arrasta-se para terça.
        with self.assertRaises(ValidationError):
            Schedule.editor_place(self.class_a.id, self.lp.id, 0, 7.5, 8.25)
        placed = Schedule.editor_place(self.class_a.id, self.lp.id, 1, 7.5, 8.25)
        lesson = Schedule.browse(placed['id'])
        self.assertEqual((lesson.teacher_id, lesson.room_id), (self.teacher, self.room))
        lesson.editor_move(2, 8.25, 9.0)
        self.assertEqual((lesson.weekday, lesson.hour_from), ('2', 8.25))
        with self.assertRaises(ValidationError):
            lesson.editor_move(0, 7.5, 8.25)
        data = Schedule.editor_class_data(self.class_a.id)
        self.assertEqual(next(s for s in data['subjects'] if s['id'] == self.lp.id)['placed'], 1)
        self.assertEqual(data['lessons'][0]['teacher'], self.teacher.name)

        # Por professor: as aulas dele em todas as turmas.
        teacher = Schedule.editor_teacher_data(self.teacher.id)
        self.assertEqual(sorted(lesson['class'] for lesson in teacher['lessons']), ['10ª A · ENF', '10ª B · ENF'])
        self.assertEqual(self.class_a.action_edit_schedule()['context'], {'default_class_id': self.class_a.id})

    def test_teachers_pages(self):
        """Docentes: a troca de professor passa para o horário, os avisos antes de gravar, a ficha e os candidatos a
        director de turma (primeiro quem dá aulas na turma)."""
        Assignment = self.env['edu.teaching.assignment']
        Schedule = self.env['edu.schedule']
        assignment = Assignment.create(
            {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'teacher_id': self.teacher.id}
        )
        lesson = Schedule.create(
            {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'weekday': '0', 'hour_from': 7.5, 'hour_to': 8.25}
        )
        self.assertEqual(lesson.teacher_id, self.teacher)
        assignment.teacher_id = self.teacher2
        self.assertEqual(lesson.teacher_id, self.teacher2)
        # Professor inactivo não se coloca.
        retired = self.env['hr.employee'].create({'name': 'Reformado', 'edu_is_teacher': True, 'active': False})
        with self.assertRaises(ValidationError):
            Assignment.create({'class_id': self.class_b.id, 'subject_id': self.lp.id, 'teacher_id': retired.id})
        # Aviso antes de gravar: a disciplina já tem professor nesta turma.
        draft = Assignment.new({'class_id': self.class_a.id, 'subject_id': self.lp.id, 'teacher_id': self.teacher.id})
        self.assertIn('já é dada por Rita Professora', draft._onchange_teacher_warning()['warning']['message'])
        # Ficha do professor (perfil público): disciplinas, turmas, carga e horário.
        public = self.env['hr.employee.public'].browse(self.teacher2.id)
        self.assertEqual((public.edu_subjects_label, public.edu_class_count), ('Língua Portuguesa', 1))
        self.assertEqual(public.edu_load_label, '1 de 24')
        self.assertIn('10ª A · ENF', public.edu_teaching_html)
        self.assertIn('10ª A · ENF', public.edu_schedule_html)
        # Director de turma: quem dá aulas na turma aparece primeiro e diz o que dá.
        Employee = self.env['hr.employee'].with_context(edu_director_class_id=self.class_a.id)
        found = Employee.name_search('', [('edu_is_teacher', '=', True)])
        self.assertEqual(found[0], (self.teacher2.id, 'Rita Professora · dá Língua Portuguesa'))
        self.class_a.director_id = self.teacher2
        self.assertTrue(self.class_a.director_teaches)
        public.invalidate_recordset()
        self.env['hr.employee'].invalidate_model(['edu_weekly_load_max'])
        self.assertEqual(public.edu_directed_class, '10ª A · ENF')
        self.assertEqual(public.edu_load_max, 22)
        self.assertIn('menos 2 por ser director(a) de turma da 10ª A · ENF', public.edu_load_notes)
        self.assertIn('Matemática', self.class_a.missing_teacher_subjects)
        self.assertIn(self.class_a, self.env['edu.class'].search([('missing_teacher_subjects', '!=', False)]))

    def test_audit_schedule_rules(self):
        """Auditoria da fase 5: professor da colocação do trimestre e da disciplina nova, domingo e trimestre de outro
        ano recusados, o editor mantém a duração e é só da secretaria."""
        Assignment = self.env['edu.teaching.assignment']
        Schedule = self.env['edu.schedule']
        second = self.year.trimester_ids.filtered(lambda t: t.number == 2)
        Assignment.create(
            {
                'class_id': self.class_b.id,
                'subject_id': self.mat.id,
                'teacher_id': self.teacher2.id,
                'trimester_id': second.id,
            }
        )
        placed = Schedule.editor_place(self.class_b.id, self.mat.id, 0, 7.5, 8.25, trimester_id=second.id)
        self.assertEqual(Schedule.browse(placed['id']).teacher_id, self.teacher2)
        # Mudar a disciplina de um tempo: passa ao professor colocado na nova.
        Assignment.create([
            {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'teacher_id': self.teacher.id},
            {'class_id': self.class_a.id, 'subject_id': self.mat.id, 'teacher_id': self.teacher2.id},
        ])  # fmt: skip
        lesson = Schedule.create(
            {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'weekday': '1', 'hour_from': 9.0, 'hour_to': 10.5}
        )
        self.assertEqual(lesson.teacher_id, self.teacher)
        lesson.subject_id = self.mat
        self.assertEqual(lesson.teacher_id, self.teacher2)
        # Arrastar mantém a duração (90 minutos).
        lesson.editor_move(2, 8.0, 8.75)
        self.assertEqual((lesson.weekday, lesson.hour_from, lesson.hour_to), ('2', 8.0, 9.5))
        with self.assertRaisesRegex(ValidationError, 'domingo'):
            lesson.weekday = '6'
        other_year = self.env['edu.academic.year'].create(
            {'name': '2027/2028', 'date_start': date(2027, 9, 1), 'date_end': date(2028, 7, 31)}
        )
        other_year.action_generate_trimesters()
        with self.assertRaisesRegex(ValidationError, 'trimestre'):
            lesson.trimester_id = other_year.trimester_ids[:1]
        # O editor é da secretaria.
        teacher_user = self.env['res.users'].create(
            {
                'name': 'Professor',
                'login': 'prof_editor',
                'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        with self.assertRaises(AccessError):
            Schedule.with_user(teacher_user).editor_options()
