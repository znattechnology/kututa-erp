from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduCore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.technical = cls.env.ref('edu_core.level_tecnico')
        cls.nursing = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.technical.id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }
        )

    def test_national_calendar(self):
        """Calendário Escolar Nacional 2026/2027 (DE n.º 8212/2026) carregado na escola, que o pode editar."""
        self.year.action_load_national_calendar()
        events = self.year.calendar_event_ids
        self.assertGreater(len(events), 100)
        phases = set(events.mapped('phase'))
        self.assertLessEqual({'application', 'selection_test', 'enrollment', 'confirmation'}, phases)
        test = events.filtered(lambda e: e.phase == 'selection_test')
        self.assertIn(self.technical, test.level_ids)
        # A escola altera um evento; ao carregar de novo, a alteração fica.
        enrollment = events.filtered(lambda e: e.phase == 'enrollment')[:1]
        enrollment.date_end = enrollment.date_end.replace(day=27)
        self.assertTrue(enrollment.edited)
        self.year.action_load_national_calendar()
        self.assertEqual(enrollment.date_end.day, 27)
        self.assertEqual(len(self.year.calendar_event_ids), len(events))
        start, end = self.env['edu.calendar.event']._phase_window('enrollment', around=enrollment.date_start)
        self.assertEqual((start, end), (enrollment.date_start, enrollment.date_end))

    def test_academic_year(self):
        self.year.action_generate_trimesters()
        trimesters = self.year.trimester_ids.sorted('number')
        self.assertEqual(trimesters.mapped('number'), [1, 2, 3])
        self.assertEqual(trimesters[0].name, '1º Trimestre')
        self.assertEqual(trimesters[0].date_start, self.year.date_start)
        self.assertEqual(trimesters[-1].date_end, self.year.date_end)
        self.assertEqual(self.company.edu_current_year_id, self.year)
        with self.assertRaises(UserError):
            self.year.action_generate_trimesters()
        with self.assertRaises(ValidationError):
            self.env['edu.academic.year'].create(
                {'name': 'Sobreposto', 'date_start': date(2027, 7, 1), 'date_end': date(2028, 6, 30)}
            )
        nxt = self.env['edu.academic.year'].create(
            {'name': '2027/2028', 'date_start': date(2027, 9, 1), 'date_end': date(2028, 7, 31)}
        )
        nxt.action_set_current()
        self.assertFalse(self.year.is_current)
        self.assertEqual(self.company.edu_current_year_id, nxt)

    def test_trimester_close(self):
        self.year.action_generate_trimesters()
        first = self.year.trimester_ids.filtered(lambda t: t.number == 1)
        second = self.year.trimester_ids.filtered(lambda t: t.number == 2)
        with self.assertRaises(UserError):
            second.action_close()  # fecham-se por ordem
        first.action_close()
        self.assertEqual(first.state, 'closed')
        self.assertEqual(first.closed_by_id, self.env.user)
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretária',
                'login': 'secretaria_edu',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        with self.assertRaises(UserError):
            first.with_user(clerk).action_reopen()
        first.action_reopen()
        self.assertEqual(first.state, 'open')
        with self.assertRaises(ValidationError):
            first.date_end = date(2027, 8, 15)

    def test_course_curriculum(self):
        curriculum = self.nursing.curriculum_id
        self.assertTrue(curriculum.is_national)
        self.assertEqual(self.nursing.duration_years, 4)
        self.assertEqual(curriculum.name, 'Plano Nacional — Técnico de Enfermagem')
        self.assertEqual((curriculum.class_from, curriculum.class_to), (10, 13))
        tenth = curriculum.year_ids.filtered(lambda y: y.class_number == 10)
        codes = tenth.line_ids.mapped('code')
        # Tronco comum (LP, MAT, INF na 10ª) mais o perfil de enfermagem (BIO, TENF).
        for code in ('LP', 'MAT', 'INF', 'BIO', 'TENF'):
            self.assertIn(code, codes)
        lp = tenth.line_ids.filtered(lambda line: line.code == 'LP')
        self.assertEqual(lp.subject_id.name, 'Língua Portuguesa')
        self.assertEqual(lp.component, 'socio_cultural')
        # A matriz do plano: as componentes como títulos, as disciplinas por baixo e o total de cada classe.
        matrix = self.nursing.plan_matrix
        for text in ('Sociocultural', 'Científica', 'Língua Portuguesa', 'Tempos por semana', '10ª', '13ª'):
            self.assertIn(text, matrix)
        self.assertLess(matrix.index('Sociocultural'), matrix.index('Língua Portuguesa'))
        self.assertLess(matrix.index('Língua Portuguesa'), matrix.index('Científica'))
        # Gerar outra vez não duplica.
        self.assertEqual(self.nursing._materialize_curriculum(), curriculum)
        # Outro curso reutiliza as disciplinas da escola pelo código.
        accounting = self.env['edu.course'].create(
            {
                'name': 'Técnico de Contabilidade',
                'code': 'CONT',
                'level_id': self.technical.id,
                'curriculum_template_id': self.env.ref('edu_core.tpl_tec_contab').id,
            }
        )
        self.assertEqual(self.env['edu.subject'].search_count([('code', '=', 'LP')]), 1)
        self.assertIn(lp.subject_id, accounting.curriculum_id.line_ids.subject_id)

    def test_level_plan(self):
        action = self.env.ref('edu_core.level_primario').action_materialize_plan()
        curriculum = self.env['edu.curriculum'].browse(action['res_id'])
        self.assertFalse(curriculum.course_id)
        self.assertEqual((curriculum.class_from, curriculum.class_to), (1, 6))
        self.assertEqual(curriculum.year_ids[0].name, '1ª Classe')
        self.assertFalse(self.env.ref('edu_core.level_iniciacao').action_materialize_plan())

    def test_no_materialize_context(self):
        course = (
            self.env['edu.course']
            .with_context(edu_no_materialize=True)
            .create({'name': 'Migrado', 'code': 'MIG', 'level_id': self.technical.id})
        )
        self.assertFalse(course.curriculum_ids)

    def test_class(self):
        curriculum = self.nursing.curriculum_id
        tenth = curriculum.year_ids.filtered(lambda y: y.class_number == 10)
        room = self.env['edu.room'].create({'name': 'Sala 1', 'code': 'S1'})
        morning = self.env['edu.shift'].create({'name': 'Manhã', 'hour_from': 7.5, 'hour_to': 12.5})
        edu_class = self.env['edu.class'].create(
            {
                'name': 'A',
                'course_id': self.nursing.id,
                'curriculum_year_id': tenth.id,
                'room_id': room.id,
                'shift_id': morning.id,
            }
        )
        self.assertEqual(edu_class.academic_year_id, self.year)
        self.assertEqual(edu_class.curriculum_id, curriculum)
        self.assertEqual(edu_class.class_number, 10)
        self.assertEqual(edu_class.display_name, '10ª A · ENF · 2026/2027')
        self.assertIn(edu_class.id, [r[0] for r in self.env['edu.class'].name_search('10ª A')])
        self.assertIn(edu_class.id, [r[0] for r in self.env['edu.class'].name_search('ENF')])
        self.assertIn('TENF', edu_class.subject_line_ids.mapped('code'))
        with self.assertRaisesRegex(ValidationError, 'Sala 1'):
            self.env['edu.class'].create(
                {
                    'name': 'B',
                    'course_id': self.nursing.id,
                    'class_number': 10,
                    'room_id': room.id,
                    'shift_id': morning.id,
                }  # fmt: skip
            )
        with self.assertRaises(ValidationError):
            self.env['edu.class'].create({'name': 'C', 'course_id': self.nursing.id, 'class_number': 7})

    def test_class_list_opens_on_current_year(self):
        # A lista de turmas abre no ano em curso; o painel dos anos lectivos deixa escolher outro.
        action = self.env['edu.class'].action_open_classes()
        self.assertEqual(action['res_model'], 'edu.class')
        self.assertEqual(action['context']['searchpanel_default_academic_year_id'], self.year.id)
        self.assertEqual(self.env.ref('edu_core.menu_edu_class').action, self.env.ref('edu_core.action_edu_class_open'))
        search = self.env['edu.class'].get_views([(False, 'search')])['views']['search']['arch']
        self.assertIn('<searchpanel', search)

    def test_subject_prerequisites(self):
        subjects = self.nursing.curriculum_id.line_ids.subject_id
        first, second = subjects[:2]
        second.prerequisite_ids = first
        with self.assertRaises(ValidationError):
            first.prerequisite_ids = second
