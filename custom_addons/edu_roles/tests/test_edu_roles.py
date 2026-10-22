from datetime import date

from lxml import etree

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

    def test_class_documents_without_hr_access(self):
        # A secretaria e o professor imprimem os documentos da turma sem acesso às fichas do RH (o cargo de quem
        # assina usa o sexo do director de turma, que é um campo do RH).
        self.teacher.sex = 'female'
        self.class_a.director_id = self.teacher
        Report = self.env['ir.actions.report']
        for user in (self.clerk, self.teacher_user):
            Wizard = self.env['edu.pauta.print'].with_user(user)
            final = Wizard.create({'class_id': self.class_a.id, 'kind': 'final'})
            mini = Wizard.create({'class_id': self.class_a.id, 'kind': 'mini', 'subject_id': self.lp.id})
            documents = (
                ('edu_documents.report_pauta', final.ids),
                ('edu_documents.report_mini_pauta', mini.ids),
                ('edu_documents.report_class_list', self.class_a.ids),
                ('edu_documents.report_class_schedule', self.class_a.ids),
            )
            for report_name, ids in documents:
                with self.subTest(user=user.login, report=report_name):
                    html = Report.with_user(user)._render_qweb_html(report_name, ids)[0].decode()
                    if report_name == 'edu_documents.report_pauta':
                        self.assertIn('A Directora de Turma', html)
                    elif report_name == 'edu_documents.report_mini_pauta':
                        self.assertIn('Directora de Turma', html)
                    elif report_name == 'edu_documents.report_class_schedule':
                        self.assertIn('HORÁRIO DA TURMA', html)
                    elif report_name != 'edu_documents.report_class_list':
                        self.assertIn('A DIRECTORA DE TURMA', html)

    def _menus(self, user):
        # Como na interface: um menu só aparece se todos os ascendentes também aparecerem.
        Menu = self.env['ir.ui.menu'].with_user(user)
        ids = Menu._visible_menu_ids()
        shown = Menu.sudo().browse(ids).filtered(lambda m: all(int(i) in ids for i in m.parent_path.split('/')[:-1]))
        return set(shown.get_external_id().values())

    def test_teacher_menus(self):
        menus = self._menus(self.teacher_user)
        # O professor tem o seu painel (como a secretaria tem a Secretaria Express), com o conselho de turma, que é do
        # director de turma; não vê os menus da secretaria.
        for xmlid in ('edu_roles.menu_edu_teacher_root', 'edu_roles.menu_my_lessons', 'edu_roles.menu_my_classes',
                      'edu_roles.menu_my_assessments', 'edu_evaluation.menu_edu_council_session',
                      'edu_roles.menu_teacher_absences'):  # fmt: skip
            self.assertIn(xmlid, menus)
        self.assertNotIn('edu_core.menu_edu_root', menus)
        self.assertEqual(
            self.env.ref('edu_evaluation.menu_edu_council_session').parent_id,
            self.env.ref('edu_roles.menu_teacher_direction'),
        )
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
        # Menu do secPed (ADMIN_SERVICOS): configuração académica, docentes, cartões, encarregados…
        for xmlid in ('edu_roles.menu_section_config', 'edu_core.menu_edu_academic_year',
                      'edu_roles.menu_edu_trimester', 'edu_core.menu_edu_course', 'edu_core.menu_edu_subject',
                      'edu_people.menu_edu_teacher',
                      'edu_roles.menu_edu_class_directors', 'edu_roles.menu_edu_enrollment_new',
                      'edu_roles.menu_edu_enrollment_dropped', 'edu_roles.menu_edu_student_cards',
                      'edu_roles.menu_edu_student_history', 'edu_roles.menu_edu_internship_new',
                      'edu_roles.menu_edu_student_guardian'):  # fmt: skip
            self.assertIn(xmlid, clerk)
        self.assertEqual(
            self.env.ref('edu_core.menu_edu_academic_year').parent_id, self.env.ref('edu_roles.menu_section_config')
        )
        # A secretaria altera a configuração académica, mas não a apaga.
        year = self.env['edu.academic.year'].with_user(self.clerk)
        self.assertTrue(year.has_access('write'))
        self.assertFalse(year.has_access('unlink'))
        cashier = self._menus(self.cashier)
        self.assertIn('edu_fees.menu_edu_debtors', cashier)
        # A tesouraria consulta os alunos no mesmo menu da secretaria (um só «Alunos» para a direcção).
        self.assertIn('edu_people.menu_edu_student', cashier)
        self.assertNotIn('edu_enrollment.menu_edu_application', cashier)
        self.assertNotIn('edu_evaluation.menu_edu_assessment', cashier)
        director = self._menus(self.director)
        for xmlid in ('edu_core.menu_edu_config', 'edu_fees.menu_edu_debtors', 'edu_enrollment.menu_edu_application'):
            self.assertIn(xmlid, director)

    def test_default_app(self):
        # Sem acção inicial, o Odoo abre a primeira aplicação do menu: tem de ser a Secretaria Express, não o chat.
        root = self.env.ref('edu_core.menu_edu_root').id
        for user in (self.clerk, self.cashier, self.director):
            menus = self.env['ir.ui.menu'].with_user(user).load_menus(False)
            self.assertEqual(menus['root']['children'][0], root, user.login)
        # O professor entra no Painel do Professor.
        menus = self.env['ir.ui.menu'].with_user(self.teacher_user).load_menus(False)
        self.assertEqual(menus['root']['children'][0], self.env.ref('edu_roles.menu_edu_teacher_root').id)
        # Sem turmas de iniciação (uma escola técnica), o RDEC não aparece.
        rdec = self.env.ref('edu_roles.menu_teacher_rdec').id
        if not self.env['edu.class'].search_count([('level_id.code', '=', 'INICIACAO')]):
            self.assertNotIn(rdec, menus)

    def test_teacher_fields_without_hr(self):
        # Sem acesso ao RH, os funcionários lêem-se pelo perfil público: os campos de professor têm de lá estar.
        fields = ['name', 'edu_is_teacher', 'edu_specialization', 'edu_coordination_id', 'edu_subject_ids']
        for user in (self.clerk, self.teacher_user):
            values = self.env['hr.employee'].with_user(user).browse(self.teacher.id).read(fields)[0]
            self.assertTrue(values['edu_is_teacher'], user.login)
        form = self.env['edu.class'].with_user(self.clerk).browse(self.class_a.id)
        form.web_read({'director_id': {'fields': {'edu_is_teacher': {}}}, 'assignment_ids': {'fields': {
            'teacher_id': {'fields': {'edu_specialization': {}, 'edu_coordination_id': {}}}}}})  # fmt: skip

    @staticmethod
    def _spec(node, model):
        """Campos de uma vista (com os das sub-listas), como o cliente web os pede."""
        spec = {}
        for field in node.iterchildren():
            if field.tag != 'field':
                spec.update(TestEduRoles._spec(field, model))
                continue
            name = field.get('name')
            if name not in model._fields:
                continue
            sub = next((v for v in field.iterchildren() if v.tag in ('list', 'form', 'kanban')), None)
            comodel = model.env.get(model._fields[name].comodel_name) if model._fields[name].relational else None
            spec[name] = {'fields': TestEduRoles._spec(sub, comodel)} if sub is not None and comodel is not None else {}
        return spec

    def test_menus_open_without_access_errors(self):
        # Cada perfil abre a lista e a ficha de todos os menus que vê, com os campos das próprias vistas.
        checked = 0
        for user in (self.clerk, self.cashier, self.teacher_user, self.director):
            Menu = self.env['ir.ui.menu'].with_user(user)
            ids = Menu._visible_menu_ids()
            for menu in Menu.sudo().browse(ids):
                action = menu.action
                if not action or action._name != 'ir.actions.act_window' or not action.res_model.startswith('edu.'):
                    continue
                if not all(int(i) in ids for i in menu.parent_path.split('/')[:-1]):
                    continue
                Model = self.env[action.res_model].with_user(user)
                views = Model.get_views([(False, 'list'), (False, 'form')])['views']
                for kind in ('list', 'form'):
                    spec = self._spec(etree.fromstring(views[kind]['arch']), Model)
                    with self.subTest(user=user.login, menu=menu.complete_name, view=kind):
                        Model.web_search_read([], spec, limit=1)
                        Model.search([], limit=1).web_read(spec)
                        checked += 1
        self.assertGreater(checked, 50)

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
