from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestGuardianPortal(HttpCase):
    """A área do encarregado: só os educandos que a escola lhe ligou com acesso ao portal, com os dados da área do
    estudante; o RDEC na Iniciação; e as mensagens só com a escola."""

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
        cls.teacher_user = cls.env['res.users'].create(
            {
                'name': 'Professora Lurdes',
                'login': 'prof_guardian',
                'group_ids': [Command.set([cls.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        cls.teacher = cls.env['hr.employee'].create(
            {'name': 'Professora Lurdes', 'edu_is_teacher': True, 'user_id': cls.teacher_user.id}
        )
        cls.env['edu.teaching.assignment'].create(
            {'class_id': cls.edu_class.id, 'subject_id': cls.lp.id, 'teacher_id': cls.teacher.id}
        )
        cls.edu_class.director_id = cls.teacher
        cls.ana = cls.env['edu.student'].create({'name': 'Ana Educanda'})
        cls.bento = cls.env['edu.student'].create({'name': 'Bento Alheio'})
        cls.enrollments = cls.env['edu.enrollment']
        for student in (cls.ana, cls.bento):
            enrollment = cls.env['edu.enrollment'].create({'student_id': student.id, 'class_id': cls.edu_class.id})
            enrollment.action_confirm()
            cls.enrollments |= enrollment
        ana_e, bento_e = cls.enrollments
        result = (
            cls.env['edu.grade.grid']
            .with_user(cls.teacher_user)
            .grid_save(
                cls.edu_class.id,
                cls.lp.id,
                [
                    {'enrollment_id': ana_e.id, 'trimester_id': cls.t1.id, 'column': 'npp', 'value': 14},
                    {'enrollment_id': ana_e.id, 'trimester_id': cls.t1.id, 'column': 'npt', 'value': 12},
                    {'enrollment_id': bento_e.id, 'trimester_id': cls.t1.id, 'column': 'npp', 'value': 4},
                ],
            )
        )
        assert result['ok'], result
        cls.guardian = cls.env['edu.guardian'].create({'name': 'Gil Encarregado', 'phone': '923000000'})
        cls.env['edu.student.guardian'].create(
            {'student_id': cls.ana.id, 'guardian_id': cls.guardian.id, 'relationship': 'father', 'is_primary': True}
        )
        # O Bento está ligado, mas sem acesso ao portal: não aparece.
        cls.env['edu.student.guardian'].create(
            {'student_id': cls.bento.id, 'guardian_id': cls.guardian.id, 'can_access_portal': False}
        )
        cls.gil_user = cls.env['res.users'].create(
            {
                'name': 'Gil Encarregado',
                'login': 'gil_guardian',
                'password': 'gil_guardian_pw_123',
                'partner_id': cls.guardian.partner_id.id,
                'group_ids': [Command.set([cls.env.ref('edu_portal.group_edu_guardian').id])],
            }
        )

    def _iniciacao(self):
        """Uma turma da Iniciação, com a Carla, educanda do Gil, e o RDEC do 1.º trimestre começado."""
        course = self.env['edu.course'].create(
            {'name': 'Iniciação', 'code': 'INI', 'level_id': self.env.ref('edu_core.level_iniciacao').id}
        )
        subjects = self.env['edu.subject'].create(
            [{'name': 'Linguagem', 'code': 'LIN'}, {'name': 'Expressão Plástica', 'code': 'EXP'}]
        )
        curriculum = self.env['edu.curriculum'].create(
            {'name': 'Plano — Iniciação', 'course_id': course.id, 'level_id': course.level_id.id}
        )
        year_line = self.env['edu.curriculum.year'].create(
            {
                'curriculum_id': curriculum.id,
                'year': 1,
                'class_number': 0,
                'line_ids': [Command.create({'subject_id': s.id, 'weekly_hours': 3}) for s in subjects],
            }
        )
        edu_class = self.env['edu.class'].create(
            {
                'name': 'A',
                'course_id': course.id,
                'class_number': 0,
                'curriculum_id': curriculum.id,
                'curriculum_year_id': year_line.id,
                'academic_year_id': self.year.id,
            }
        )
        educator = self.env['hr.employee'].create({'name': 'Educadora Rosa', 'edu_is_teacher': True})
        edu_class.director_id = educator
        carla = self.env['edu.student'].create({'name': 'Carla Pequena'})
        enrollment = self.env['edu.enrollment'].create(
            {'student_id': carla.id, 'class_id': edu_class.id, 'subject_ids': [Command.set(subjects.ids)]}
        )
        enrollment.action_confirm()
        self.env['edu.student.guardian'].create({'student_id': carla.id, 'guardian_id': self.guardian.id})
        rdec = self.env['edu.rdec']._prepare(edu_class, self.t1)
        rdec.line_ids[0].level = 'very_good'
        return carla, rdec

    def test_pages_only_own_children(self):
        Portal = self.env['edu.guardian.portal'].with_user(self.gil_user)
        for page in ('home', 'children', 'grades', 'rdec', 'absences', 'exams', 'fees', 'notifications', 'profile'):
            with self.subTest(page=page):
                data = Portal.page_data(page)
                self.assertTrue(data['has_guardian'])
                self.assertEqual([c['id'] for c in data['children']], self.ana.ids)
                self.assertNotIn('Bento Alheio', str(data))
        # Pedir um educando que não é seu (ou sem acesso ao portal) dá o seu.
        data = Portal.page_data('grades', {'student_id': self.bento.id})
        self.assertEqual(data['child_id'], self.ana.id)
        row = next(r for r in data['grades']['subjects'] if r['id'] == self.lp.id)
        self.assertEqual(row['by_trimester'][self.t1.id]['ct']['text'], '13')
        # Mudar de educando num ano em que ele não tem matrícula: o ano dele, e a página diz qual pediu.
        past = self.env['edu.academic.year'].create(
            {'name': '2025/2026', 'date_start': date(2025, 9, 1), 'date_end': date(2026, 7, 31)}
        )
        grades = Portal.page_data('grades', {'student_id': self.ana.id, 'academic_year_id': past.id})['grades']
        self.assertEqual((grades['year'], grades['year_missing']), ('2026/2027', '2025/2026'))
        grades = Portal.page_data('grades', {'student_id': self.ana.id, 'academic_year_id': self.year.id})['grades']
        self.assertEqual(grades['year_missing'], '')
        card = Portal.page_data('children')['card']
        self.assertEqual(card['relationship'], 'Pai')
        lurdes = {'name': 'Professora Lurdes', 'partner_id': self.teacher_user.partner_id.id}
        self.assertEqual(card['director'], lurdes)
        lp = next(s for s in card['subjects'] if s['id'] == self.lp.id)
        self.assertEqual(lp['teachers'], [lurdes])
        self.assertEqual(card['summary']['trend'][0]['text'], '13,0')
        # O encarregado não lê os modelos da escola nem os contactos dos alunos.
        with self.assertRaises(AccessError):
            self.env['edu.subject.result'].with_user(self.gil_user).search([])
        Partner = self.env['res.partner'].with_user(self.gil_user)
        self.assertFalse(Partner.search([('id', 'in', (self.ana | self.bento).partner_id.ids)]))

    def test_home(self):
        data = self.env['edu.guardian.portal'].with_user(self.gil_user).page_data('home')
        summary = data['summaries'][0]
        self.assertEqual(summary['name'], 'Ana Educanda')
        self.assertEqual(summary['average']['text'], '13,0')
        self.assertEqual(summary['overdue'], 0)
        # Os gráficos: a média do 1.º trimestre, as aulas e as propinas de Setembro a Julho (ainda sem facturas).
        self.assertEqual(summary['trend'][0]['text'], '13,0')
        self.assertEqual(summary['lessons'], {'present': 0, 'excused': 0, 'absent': 0})
        self.assertEqual([m['label'] for m in summary['months']][:2], ['Set', 'Out'])
        self.assertEqual(len(summary['months']), 11)
        self.assertEqual({m['state'] for m in summary['months']}, {'none'})
        self.assertIn('Notas novas de Língua Portuguesa.', [item['text'] for item in data['feed']])

    def test_rdec(self):
        Portal = self.env['edu.guardian.portal'].with_user(self.gil_user)
        Menu = self.env['ir.ui.menu'].with_user(self.gil_user)
        rdec_menu = self.env.ref('edu_portal.menu_guardian_rdec').id
        self.assertIn(rdec_menu, Menu._load_menus_blacklist(), 'sem educandos na Iniciação, sem RDEC')
        carla, rdec = self._iniciacao()
        self.assertNotIn(rdec_menu, Menu._load_menus_blacklist())
        self.assertEqual(Portal.page_data('rdec')['child_id'], carla.id, 'sem escolha, o educando da Iniciação')
        data = Portal.page_data('rdec', {'student_id': carla.id})['rdec']
        self.assertTrue(data['applicable'])
        self.assertEqual(data['state'], 'progress')
        self.assertEqual([a['level_label'] for a in data['areas']], ['Muito bom', ''])
        # A Ana (do técnico) não tem RDEC: pedida noutra página, o RDEC abre na Carla, e só ela tem separador.
        data = Portal.page_data('rdec', {'student_id': self.ana.id})
        self.assertEqual(data['child_id'], carla.id)
        self.assertEqual([c['id'] for c in data['children']], carla.ids)
        # O documento: o RDEC dos educandos sim; o de outra criança não.
        action = Portal.rdec_report(carla.id, self.t1.id)
        self.assertEqual(action['context']['active_ids'], rdec.ids)
        Report = self.env['ir.actions.report'].with_user(self.gil_user)
        html = Report._render_qweb_html('edu_documents.report_rdec', rdec.ids)[0]
        self.assertIn(b'Carla Pequena', html)
        other = self.env['edu.student'].create({'name': 'Dina Outra'})
        enrollment = self.env['edu.enrollment'].create(
            {
                'student_id': other.id,
                'class_id': rdec.class_id.id,
                'subject_ids': [Command.set(rdec.line_ids.subject_id.ids)],
            }
        )
        enrollment.action_confirm()
        other_rdec = self.env['edu.rdec']._prepare(rdec.class_id, self.t1)
        with self.assertRaises(AccessError):
            Report._render_qweb_html('edu_documents.report_rdec', other_rdec.ids)
        with self.assertRaises(AccessError):
            Report._render_qweb_html('edu_documents.report_class_schedule', self.edu_class.ids)

    def test_guardian_lockdown(self):
        """O encarregado é utilizador interno: não muda os seus dados, só vê a sua área, e nas Discussões só tem as
        suas conversas com a escola (sem os canais do pessoal nem as notas internas dos registos)."""
        gil = self.gil_user.with_user(self.gil_user)
        with self.assertRaises(AccessError):
            gil.partner_id.write({'name': 'Outro nome'})
        with self.assertRaises(AccessError):
            gil.write({'email': 'outro@example.com'})
        roots = self.env['ir.ui.menu'].with_user(self.gil_user).load_menus(False)['root']['children']
        self.assertIn(self.env.ref('edu_portal.menu_guardian_root').id, roots)
        self.assertNotIn(self.env.ref('mail.menu_root_discuss').id, roots)
        general = self.env['discuss.channel'].create(
            {'name': 'Geral', 'group_ids': [Command.link(self.env.ref('base.group_user').id)]}
        )
        self.assertNotIn(self.guardian.partner_id, general.channel_member_ids.partner_id)
        Channel = self.env['discuss.channel'].with_user(self.gil_user)
        self.assertFalse(Channel.search([]))
        # Escreve à directora de turma: a conversa é sua e lê-se.
        Channel._get_or_create_chat([self.teacher_user.partner_id.id])
        chat = Channel.search([])
        self.assertEqual(chat.channel_type, 'chat')
        message = chat.message_post(body='Bom dia, professora.', message_type='comment')
        self.assertTrue(self.env['mail.message'].with_user(self.gil_user).search([('id', '=', message.id)]))
        note = self.edu_class.message_post(body='Nota interna da turma', message_type='comment')
        self.assertFalse(self.env['mail.message'].with_user(self.gil_user).search([('id', '=', note.id)]))
        # Os contactos da «Nova conversa»: a directora de turma da Ana e a secretaria.
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretaria Geral',
                'login': 'secretaria_guardian',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        groups = self.env['edu.teacher.home'].with_user(self.gil_user).chat_contacts()
        by_key = {g['key']: g for g in groups}
        self.assertEqual(
            [c['partner_id'] for c in by_key[f'child{self.ana.id}']['contacts']], self.teacher_user.partner_id.ids
        )
        self.assertIn(clerk.partner_id.id, [c['partner_id'] for c in by_key['office']['contacts']])
        # Como no secPed, só esses: a procura da «Nova conversa» não mostra outro professor da escola, e a conversa
        # com ele não se abre (nem pedida directamente ao servidor).
        stranger = self.env['res.users'].create(
            {
                'name': 'Professor Alheio',
                'login': 'prof_alheio',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_teacher').id])],
            }
        )
        self.env['hr.employee'].create({'name': 'Professor Alheio', 'edu_is_teacher': True, 'user_id': stranger.id})
        Partner = self.env['res.partner'].with_user(self.gil_user)
        # A secretaria encontra-se e abre-se conversa com ela, mesmo sem ficha de funcionário.
        self.assertEqual(Partner.search_for_channel_invite('Secretaria Geral')['partner_ids'], clerk.partner_id.ids)
        office_chat = Channel._get_or_create_chat([clerk.partner_id.id])
        self.assertIn(clerk.partner_id, office_chat.channel_member_ids.partner_id)
        found = Partner.search_for_channel_invite('Professor')['partner_ids']
        self.assertIn(self.teacher_user.partner_id.id, found)
        self.assertNotIn(stranger.partner_id.id, found)
        with self.assertRaises(AccessError):
            Channel._get_or_create_chat([stranger.partner_id.id])
        with self.assertRaises(AccessError):
            chat._add_members(partners=stranger.partner_id)
        # O professor escreve-lhe na mesma (a restrição é só do encarregado).
        self.env['discuss.channel'].with_user(stranger)._get_or_create_chat([self.guardian.partner_id.id])
        # Um professor que também é encarregado continua com o seu painel e as regras de professor.
        self.teacher_user.group_ids = [Command.link(self.env.ref('edu_portal.group_edu_guardian').id)]
        self.assertFalse(self.teacher_user._edu_guardian_only())
        self.assertTrue(self.env['discuss.channel'].with_user(self.teacher_user).search([('id', '=', general.id)]))
        # E o mesmo com o aluno: um professor com o perfil «Aluno» não perde os canais do pessoal.
        self.teacher_user.group_ids = [Command.link(self.env.ref('edu_portal.group_edu_student').id)]
        self.assertTrue(self.env['discuss.channel'].with_user(self.teacher_user).search([('id', '=', general.id)]))
