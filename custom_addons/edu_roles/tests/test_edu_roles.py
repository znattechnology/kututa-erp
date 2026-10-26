from datetime import date, timedelta

from lxml import etree

from odoo import Command, fields
from odoo.addons.edu_roles.models.edu_attendance_page import absence_limit_of
from odoo.exceptions import AccessError, UserError
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
        # O professor tem o seu painel, com o menu do secPed: a mini-pauta, o conselho de turma, a justificação de
        # faltas, a MAC e o RDEC abrem-se dentro da turma, em «Turmas e notas».
        for xmlid in ('edu_roles.menu_edu_teacher_root', 'edu_roles.menu_teacher_grade_grid',
                      'edu_roles.menu_my_schedule', 'edu_roles.menu_my_supervisions', 'edu_roles.menu_teacher_calendar',
                      'edu_roles.menu_my_lessons',
                      'edu_roles.menu_teacher_absence_summary', 'edu_roles.menu_teacher_messages',
                      'edu_roles.menu_teacher_profile'):  # fmt: skip
            self.assertIn(xmlid, menus)
        self.assertNotIn('edu_core.menu_edu_root', menus)
        self.assertNotIn('edu_evaluation.menu_edu_council_session', menus)
        roots = self.env['ir.ui.menu'].with_user(self.teacher_user).load_menus(False)['root']['children']
        self.assertEqual(roots, [self.env.ref('edu_roles.menu_edu_teacher_root').id], 'só o painel, sem Discussões')
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
        # A tesouraria tem a sua aplicação, com a barra lateral do secPed; não vê o menu da secretaria.
        cashier = self._menus(self.cashier)
        for xmlid in ('edu_roles.menu_treasury_home', 'edu_roles.menu_treasury_students',
                      'edu_fees.menu_edu_payment_requests', 'edu_fees.menu_edu_invoices',
                      'edu_roles.menu_treasury_receipts', 'edu_roles.menu_treasury_agt',
                      'edu_fees.menu_edu_fee_plan', 'edu_fees.menu_edu_late_fee_rule'):  # fmt: skip
            self.assertIn(xmlid, cashier)
        for xmlid in ('edu_core.menu_edu_root', 'edu_people.menu_edu_student', 'edu_enrollment.menu_edu_application',
                      'edu_evaluation.menu_edu_assessment', 'edu_fees.menu_edu_debtors'):  # fmt: skip
            self.assertNotIn(xmlid, cashier)
        self.assertNotIn('edu_roles.menu_treasury_root', clerk)
        director = self._menus(self.director)
        for xmlid in (
            'edu_core.menu_edu_config',
            'edu_roles.menu_treasury_students',
            'edu_enrollment.menu_edu_application',
        ):
            self.assertIn(xmlid, director)

    def test_default_app(self):
        # Sem acção inicial, o Odoo abre a primeira aplicação do menu: tem de ser a Secretaria Express, não o chat.
        root = self.env.ref('edu_core.menu_edu_root').id
        for user in (self.clerk, self.director):
            menus = self.env['ir.ui.menu'].with_user(user).load_menus(False)
            self.assertEqual(menus['root']['children'][0], root, user.login)
        # A tesouraria entra na Tesouraria.
        menus = self.env['ir.ui.menu'].with_user(self.cashier).load_menus(False)
        self.assertEqual(menus['root']['children'][0], self.env.ref('edu_roles.menu_treasury_root').id)
        # O professor entra no Painel do Professor.
        menus = self.env['ir.ui.menu'].with_user(self.teacher_user).load_menus(False)
        self.assertEqual(menus['root']['children'][0], self.env.ref('edu_roles.menu_edu_teacher_root').id)

    def test_treasury_pages(self):
        """A tesouraria: o painel, «Facturar e receber» por turma e a ficha financeira; só para a tesouraria."""
        student = self.env['edu.student'].create({'name': 'Aluno da tesouraria'})
        enrollment = self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': self.class_a.id})
        enrollment.action_confirm()
        Treasury = self.env['edu.treasury'].with_user(self.cashier)
        home = Treasury.home_data()
        self.assertEqual(len(home['monthly']), 6)
        self.assertEqual(home['overdue_count'], 0)
        classes = Treasury.classes()['classes']
        self.assertIn(self.class_a.id, [c['id'] for c in classes])
        rows = Treasury.students(self.class_a.id, False, '')['rows']
        self.assertIn(student.id, [r['student_id'] for r in rows])
        self.assertFalse(Treasury.students(False, False, '')['rows'], 'sem turma nem pesquisa: escolher primeiro')
        data = Treasury.student_data(student.id)
        self.assertEqual((data['student']['name'], data['open'], data['documents']), (student.name, [], []))
        action = Treasury.student_action(student.id, 'receive', [])
        self.assertEqual((action['res_model'], action['views']), ('edu.fee.payment', [(False, 'form')]))
        with self.assertRaises(AccessError):
            self.env['edu.treasury'].with_user(self.clerk).home_data()

    def test_attendance_page(self):
        """«Presenças», como no secPed: a chamada começa com todos presentes mas só fica registada quando se guarda;
        com o sumário, a aula fica dada. Só o director de turma justifica."""
        self.year.action_generate_trimesters()
        self.year.trimester_ids.sorted('number')[0].is_current = True
        student = self.env['edu.student'].create({'name': 'Aluno da chamada'})
        enrollment = self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': self.class_a.id})
        enrollment.action_confirm()
        Page = self.env['edu.attendance.page'].with_user(self.teacher_user)
        options = Page.options()
        self.assertIn(self.class_a.id, [c['id'] for c in options['classes']])
        day = self.year.trimester_ids.sorted('number')[0].date_start
        lesson = Page.new_lesson(
            self.class_a.id, self.lp.id, {'date': fields.Date.to_string(day), 'hour_from': 8.0, 'hour_to': 9.0}
        )
        roll = Page.roll(lesson['id'])
        self.assertFalse(roll['saved'])
        row = next(r for r in roll['rows'] if r['enrollment_id'] == enrollment.id)
        self.assertEqual((row['state'], row['can_justify']), ('present', False))
        # Sem sumário: a chamada fica guardada, a aula ainda não está dada.
        saved = Page.save(lesson['id'], [dict(row, state='absent')], '')
        self.assertTrue(saved['saved'])
        self.assertFalse(saved['done'])
        self.assertEqual(Page.lessons(self.class_a.id, self.lp.id)[0]['roll_saved'], True)
        # Justificar é do director de turma.
        with self.assertRaises(AccessError):
            Page.save(lesson['id'], [dict(row, state='excused', justification='Doença')], '')
        done = Page.save(lesson['id'], [dict(row, state='late')], 'Revisão do capítulo 3')
        self.assertTrue(done['done'])
        self.assertEqual(done['lesson']['state'], 'done')
        line = self.env['edu.lesson.attendance'].search([('enrollment_id', '=', enrollment.id)])
        self.assertEqual(line.state, 'late')
        # A mesma aula outra vez não se duplica.
        self.assertTrue(
            Page.new_lesson(
                self.class_a.id, self.lp.id, {'date': fields.Date.to_string(day), 'hour_from': 8.0, 'hour_to': 9.0}
            )['existed']
        )
        # Outra turma, onde não dá aulas nem é director: recusada.
        with self.assertRaises(AccessError):
            Page.lessons(self.class_b.id, self.lp.id)
        # Uma aula futura não recebe chamada (a chamada faz-se no próprio dia).
        tomorrow = fields.Date.context_today(Page) + timedelta(days=1)
        future = None
        if tomorrow <= self.year.date_end:
            future = self.env['edu.lesson'].create(
                {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'date': tomorrow, 'hour_from': 8.0,
                 'hour_to': 9.0}
            )  # fmt: skip
        if future:
            self.assertTrue(Page.roll(future.id)['future'])
            with self.assertRaises(UserError):
                Page.save(future.id, [dict(row, state='absent')], '')
        # Uma falta justificada não fica sem motivo (como director da turma).
        self.class_a.director_id = self.teacher
        Page.save(lesson['id'], [dict(row, state='excused', justification='Doença')], 'Revisão do capítulo 3')
        with self.assertRaises(UserError):
            Page.save(lesson['id'], [dict(row, state='excused', justification='')], 'Revisão do capítulo 3')
        # Uma aula marcada como não realizada não se volta a registar por «Registar outra aula».
        self.env['edu.lesson'].browse(lesson['id']).sudo().with_context(edu_lesson_system=True).state = 'cancelled'
        with self.assertRaises(UserError):
            Page.new_lesson(
                self.class_a.id, self.lp.id, {'date': fields.Date.to_string(day), 'hour_from': 8.0, 'hour_to': 9.0}
            )

    def test_secretaria_dashboard(self):
        """O painel da secretaria: o que está por tratar (com a lista onde se resolve), os números e as turmas. O
        professor não o abre."""
        self.year.action_generate_trimesters()
        self.year.trimester_ids.sorted('number')[0].is_current = True
        student = self.env['edu.student'].create({'name': 'Aluno do painel'})
        self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': self.class_a.id}).action_confirm()
        Home = self.env['edu.secretaria.home'].with_user(self.clerk)
        data = Home.home_data()
        self.assertEqual(data['kpis']['students'], 1)
        self.assertEqual(data['kpis']['classes'], 2)
        pending = {p['key']: p['count'] for p in data['pending']}
        self.assertEqual(pending.get('directors'), 2, 'as duas turmas ainda sem director de turma')
        row = next(r for r in data['classes'] if r['id'] == self.class_a.id)
        self.assertEqual((row['students'], row['capacity']), (1, self.class_a.capacity))
        self.assertTrue(row['expected'])
        self.assertEqual(Home.open('directors')['res_model'], 'edu.class')
        self.assertEqual(Home.open('students')['res_model'], 'edu.enrollment')
        with self.assertRaises(AccessError):
            self.env['edu.secretaria.home'].with_user(self.teacher_user).home_data()

    def test_teacher_dashboard(self):
        """O painel do professor: as notas do trimestre em cada turma e disciplina e os números principais."""
        self.year.action_generate_trimesters()
        trimester = self.year.trimester_ids.sorted('number')[0]
        trimester.is_current = True
        for name in ('Aluna positiva', 'Aluno negativo', 'Aluno sem nota'):
            student = self.env['edu.student'].create({'name': name})
            self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': self.class_a.id}).action_confirm()
        enrollments = self.class_a.enrollment_ids.sorted('id')
        Grid = self.env['edu.grade.grid'].with_user(self.teacher_user)
        result = Grid.grid_save(
            self.class_a.id,
            self.lp.id,
            [
                {'enrollment_id': enrollments[0].id, 'trimester_id': trimester.id, 'column': 'npp', 'value': 14},
                {'enrollment_id': enrollments[0].id, 'trimester_id': trimester.id, 'column': 'npt', 'value': 12},
                {'enrollment_id': enrollments[1].id, 'trimester_id': trimester.id, 'column': 'npp', 'value': 6},
                {'enrollment_id': enrollments[1].id, 'trimester_id': trimester.id, 'column': 'npt', 'value': 8},
            ],
        )
        self.assertTrue(result['ok'], result)
        dashboard = self.env['edu.teacher.home'].with_user(self.teacher_user).home_data()['dashboard']
        row = next(g for g in dashboard['grades'] if g['class_id'] == self.class_a.id)
        self.assertEqual((row['positives'], row['negatives'], row['missing']), (1, 1, 1))
        self.assertEqual(row['average'], '10,0')
        self.assertEqual((dashboard['graded'], dashboard['expected']), (2, 3))

    def test_absence_report(self):
        """«Relatório de faltas», como no secPed: o aluno que atingiu o limite nas disciplinas do professor e o mapa
        da turma que dirige."""
        self.year.action_generate_trimesters()
        trimester = self.year.trimester_ids.sorted('number')[0]
        trimester.is_current = True
        self.class_a.director_id = self.teacher
        student = self.env['edu.student'].create({'name': 'Aluno faltoso'})
        enrollment = self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': self.class_a.id})
        enrollment.action_confirm()
        limit = absence_limit_of(self.class_a, self.lp)
        self.assertTrue(limit)
        regime = self.class_a._edu_regime()
        failing = limit + 1 if regime == 'technical' else limit
        for index in range(failing):
            day = trimester.date_start + timedelta(days=index)
            lesson = self.env['edu.lesson'].create(
                {'class_id': self.class_a.id, 'subject_id': self.lp.id, 'date': day, 'hour_from': 8.0, 'hour_to': 9.0,
                 'summary': 'Aula'}
            )  # fmt: skip
            lesson.action_open_roll_call()
            lesson.attendance_ids.filtered(lambda line: line.enrollment_id == enrollment).state = 'absent'
            lesson.action_done()
        data = self.env['edu.attendance.page'].with_user(self.teacher_user).absence_report()
        self.assertEqual(data['trimester_id'], trimester.id)
        mine = next(g for g in data['mine'] if g['id'] == enrollment.id)
        self.assertEqual(mine['worst'], 'failed')
        self.assertEqual(mine['items'][0]['counted'], failing)
        board = data['board']
        self.assertEqual(board['class_id'], self.class_a.id)
        row = next(r for r in board['students'] if r['id'] == enrollment.id)
        self.assertEqual(row['cells'][self.lp.id]['status'], 'failed')
        self.assertEqual(board['failed'], 1)

    def test_chat_contacts(self):
        """«Nova conversa» das Mensagens, por grupos, como no secPed: o director da turma onde dou aulas, os colegas
        das minhas turmas, a secretaria e a direcção (só quem tem utilizador; o próprio professor não aparece)."""
        director_user = self.env['res.users'].create(
            {
                'name': 'Directora Turma',
                'login': 'dir_turma',
                'group_ids': [Command.set(self.teacher_user.group_ids.ids)],
            }
        )
        director = self.env['hr.employee'].create(
            {'name': 'Directora Turma', 'user_id': director_user.id, 'edu_is_teacher': True}
        )
        self.class_a.director_id = director
        groups = {g['key']: g for g in self.env['edu.teacher.home'].with_user(self.teacher_user).chat_contacts()}
        self.assertIn(director_user.partner_id.id, [c['partner_id'] for c in groups['directors']['contacts']])
        self.assertIn(self.clerk.partner_id.id, [c['partner_id'] for c in groups['office']['contacts']])
        self.assertIn(self.director.partner_id.id, [c['partner_id'] for c in groups['direction']['contacts']])
        everyone = [c['partner_id'] for g in groups.values() for c in g['contacts']]
        self.assertNotIn(self.teacher_user.partner_id.id, everyone)
        self.assertEqual(len(everyone), len(set(everyone)))

    def test_academic_calendar(self):
        """«Calendário académico», como no secPed: os eventos do ano e o início e o fim de cada trimestre; as datas
        comemorativas do calendário nacional vêm marcadas (o professor pode escondê-las)."""
        self.year.action_generate_trimesters()
        self.env['edu.calendar.event'].create(
            {'name': 'Reunião de pais', 'event_type': 'meeting', 'academic_year_id': self.year.id,
             'date_start': date(2026, 10, 10)}
        )  # fmt: skip
        data = self.env['edu.teacher.home'].with_user(self.teacher_user).calendar_data()
        self.assertEqual(data['year'], '2026/2027')
        types = {e['type'] for e in data['events']}
        self.assertTrue({'meeting', 'trimester_start', 'trimester_end'} <= types)
        meeting = next(e for e in data['events'] if e['name'] == 'Reunião de pais')
        self.assertEqual(
            (meeting['start'], meeting['end'], meeting['commemorative']), ('2026-10-10', '2026-10-10', False)
        )
        self.assertEqual([e['start'] for e in data['events']], sorted(e['start'] for e in data['events']))

    def test_teacher_supervisions(self):
        """«Vigilâncias», como no secPed: as provas que o professor vigia, por época, e a escala para imprimir (que ele
        abre com as provas todas, embora as regras das sessões lhas escondam)."""
        room = self.env['edu.room'].create({'name': 'Sala 7', 'code': 'S7'})
        period = self.env['edu.exam.period'].create(
            {'name': 'Provas do I Trimestre', 'date_start': date(2026, 12, 9), 'date_end': date(2026, 12, 18)}
        )
        period.planner_mark(self.lp.id, '2026-12-09', 8.0, 10.0, self.class_a.ids)
        session = period.session_ids
        self.env['edu.exam.period'].planner_set_room(session.id, room.id)
        self.env['edu.exam.period'].planner_set_supervisor(session.id, self.teacher.id)
        Home = self.env['edu.teacher.home'].with_user(self.teacher_user)
        data = Home.supervisions_data()
        self.assertEqual([p['name'] for p in data['periods']], ['Provas do I Trimestre'])
        row = data['periods'][0]['rows'][0]
        self.assertEqual((row['id'], row['start'], row['end'], row['rooms']), (session.id, 480, 600, 'S7 · Sala 7'))
        action = Home.supervisions_report(period.id)
        self.assertEqual(action['report_type'], 'qweb-html')
        document = self.env['edu.exam.calendar.print'].browse(action['context']['active_ids'])
        html = (
            self.env['ir.actions.report']
            .with_user(self.teacher_user)
            ._render_qweb_html('edu_documents.report_exam_calendar', document.ids)[0]
            .decode()
        )
        self.assertIn('ESCALA DE VIGILÂNCIA', html)
        self.assertIn('08:00–10:00', html)
        # Outro professor não abre a escala desta época.
        other = self.env['res.users'].create(
            {'name': 'Outro', 'login': 'outro_prof', 'group_ids': [Command.set(self.teacher_user.group_ids.ids)]}
        )
        self.env['hr.employee'].create({'name': 'Outro', 'user_id': other.id, 'edu_is_teacher': True})
        with self.assertRaises(UserError):
            self.env['edu.teacher.home'].with_user(other).supervisions_report(period.id)

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
        # Em «Turmas e notas» só as suas turmas.
        grid = self.env['edu.grade.grid'].with_user(self.teacher_user).grid_classes(self.year.id)
        self.assertEqual([c['id'] for c in grid['classes']], self.class_a.ids)

    def test_grade_grid_profiles(self):
        """Notas da turma: o professor vê só as turmas e disciplinas que lecciona; o director de turma vê todas as
        disciplinas da turma mas só altera as suas e imprime a pauta; a secretaria consulta e imprime."""
        self.year.action_generate_trimesters()
        self.year.trimester_ids.sorted('number')[0].is_current = True
        Grid = self.env['edu.grade.grid'].with_user(self.teacher_user)
        self.assertEqual([c['id'] for c in Grid.grid_classes()['classes']], self.class_a.ids)
        self.assertEqual([(s['id'], s['editable']) for s in Grid.grid_subjects(self.class_a.id)], [(self.lp.id, True)])
        data = Grid.grid_data(self.class_a.id, self.lp.id)
        self.assertTrue(data['can_edit'])
        self.assertFalse(data['can_print'])
        trimester = data['trimesters'][0]['id']
        with self.assertRaises(AccessError):
            Grid.grid_print(self.class_a.id, trimester, True)
        other = self.class_a.subject_line_ids.subject_id.filtered(lambda s: s.code != 'LP')[:1]
        with self.assertRaises(AccessError):
            Grid.grid_data(self.class_a.id, other.id)
        # Dentro da turma (o menu do secPed não os tem): a mini-pauta e o conselho; justificar faltas é do director.
        links = Grid.grid_classes()['classes'][0]['links']
        self.assertEqual([link['key'] for link in links], ['mini_pauta', 'council'])
        action = Grid.class_link_action(self.class_a.id, 'mini_pauta')
        self.assertEqual(action['context']['default_class_id'], self.class_a.id)
        with self.assertRaises(UserError):
            Grid.class_link_action(self.class_a.id, 'absences')
        with self.assertRaises(AccessError):
            Grid.class_link_action(self.class_b.id, 'council')

        # Director da turma B, onde não dá aulas: vê todas as disciplinas, não altera nenhuma, imprime a pauta.
        self.class_b.director_id = self.teacher
        self.assertEqual([c['id'] for c in Grid.grid_classes()['classes']], (self.class_a | self.class_b).ids)
        links = Grid.grid_classes()['classes'][1]['links']
        self.assertEqual([link['key'] for link in links], ['mini_pauta', 'council', 'absences'])
        action = Grid.class_link_action(self.class_b.id, 'absences')
        self.assertIn(('enrollment_id.class_id', '=', self.class_b.id), action['domain'])
        subjects = Grid.grid_subjects(self.class_b.id)
        self.assertEqual(len(subjects), len(self.class_b.subject_line_ids.filtered('weekly_hours')))
        self.assertFalse(any(s['editable'] for s in subjects))
        data = Grid.grid_data(self.class_b.id, self.lp.id)
        self.assertFalse(data['can_edit'])
        self.assertTrue(data['can_print'])
        self.assertEqual(Grid.grid_print(self.class_b.id, trimester, True)['report_type'], 'qweb-html')
        # O director gera mesmo a pauta (sem acesso ao plano curricular).
        wizard = self.env['edu.pauta.print'].with_user(self.teacher_user).search([], order='id desc', limit=1)
        html = (
            self.env['ir.actions.report']
            .with_user(self.teacher_user)
            ._render_qweb_html('edu_documents.report_pauta', wizard.ids)[0]
            .decode()
        )
        self.assertIn('MAPA DE APROVEITAMENTO', html)
        with self.assertRaises(AccessError):
            Grid.grid_save(self.class_b.id, self.lp.id, [])

        # A secretaria vê todas as turmas, imprime, mas não altera.
        Clerk = self.env['edu.grade.grid'].with_user(self.clerk)
        self.assertEqual(len(Clerk.grid_classes()['classes']), 2)
        data = Clerk.grid_data(self.class_a.id, self.lp.id)
        self.assertEqual((data['can_edit'], data['can_print']), (False, True))

    def test_teacher_home(self):
        """Painel do Professor, como no secPed: as aulas do dia pelo horário (a chamada a um toque cria a aula), as
        turmas com a direcção assinalada e os atalhos da conta."""
        self.year.action_generate_trimesters()
        # O tempo do horário no dia de hoje (seja qual for): a chamada só se abre no próprio dia.
        today = fields.Date.context_today(self.env['edu.lesson'])
        schedule = self.env['edu.schedule'].create(
            {
                'class_id': self.class_a.id,
                'subject_id': self.lp.id,
                'weekday': str(today.weekday()),
                'hour_from': 8.0,
                'hour_to': 9.0,
            }
        )
        self.class_b.director_id = self.teacher
        Home = self.env['edu.teacher.home'].with_user(self.teacher_user)
        data = Home.home_data()
        classes = [(c['id'], c['directs']) for c in data['classes']]
        self.assertEqual(classes, [(self.class_a.id, False), (self.class_b.id, True)])
        self.assertEqual([lesson['schedule_id'] for lesson in data['lessons']], schedule.ids)
        self.assertFalse(data['lessons'][0]['lesson_id'])
        action = Home.open_lesson(schedule.id, fields.Date.to_string(today))
        self.assertEqual(action['tag'], 'edu_roles.attendance')
        lesson = self.env['edu.lesson'].browse(action['context']['attendance_lesson_id'])
        self.assertEqual((lesson.schedule_id, lesson.date, lesson.teacher_id), (schedule, today, self.teacher))
        again = Home.open_lesson(schedule.id, fields.Date.to_string(today))
        self.assertEqual(again['context']['attendance_lesson_id'], lesson.id)
        self.assertEqual(Home.home_data()['lessons'][0]['lesson_id'], lesson.id)
        # «Meu horário»: as aulas da semana (minutos desde a meia-noite), a carga e a folha A4 na aplicação.
        week = Home.schedule_data()
        self.assertEqual(
            [(w['id'], w['weekday'], w['start'], w['end'], w['class_id']) for w in week['lessons']],
            [(schedule.id, today.weekday(), 480, 540, self.class_a.id)],
        )
        self.assertEqual(week['load']['count'], 1)
        self.assertTrue(week['load']['notes'])  # director da turma B: menos 2 tempos
        self.assertEqual(Home.schedule_report(True)['report_type'], 'qweb-html')
        # «Meu perfil» e «Recibos e férias», como no secPed.
        profile = Home.profile_data()
        self.assertEqual(profile['classes'], [self.class_a._editor_label()])
        self.assertIn(self.class_b._editor_label(), profile['directs'])
        payslips = Home.payslips_data()
        self.assertEqual(payslips['has_payroll'], 'l10n_ao_payroll.payslip' in self.env)
        self.assertEqual(payslips['payslips'], [])
        # Um tempo de outro professor não se abre.
        other = self.env['hr.employee'].create({'name': 'Outro', 'edu_is_teacher': True})
        schedule.teacher_id = other
        with self.assertRaises(UserError):
            Home.open_lesson(schedule.id, fields.Date.to_string(today))
