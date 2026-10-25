from datetime import date, timedelta
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
        self.assertIn('a média é 13,0, com positiva a uma disciplina', grades['summary'])
        self.assertFalse(grades['show_situation'], 'a situação só aparece no último trimestre')
        self.assertFalse(grades['show_pg'], 'PG e CA só depois de lançada a prova global')

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
        self.assertIn('a média é 15,0', grades['summary'])
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

    def test_student_lockdown(self):
        """O aluno é utilizador interno, mas não muda os seus dados (são da secretaria), não lista os outros
        utilizadores, não entra nas conversas nem no calendário do pessoal e só abre o horário da sua turma."""
        ana = self.ana_user.with_user(self.ana_user)
        with self.assertRaises(AccessError):
            ana.partner_id.write({'name': 'Outro nome'})
        with self.assertRaises(AccessError):
            ana.write({'email': 'outro@example.com'})
        # A palavra-passe muda-se (o assistente escreve como o próprio utilizador, em sudo).
        ana.env.user._change_password('ana_portal_pw_456')
        Users = self.env['res.users'].with_user(self.ana_user)
        self.assertTrue(Users.search([('id', '=', self.ana_user.id)]), 'o seu utilizador lê-se')
        bento_user = self.env['res.users'].create(
            {
                'name': 'Bento Vizinho',
                'login': 'bento_portal',
                'partner_id': self.bento.partner_id.id,
                'group_ids': [Command.set([self.env.ref('edu_portal.group_edu_student').id])],
            }
        )
        self.assertFalse(Users.search([('id', '=', bento_user.id)]), 'os outros alunos não se listam')
        self.assertTrue(Users.search([('login', '=', 'prof_portal')]), 'o pessoal sim')
        # Nem as conversas (o «General» junta os internos), nem o calendário, nem as notas internas dos registos.
        general = self.env['discuss.channel'].create(
            {'name': 'Geral', 'group_ids': [Command.link(self.env.ref('base.group_user').id)]}
        )
        self.assertNotIn(self.ana.partner_id, general.channel_member_ids.partner_id)
        self.assertIn(self.env.user.partner_id, general.channel_member_ids.partner_id)
        self.assertFalse(self.env['discuss.channel'].with_user(self.ana_user).search([]))
        self.assertFalse(self.env['calendar.event'].with_user(self.ana_user).search([]))
        with self.assertRaises(AccessError):
            self.env['calendar.event'].with_user(self.ana_user).create({'name': 'Festa'})
        note = self.edu_class.message_post(body='Nota interna da turma', message_type='comment')
        self.assertFalse(self.env['mail.message'].with_user(self.ana_user).search([('id', '=', note.id)]))
        # Os relatórios: o horário da sua turma sim; o de outra turma e a lista dos professores não.
        Report = self.env['ir.actions.report'].with_user(self.ana_user)
        other_class = self.edu_class.copy({'name': 'Z'})
        with self.assertRaises(AccessError):
            Report._render_qweb_html('edu_documents.report_class_schedule', other_class.ids)
        teachers = self.env['hr.employee.public'].search([], limit=1)
        with self.assertRaises(AccessError):
            Report._render_qweb_html('edu_documents.report_teachers', teachers.ids)
        # Os auxiliares do portal não se chamam por RPC: só as páginas.
        Portal = type(self.env['edu.student.portal'])
        for name in ('grades', 'exams', 'absences', 'fees', 'profile', 'internships', 'projects'):
            self.assertTrue(getattr(getattr(Portal, name), '_api_private', False), name)

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

    def test_exams(self):
        """As provas da turma, como no secPed: por época, o dia só na primeira prova desse dia, e o calendário em A4 da
        sua turma (o de outra turma não)."""
        period = self.env['edu.exam.period'].create(
            {'name': 'Provas do I Trimestre', 'date_start': date(2027, 7, 1), 'date_end': date(2027, 7, 20)}
        )
        for day, hour in ((5, 8), (5, 10), (6, 8)):
            self.env['edu.exam.session'].create(
                {
                    'period_id': period.id,
                    'subject_id': self.lp.id,
                    'class_ids': [Command.set(self.edu_class.ids)],
                    'date': date(2027, 7, day),
                    'hour_from': hour,
                    'hour_to': hour + 1.5,
                }
            )
        # O recurso marcado para a turma só aparece a quem foi convocado.
        resit = self.env['edu.exam.period'].create(
            {'name': 'Recurso', 'kind': 'resit', 'date_start': date(2027, 7, 21), 'date_end': date(2027, 7, 25)}
        )
        resit_session = self.env['edu.exam.session'].create(
            {
                'period_id': resit.id,
                'subject_id': self.lp.id,
                'class_ids': [Command.set(self.edu_class.ids)],
                'date': date(2027, 7, 22),
                'hour_from': 8,
                'hour_to': 9.5,
            }
        )
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        exams = Portal.page_data('exams')['exams']
        self.assertEqual((exams['count'], exams['days']), (3, 2))
        self.env['edu.exam.seat'].create({'session_id': resit_session.id, 'enrollment_id': self.enrollments[0].id})
        self.assertEqual(Portal.page_data('exams')['exams']['count'], 4)
        resit.unlink()
        self.assertEqual([r['first_of_day'] for r in exams['rows']], [True, False, True])
        self.assertTrue(exams['rows'][0]['day'].endswith('5 de Julho'))
        action = Portal.exams_report()
        self.assertEqual(action['report_type'], 'qweb-html')
        Report = self.env['ir.actions.report'].with_user(self.ana_user)
        documents = self.env['edu.exam.calendar.print'].browse(action['context']['active_ids'])
        html = Report._render_qweb_html('edu_documents.report_exam_calendar', documents.ids)[0].decode()
        self.assertIn('CALENDÁRIO DE PROVAS', html)
        other_class = self.edu_class.copy({'name': 'Z'})
        other = (
            self.env['edu.exam.calendar.print']
            .with_user(self.ana_user)
            .sudo()
            .create({'period_id': period.id, 'class_id': other_class.id})
        )
        with self.assertRaises(AccessError):
            Report._render_qweb_html('edu_documents.report_exam_calendar', other.ids)

    def test_absences_worst_trimester(self):
        """No ensino geral o limite é por trimestre e conta o pior trimestre de cada disciplina (como no secPed)."""
        course = self.env['edu.course'].create(
            {'name': 'Ensino secundário I ciclo', 'code': 'SEC1', 'level_id': self.env.ref('edu_core.level_sec1').id}
        )
        seventh = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 7)
        edu_class = self.env['edu.class'].create(
            {'name': 'A', 'course_id': course.id, 'curriculum_year_id': seventh.id}
        )
        subject = edu_class.subject_line_ids.subject_id.filtered(lambda s: s.code == 'LP')
        student = self.env['edu.student'].create({'name': 'Carla Geral'})
        enrollment = self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': edu_class.id})
        enrollment.action_confirm()
        t1, t2 = self.year.trimester_ids.sorted('number')[:2]
        for trimester, absences in ((t1, 1), (t2, 2)):
            for index in range(absences):
                lesson = self.env['edu.lesson'].create(
                    {'class_id': edu_class.id, 'subject_id': subject.id, 'summary': 'Aula', 'hour_from': 8.0,
                     'hour_to': 9.0, 'date': trimester.date_start + timedelta(days=index)}
                )  # fmt: skip
                lesson.action_open_roll_call()
                lesson.attendance_ids.state = 'absent'
                # O 2.º trimestre ainda não chegou: a aula dá-se por dada como o sistema faz.
                lesson.with_context(edu_lesson_system=True).state = 'done'
        user = self.env['res.users'].create(
            {
                'name': 'Carla Geral',
                'login': 'carla_geral',
                'partner_id': student.partner_id.id,
                'group_ids': [Command.set([self.env.ref('edu_portal.group_edu_student').id])],
            }
        )
        absences = self.env['edu.student.portal'].with_user(user).page_data('absences')['absences']
        self.assertEqual(absences['regime'], 'general')
        row = next(r for r in absences['subjects'] if r['name'] == subject.name)
        self.assertEqual((row['absent'], row['counted']), (3, 2), 'as do ano; contam as do pior trimestre')
        self.assertEqual(row['window'], t2.name.replace('Trimestre', 'trimestre'))
        # Do ensino geral: sem a formação técnica no menu.
        hidden = self.env['ir.ui.menu'].with_user(user)._load_menus_blacklist()
        self.assertIn(self.env.ref('edu_portal.menu_student_training').id, hidden)

    def test_internship_and_project(self):
        """«O Meu Estágio» e «A Minha PAP», como no secPed: só para ler e só do próprio aluno; o menu da formação
        técnica aparece ao aluno do técnico."""
        self.edu_class.course_id.write({'requires_internship': True, 'requires_final_project': True})
        tutor = self.env['hr.employee'].create({'name': 'Tutora do estágio', 'edu_is_teacher': True})
        self.env['edu.internship'].create(
            {'student_id': self.ana.id, 'entity': 'Hospital Geral', 'tutor_id': tutor.id, 'hours': 120}
        )
        self.env['edu.internship'].create({'student_id': self.bento.id, 'entity': 'Clínica do vizinho'})
        self.env['edu.final.project'].create({'student_id': self.ana.id, 'name': 'Higiene hospitalar'})
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        internships = Portal.page_data('internship')['internships']
        self.assertEqual([i['entity'] for i in internships], ['Hospital Geral'])
        self.assertEqual((internships[0]['tutor'], internships[0]['hours']), ('Tutora do estágio', 120))
        self.assertIn('a data de início ainda não foi marcada', internships[0]['sentence'])
        # Sem datas não há tempo decorrido; a primeira etapa é a actual.
        self.assertIsNone(internships[0]['progress'])
        self.assertEqual([(st['key'], st['current']) for st in internships[0]['steps']][0], ('planned', True))
        projects = Portal.page_data('project')['projects']
        self.assertEqual(projects[0]['title'], 'Higiene hospitalar')
        self.assertIn('ainda não tens orientador', projects[0]['sentence'])
        menus = self.env['ir.ui.menu'].with_user(self.ana_user)._load_menus_blacklist()
        self.assertNotIn(self.env.ref('edu_portal.menu_student_training').id, menus)

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

    def test_history_notifications_and_messages(self):
        """O Histórico (só os anos com decisão), as notificações (as notas novas, sem a nota) e as mensagens: o aluno
        escreve aos professores da turma e à secretaria e só lê as suas conversas."""
        Portal = self.env['edu.student.portal'].with_user(self.ana_user)
        self.assertEqual(Portal.page_data('history')['history']['rows'], [], 'o ano em curso ainda sem decisão')
        result = self.env['edu.year.result'].search([('enrollment_id', '=', self.enrollments[0].id)], limit=1)
        result = result or self.env['edu.year.result'].create({'enrollment_id': self.enrollments[0].id})
        result.write({'status': 'promoted', 'average': 13.0})
        rows = Portal.page_data('history')['history']['rows']
        self.assertEqual(
            [(r['year'], r['status_label'], r['average']['text']) for r in rows], [('2026/2027', 'Transita', '13')]
        )
        self.assertEqual((rows[0]['average_value'], rows[0]['scale_max']), (13.0, 20))
        home = Portal.page_data('home')
        self.assertFalse(home['fees_summary']['invoiced'], 'sem facturas: o painel diz «Sem facturas»')
        self.assertIn('Notas novas de Língua Portuguesa.', [item['text'] for item in home['feed']])
        feed = Portal.page_data('notifications')['feed']
        self.assertIn('Notas novas de Língua Portuguesa.', [item['text'] for item in feed])
        self.assertNotIn('Bento', str(feed))
        # As mensagens: a conversa com o professor é sua; os canais do pessoal não.
        teacher = self.env['res.users'].search([('login', '=', 'prof_portal')])
        groups = {g['key']: g for g in self.env['edu.teacher.home'].with_user(self.ana_user).chat_contacts()}
        self.assertEqual([c['partner_id'] for c in groups['teachers']['contacts']], teacher.partner_id.ids)
        Channel = self.env['discuss.channel'].with_user(self.ana_user)
        Channel._get_or_create_chat([teacher.partner_id.id])
        chat = Channel.search([])
        self.assertEqual(chat.channel_type, 'chat')
        message = chat.message_post(body='Professor, tenho uma dúvida.', message_type='comment')
        self.assertTrue(self.env['mail.message'].with_user(self.ana_user).search([('id', '=', message.id)]))
