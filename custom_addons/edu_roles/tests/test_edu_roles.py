from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduRoles(TransactionCase):
    """Cada perfil vê só os seus menus e só mexe no que lhe pertence."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def user(login, *groups):
            return cls.env['res.users'].create(
                {'name': login, 'login': login, 'group_ids': [Command.set([cls.env.ref(g).id for g in groups])]}
            )

        cls.clerk = user('secretaria', 'edu_core.group_edu_user')
        cls.cashier = user('tesouraria', 'edu_fees.group_edu_finance')
        cls.teacher_user = user('professor', 'edu_core.group_edu_teacher')
        cls.director = user('direccao', 'edu_core.group_edu_manager')
        cls.teacher = cls.env['hr.employee'].create(
            {'name': 'Professor', 'edu_is_teacher': True, 'user_id': cls.teacher_user.id}
        )
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        course = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': cls.env.ref('edu_core.level_tecnico').id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }  # fmt: skip
        )
        tenth = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 10)
        cls.class_a = cls.env['edu.class'].create({'name': 'A', 'course_id': course.id, 'curriculum_year_id': tenth.id})
        cls.class_b = cls.env['edu.class'].create({'name': 'B', 'course_id': course.id, 'curriculum_year_id': tenth.id})
        lp = cls.class_a.subject_line_ids.subject_id.filtered(lambda s: s.code == 'LP')
        cls.env['edu.teaching.assignment'].create(
            {'class_id': cls.class_a.id, 'subject_id': lp.id, 'teacher_id': cls.teacher.id}
        )
        cls.lp = lp

    def _menus(self, user):
        # Como na interface: um menu só aparece se todos os ascendentes também aparecerem.
        Menu = self.env['ir.ui.menu'].with_user(user)
        ids = Menu._visible_menu_ids()
        shown = Menu.sudo().browse(ids).filtered(lambda m: all(int(i) in ids for i in m.parent_path.split('/')[:-1]))
        return set(shown.get_external_id().values())

    def test_teacher_menus(self):
        menus = self._menus(self.teacher_user)
        for xmlid in ('edu_roles.menu_my_lessons', 'edu_roles.menu_my_classes', 'edu_attendance.menu_edu_lesson',
                      'edu_evaluation.menu_edu_assessment', 'edu_evaluation.menu_edu_subject_result'):  # fmt: skip
            self.assertIn(xmlid, menus)
        for xmlid in ('edu_enrollment.menu_edu_application', 'edu_enrollment.menu_edu_enrollment',
                      'edu_fees.menu_edu_debtors', 'edu_core.menu_edu_config', 'edu_core.menu_edu_academic_year',
                      'edu_exam.menu_edu_exam_period', 'edu_records.menu_edu_graduation', 'hr.menu_hr_root',
                      'base.menu_management', 'contacts.menu_contacts',
                      'spreadsheet_dashboard.spreadsheet_dashboard_menu_root'):  # fmt: skip
            self.assertNotIn(xmlid, menus)

    def test_clerk_and_cashier_menus(self):
        clerk = self._menus(self.clerk)
        self.assertIn('edu_enrollment.menu_edu_application', clerk)
        self.assertIn('edu_records.menu_edu_graduation', clerk)
        self.assertNotIn('edu_fees.menu_edu_debtors', clerk)
        self.assertNotIn('edu_core.menu_edu_config', clerk)
        self.assertNotIn('edu_roles.menu_my_lessons', clerk)
        cashier = self._menus(self.cashier)
        self.assertIn('edu_fees.menu_edu_debtors', cashier)
        self.assertIn('edu_fees.menu_edu_fee_students', cashier)
        self.assertNotIn('edu_enrollment.menu_edu_application', cashier)
        self.assertNotIn('edu_evaluation.menu_edu_assessment', cashier)
        director = self._menus(self.director)
        for xmlid in ('edu_core.menu_edu_config', 'edu_fees.menu_edu_debtors', 'edu_enrollment.menu_edu_application'):
            self.assertIn(xmlid, director)

    def test_data_access(self):
        # A secretaria não factura nem recebe; a tesouraria não mexe nas matrículas nem nas aulas.
        self.assertFalse(self.clerk.has_group('account.group_account_invoice'))
        self.assertTrue(self.cashier.has_group('account.group_account_invoice'))
        with self.assertRaises(AccessError):
            self.env['account.move'].with_user(self.clerk).check_access('create')
        with self.assertRaises(AccessError):
            self.env['edu.application'].with_user(self.cashier).search([])
        with self.assertRaises(AccessError):
            self.env['edu.lesson'].with_user(self.cashier).search([])
        with self.assertRaises(AccessError):
            self.env['edu.application'].with_user(self.teacher_user).search([])
        # O professor só cria aulas das suas disciplinas e só vê as suas turmas em «As minhas turmas».
        Lesson = self.env['edu.lesson'].with_user(self.teacher_user)
        Lesson.create({'class_id': self.class_a.id, 'subject_id': self.lp.id, 'date': date(2026, 9, 7)})
        with self.assertRaises(AccessError):
            Lesson.create({'class_id': self.class_b.id, 'subject_id': self.lp.id, 'date': date(2026, 9, 7)})
        action = self.env.ref('edu_roles.action_my_classes')
        mine = (
            self.env['edu.class']
            .with_user(self.teacher_user)
            .search(eval(action.domain, {'uid': self.teacher_user.id}))
        )
        self.assertEqual(mine, self.class_a)
