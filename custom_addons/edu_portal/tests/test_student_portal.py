from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.addons.edu_fees.models.edu_standing import EduStudent
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestStudentPortal(HttpCase):
    """A área do estudante: cada aluno vê só o que é seu, e as notas como na pauta."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.t1 = cls.year.trimester_ids.sorted('number')[0]
        cls.t1.is_current = True
        course = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.env.ref('edu_core.level_tecnico').id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }  # fmt: skip
        )
        tenth = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 10)
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': course.id, 'curriculum_year_id': tenth.id}
        )
        cls.lp = cls.edu_class.subject_line_ids.subject_id.filtered(lambda s: s.code == 'LP')
        teacher_user = cls.env['res.users'].create(
            {
                'name': 'Professor',
                'login': 'prof_portal',
                'group_ids': [Command.set([cls.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        teacher = cls.env['hr.employee'].create(
            {'name': 'Professor', 'edu_is_teacher': True, 'user_id': teacher_user.id}
        )
        cls.env['edu.teaching.assignment'].create(
            {'class_id': cls.edu_class.id, 'subject_id': cls.lp.id, 'teacher_id': teacher.id}
        )
        cls.ana = cls.env['edu.student'].create({'name': 'Ana Portal', 'email': 'ana.portal@example.com'})
        cls.bento = cls.env['edu.student'].create({'name': 'Bento Vizinho'})
        cls.enrollments = cls.env['edu.enrollment']
        for student in (cls.ana, cls.bento):
            enrollment = cls.env['edu.enrollment'].create({'student_id': student.id, 'class_id': cls.edu_class.id})
            enrollment.action_confirm()
            cls.enrollments |= enrollment
        Grid = cls.env['edu.grade.grid'].with_user(teacher_user)
        ana_e, bento_e = cls.enrollments
        result = Grid.grid_save(
            cls.edu_class.id,
            cls.lp.id,
            [
                {'enrollment_id': ana_e.id, 'trimester_id': cls.t1.id, 'column': 'npp', 'value': 14},
                {'enrollment_id': ana_e.id, 'trimester_id': cls.t1.id, 'column': 'npt', 'value': 12},
                {'enrollment_id': bento_e.id, 'trimester_id': cls.t1.id, 'column': 'npp', 'value': 4},
                {'enrollment_id': bento_e.id, 'trimester_id': cls.t1.id, 'column': 'npt', 'value': 6},
            ],
        )
        assert result['ok'], result
        cls.ana_user = cls.env['res.users'].create(
            {
                'name': 'Ana Portal',
                'login': 'ana_portal',
                'password': 'ana_portal_pw_123',
                'partner_id': cls.ana.partner_id.id,
                'group_ids': [Command.set([cls.env.ref('edu_portal.group_edu_student').id])],
            }
        )

    def test_grades_data(self):
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        data = Portal.page_data('grades')
        self.assertEqual(data['name'], 'Ana Portal')
        grades = data['grades']
        self.assertTrue(grades['technical'])
        self.assertEqual(grades['active']['id'], self.t1.id)
        row = next(r for r in grades['subjects'] if r['id'] == self.lp.id)
        cell = row['by_trimester'][self.t1.id]
        self.assertEqual([cell[k]['text'] for k in ('mac', 'npt', 'ct')], ['14', '12', '13'])
        self.assertTrue(cell['ct']['pos'])
        # No técnico, o último trimestre não tem NPT.
        self.assertFalse(grades['trimesters'][-1]['has_npt'])
        self.assertIn('média de 13', grades['summary'])

    def test_grades_of_past_years(self):
        """As notas dos anos anteriores (as migradas do secPed): escolhe-se o ano; uma matrícula de outro aluno não."""
        past_year = self.env['edu.academic.year'].create(
            {'name': '2025/2026', 'date_start': date(2025, 9, 1), 'date_end': date(2026, 7, 31)}
        )
        past_year.action_generate_trimesters()
        past_t1 = past_year.trimester_ids.sorted('number')[0]
        past_class = self.env['edu.class'].create(
            {
                'name': 'A',
                'course_id': self.edu_class.course_id.id,
                'curriculum_year_id': self.edu_class.curriculum_year_id.id,
                'academic_year_id': past_year.id,
            }
        )
        past = self.env['edu.enrollment'].create({'student_id': self.ana.id, 'class_id': past_class.id})
        past.sudo().state = 'completed'
        self.env['edu.term.result'].create(
            {
                'enrollment_id': past.id,
                'subject_id': self.lp.id,
                'trimester_id': past_t1.id,
                'mac': 15,
                'npt': 15,
                'mt': 15,
                'has_mac': True,
                'has_npt': True,
                'has_mt': True,
                'imported': True,
            }  # fmt: skip
        )
        self.env['edu.subject.result']._recompute_keys([(past.id, self.lp.id)])
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        grades = Portal.page_data('grades')['grades']
        self.assertEqual(grades['enrollment_id'], self.enrollments[0].id, 'abre no ano corrente')
        self.assertEqual([y['id'] for y in grades['years']], [self.enrollments[0].id, past.id])
        grades = Portal.page_data('grades', {'enrollment_id': past.id})['grades']
        self.assertTrue(grades['past'])
        self.assertEqual(grades['year'], '2025/2026')
        row = next(r for r in grades['subjects'] if r['id'] == self.lp.id)
        self.assertEqual(row['by_trimester'][past_t1.id]['ct']['text'], '15')
        self.assertIn('tiveste', grades['summary'])
        # A matrícula de outro aluno não se abre: fica o ano corrente do próprio aluno.
        bento = Portal.page_data('grades', {'enrollment_id': self.enrollments[1].id})['grades']
        self.assertEqual(bento['enrollment_id'], self.enrollments[0].id)

    def test_pages_and_privacy(self):
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        for page in ('home', 'grades', 'schedule', 'exams', 'absences', 'fees', 'profile'):
            with self.subTest(page=page):
                data = Portal.page_data(page)
                self.assertTrue(data['has_student'])
                self.assertNotIn('Bento Vizinho', str(data))
        # O aluno não lê os modelos da escola nem os contactos dos outros alunos.
        with self.assertRaises(AccessError):
            self.env['edu.subject.result'].with_user(self.ana_user).search([])
        # Os documentos de matrícula: só os seus.
        Document = self.env['edu.enrollment.document']
        Type = self.env['edu.enrollment.document.type']
        doc_type = Type.search([], limit=1) or Type.create({'name': 'Cópia do BI'})
        mine = Document.create({'enrollment_id': self.enrollments[0].id, 'type_id': doc_type.id})
        other = Document.create({'enrollment_id': self.enrollments[1].id, 'type_id': doc_type.id})
        visible = Document.with_user(self.ana_user).search([('id', 'in', (mine | other).ids)])
        self.assertEqual(visible, mine)
        Partner = self.env['res.partner'].with_user(self.ana_user)
        self.assertFalse(Partner.search([('id', '=', self.bento.partner_id.id)]))
        self.assertTrue(Partner.search([('id', '=', self.ana.partner_id.id)]))
        # O menu: só a sua área, sem as Discussões.
        roots = self.env['ir.ui.menu'].with_user(self.ana_user).load_menus(False)['root']['children']
        self.assertIn(self.env.ref('edu_portal.menu_student_root').id, roots)
        self.assertNotIn(self.env.ref('mail.menu_root_discuss').id, roots)

    def test_schedule_report(self):
        """O horário da turma em A4, como o do professor: na aplicação ou em PDF."""
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        action = Portal.schedule_report(True)
        self.assertEqual(action['report_type'], 'qweb-html')
        self.assertEqual(action['context']['active_ids'], self.edu_class.ids)
        Report = self.env['ir.actions.report'].with_user(self.ana_user)
        html = Report._render_qweb_html('edu_documents.report_class_schedule', self.edu_class.ids)[0].decode()
        self.assertIn('HORÁRIO DA TURMA', html)
        self.assertEqual(Portal.schedule_report(False)['report_type'], 'qweb-pdf')

    def test_grades_blocked_by_fees(self):
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        with patch.object(EduStudent, '_edu_gate', lambda student, point: (point == 'grades', 'Dívida')):
            grades = Portal.page_data('grades')['grades']
        self.assertTrue(grades['blocked'])
        self.assertFalse(grades['subjects'])

    def test_user_without_student(self):
        user = self.env['res.users'].create(
            {
                'name': 'Sem ficha',
                'login': 'sem_ficha',
                'group_ids': [Command.set([self.env.ref('edu_portal.group_edu_student').id])],
            }
        )
        self.assertFalse(self.env['edu.student.portal'].with_user(user).page_data('home')['has_student'])
