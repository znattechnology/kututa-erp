from datetime import date, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduEnrollment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2026/2027', 'date_start': date(2026, 9, 1), 'date_end': date(2027, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
        cls.next_year = cls.env['edu.academic.year'].create(
            {'name': '2027/2028', 'date_start': date(2027, 9, 1), 'date_end': date(2028, 7, 31)}
        )
        technical = cls.env.ref('edu_core.level_tecnico')
        cls.nursing = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Enfermagem',
                'code': 'ENF',
                'level_id': technical.id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_saude_enf').id,
            }
        )
        cls.accounting = cls.env['edu.course'].create(
            {
                'name': 'Técnico de Contabilidade',
                'code': 'CONT',
                'level_id': technical.id,
                'curriculum_template_id': cls.env.ref('edu_core.tpl_tec_contab').id,
            }
        )
        cls.class_a = cls._class(cls.nursing, 'A', 10, capacity=2)
        cls.class_b = cls._class(cls.nursing, 'B', 10)
        cls.class_cont = cls._class(cls.accounting, 'A', 10)
        cls.students = cls.env['edu.student'].create(
            [{'name': name} for name in ('Carla Nzinga', 'Ana Kiala', 'Bento Mateus')]
        )

    @classmethod
    def _class(cls, course, name, number, capacity=30, year=None):
        year_line = course.curriculum_id.year_ids.filtered(lambda y: y.class_number == number)
        return cls.env['edu.class'].create(
            {
                'name': name,
                'course_id': course.id,
                'curriculum_year_id': year_line.id,
                'capacity': capacity,
                'academic_year_id': (year or cls.year).id,
            }
        )

    def _enroll(self, student, edu_class, confirm=True):
        enrollment = self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': edu_class.id})
        if confirm:
            enrollment.action_confirm()
        return enrollment

    def test_enrollment(self):
        carla, ana, bento = self.students
        first = self._enroll(carla, self.class_a)
        self.assertEqual(first.state, 'active')
        self.assertEqual(first.order_number, 1)
        self.assertEqual(carla.matricula_number, '2026-0001')
        self.assertEqual(carla.current_class_id, self.class_a)
        self.assertEqual((carla.student_status, carla.current_course_id), ('enrolled', self.class_a.course_id))
        self.assertEqual(bento.student_status, 'none')
        # A lista de alunos procura pela turma e pela situação (campos gravados).
        Student = self.env['edu.student']
        self.assertEqual(Student.search([('current_class_id', '=', self.class_a.id)]), carla)
        self.assertIn(carla, Student.search([('student_status', '=', 'enrolled')]))
        self.assertIn('TENF', first.subject_ids.mapped('code'))
        second = self._enroll(ana, self.class_a)
        self.assertEqual(second.order_number, 2)
        self.assertEqual(self.class_a.student_count, 2)
        # Num ano fechado, quem concluiu ou ficou retido continua a contar como aluno da turma.
        second.state = 'completed'
        self.assertEqual(self.class_a.student_count, 2)
        second.state = 'active'
        # Turma completa.
        with self.assertRaisesRegex(UserError, 'completa'):
            self._enroll(bento, self.class_a)
        # Uma matrícula por aluno e ano.
        with self.assertRaises(ValidationError):
            self._enroll(carla, self.class_b, confirm=False)
        # Disciplinas fora do plano recusadas.
        with self.assertRaises(ValidationError):
            first.subject_ids |= self.class_cont.subject_line_ids.subject_id.filtered(lambda s: s.code == 'CONTG')[
                :1
            ] or (self.env['edu.subject'].create({'name': 'Fora', 'code': 'XX'}))

    def test_order_numbers_and_drop(self):
        carla, ana, bento = self.students
        enrollments = [self._enroll(student, self.class_b) for student in (carla, ana, bento)]
        self.assertEqual([e.order_number for e in enrollments], [1, 2, 3])
        self.class_b.action_renumber_alphabetical()
        self.assertEqual([e.order_number for e in enrollments], [3, 1, 2])
        wizard = self.env['edu.enrollment.drop'].create(
            {
                'enrollment_ids': [(6, 0, enrollments[1].ids)],
                'reason_code': 'relocation',
                'reason': 'Família mudou-se para o Huambo',
            }
        )
        self.assertTrue(wizard.justified)  # mudança de residência: motivo justificado (art. 28.º, n.º 4)
        wizard.action_confirm()
        self.assertEqual(enrollments[1].state, 'dropped')
        self.assertEqual(
            (enrollments[1].drop_reason_code, enrollments[1].drop_requested_by, enrollments[1].drop_justified),
            ('relocation', 'guardian', True),
        )
        self.assertTrue(enrollments[1].drop_exam_right)  # II Ciclo: direito a exames especiais
        self.assertEqual(enrollments[1].drop_reason, 'Família mudou-se para o Huambo')
        with self.assertRaises(UserError):
            enrollments[1]._drop('outra vez')
        # Quem entra a meio do ano fica no fim, sem renumerar.
        late = self._enroll(self.env['edu.student'].create({'name': 'Zacarias'}), self.class_b)
        self.assertEqual(late.order_number, 4)
        enrollments[1].action_reactivate()
        self.assertEqual(enrollments[1].state, 'active')
        self.assertFalse(enrollments[1].drop_reason_code)
        self.assertIn('Saída anterior', enrollments[1].message_ids[:1].body)
        # Prazo (técnico: 5.º dia útil do III trimestre): depois dele, só a direcção anula a pedido.
        deadline = enrollments[2]._drop_deadline()
        self.assertTrue(deadline)
        secretary = self.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'sec_drop',
                'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        late = (
            self.env['edu.enrollment.drop']
            .with_user(secretary)
            .create(
                {
                    'enrollment_ids': [(6, 0, enrollments[2].ids)],
                    'reason_code': 'withdrawal',
                    'date': deadline + timedelta(days=1),
                }
            )
        )
        self.assertIn('fora do prazo', late.warnings)
        with self.assertRaisesRegex(UserError, 'fora do prazo'):
            late.action_confirm()
        # A anulação oficiosa (processo incompleto) não tem prazo e é a escola que anula.
        late.write({'reason_code': 'incomplete', 'requested_by': 'school'})
        late.action_confirm()
        self.assertEqual((enrollments[2].state, enrollments[2].drop_exam_right), ('dropped', False))
        with self.assertRaises(UserError):
            enrollments[1].unlink()

    def test_application(self):
        application = self.env['edu.application'].create(
            {
                'name': 'Domingos Neto',
                'birth_date': date(2010, 1, 9),
                'id_number': '001122334LA040',
                'guardian_name': 'Rosa Neto',
                'guardian_phone': '+244 926 000 000',
                'guardian_relationship': 'mother',
                'desired_course_id': self.nursing.id,
                'desired_class_number': 10,
                'completed_class': 9,
            }
        )
        with self.assertRaises(UserError):
            application.action_approve()
        application.action_submit()
        with self.assertRaises(UserError):
            application.action_reject()
        application.action_review()
        with self.assertRaises(UserError):
            application.action_approve()
        application.class_id = self.class_b
        # Prova de acesso (técnico): sem nota não se aprova.
        self.assertTrue(application.admission_test_required)
        with self.assertRaisesRegex(UserError, 'prova de acesso'):
            application.action_approve()
        application.write({'has_admission_score': True, 'admission_score': 12.5})
        application.action_approve()
        self.assertEqual(application.state, 'approved')
        student = application.student_id
        self.assertEqual(student.id_number, '001122334LA040')
        self.assertEqual(student.primary_guardian_id.name, 'Rosa Neto')
        self.assertEqual(application.enrollment_id.state, 'active')
        self.assertTrue(student.matricula_number)
        # Abaixo da nota mínima (10), a candidatura é rejeitada com a fundamentação da lei.
        weak = self.env['edu.application'].create(
            {'name': 'Ermelinda Sousa', 'desired_course_id': self.nursing.id, 'desired_class_number': 10}
        )
        weak.action_submit()
        weak.write({'has_admission_score': True, 'admission_score': 9})
        self.assertEqual(weak.state, 'rejected')
        self.assertIn('art. 52.º', weak.decision_note)
        with self.assertRaises(UserError):
            application.name = 'Outro'
        with self.assertRaises(UserError):
            application.action_cancel()

    def test_transfers(self):
        carla, ana, _bento = self.students
        self.class_b.capacity = 30
        enrollment = self._enroll(carla, self.class_a)
        other = self._enroll(ana, self.class_b)
        transfer = self.env['edu.transfer'].create(
            {
                'student_id': carla.id,
                'enrollment_id': enrollment.id,
                'transfer_type': 'course_change',
                'to_class_id': self.class_cont.id,
                'reason': 'Pedido do encarregado',
            }
        )
        with self.assertRaises(UserError):
            transfer.action_complete()
        transfer.action_approve()
        transfer.action_complete()
        self.assertEqual(transfer.state, 'completed')
        self.assertEqual(transfer.from_class_id, self.class_a)
        self.assertEqual(enrollment.class_id, self.class_cont)
        self.assertEqual(enrollment.order_number, 1)
        self.assertNotIn('TENF', enrollment.subject_ids.mapped('code'))
        self.assertEqual(enrollment.subject_ids, self.class_cont.subject_line_ids.subject_id)
        exit_transfer = self.env['edu.transfer'].create(
            {
                'student_id': ana.id,
                'enrollment_id': other.id,
                'transfer_type': 'external',
                'external_school': 'Liceu do Huambo',
                'reason': 'Mudança de província',
            }
        )
        self.assertEqual(exit_transfer.from_class_id, self.class_b)  # a origem fica gravada logo no pedido
        exit_transfer.action_approve()
        self.assertIn('parecer de vaga', exit_transfer.next_step)
        with self.assertRaisesRegex(UserError, 'confirmação de vaga'):
            exit_transfer.action_complete()
        exit_transfer.write({'vacancy_confirmed': True, 'vacancy_reference': 'Ofício 12/2026'})
        exit_transfer.action_complete()
        self.assertEqual(other.state, 'transferred')
        self.assertIn('Liceu do Huambo', other.drop_reason)
        with self.assertRaises(UserError):
            exit_transfer.unlink()  # concluída: não se apaga
        # Rejeitar exige fundamentação; a decisão é da direcção.
        secretary = self.env['res.users'].create(
            {'name': 'Sec', 'login': 'sec_trf', 'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_user').id])]}
        )
        bento_enrollment = self._enroll(_bento, self.class_b)
        pending = self.env['edu.transfer'].create(
            {
                'student_id': _bento.id,
                'enrollment_id': bento_enrollment.id,
                'transfer_type': 'class_change',
                'to_class_id': self.class_a.id,
                'reason': 'Turno',
            }
        )
        with self.assertRaisesRegex(UserError, 'direcção'):
            pending.with_user(secretary).action_approve()
        with self.assertRaisesRegex(UserError, 'fundamentação'):
            pending.action_reject()
        # Mudar de turma só para uma turma da mesma classe.
        eleventh = self._class(self.nursing, 'C', 11)
        with self.assertRaisesRegex(ValidationError, 'mesma classe'):
            pending.to_class_id = eleventh
        # Entrada de outra escola: cria o aluno e matricula-o como transferido.
        incoming = self.env['edu.transfer'].create(
            {
                'transfer_type': 'incoming',
                'incoming_name': 'Zeferino Lukamba',
                'incoming_id_number': '009988776LA041',
                'origin_school': 'Instituto Médio de Saúde do Huambo',
                'to_class_id': self.class_b.id,
                'reason': 'Mudança de residência',
            }
        )
        incoming.action_approve()
        with self.assertRaisesRegex(UserError, 'guia'):
            incoming.action_complete()
        incoming.origin_documents = True
        incoming.action_complete()
        self.assertEqual(incoming.student_id.id_number, '009988776LA041')
        self.assertEqual(
            (incoming.enrollment_id.enrollment_type, incoming.enrollment_id.state), ('transfer_in', 'active')
        )
        with self.assertRaises(ValidationError):
            self.env['edu.transfer'].create(
                {'student_id': ana.id, 'enrollment_id': other.id, 'transfer_type': 'external', 'reason': 'x'}
            )

    def test_renewal(self):
        carla, ana, _bento = self.students
        self._enroll(carla, self.class_b)
        self._enroll(ana, self.class_b)
        eleventh = self._class(self.nursing, 'A', 11, year=self.next_year)
        wizard = self.env['edu.enrollment.renewal'].create(
            {'source_class_id': self.class_b.id, 'target_class_id': eleventh.id}
        )
        self.assertEqual(len(wizard.enrollment_ids), 2)
        wizard.action_confirm()
        renewed = eleventh.enrollment_ids
        self.assertEqual(len(renewed), 2)
        self.assertEqual(set(renewed.mapped('state')), {'active'})
        self.assertEqual(set(renewed.mapped('enrollment_type')), {'renewal'})
        self.assertEqual(carla.matricula_number, '2026-0001')
        # Enquanto o ano que acaba for o ano em curso, a turma actual é a dele (a lista «Matriculados este ano» não
        # se esvazia); ao passar ao ano seguinte, é a nova.
        self.assertEqual(carla.current_class_id, self.class_b)
        self.assertEqual(carla.student_status, 'enrolled')
        self.next_year.action_set_current()
        self.assertEqual(carla.current_class_id, eleventh)
        # Repetir a rematrícula não duplica.
        self.env['edu.enrollment.renewal'].create(
            {'source_class_id': self.class_b.id, 'target_class_id': eleventh.id}
        ).action_confirm()
        self.assertEqual(len(eleventh.enrollment_ids), 2)

    def test_admission_and_documents(self):
        """Fase D: idade mínima, habilitação de acesso, seriação com vagas, prazos do calendário, documentos da
        primeira matrícula e o aviso dos 60 dias à direcção e à secretaria."""
        Application = self.env['edu.application']
        self.nursing.admission_vacancies = 1
        apps = Application.create(
            [
                {
                    'name': name,
                    'desired_course_id': self.nursing.id,
                    'desired_class_number': 10,
                    'completed_class': completed,
                    'birth_date': date(2010, 3, 1),
                }
                for name, completed in (('Primeira', 9), ('Segunda', 9), ('Sem habilitação', 8))
            ]
        )
        apps.action_submit()
        apps[0].write({'has_admission_score': True, 'admission_score': 14, 'previous_average': 12})
        apps[1].write({'has_admission_score': True, 'admission_score': 14, 'previous_average': 15})
        apps[2].write({'has_admission_score': True, 'admission_score': 16})
        Application.action_rank()
        # Mesma nota: desempata a média do nível anterior; 1 vaga, os outros suplentes.
        self.assertEqual((apps[1].admission_rank, apps[1].admission_result), (2, 'waitlist'))
        self.assertEqual(apps[2].admission_result, 'admitted')
        apps[0].class_id = self.class_b
        with self.assertRaisesRegex(UserError, 'seriação'):
            apps[0].action_approve()
        apps[2].class_id = self.class_b
        with self.assertRaisesRegex(UserError, 'Habilitação de acesso'):
            apps[2].action_approve()
        # Idade mínima: 15 anos no ano da matrícula para o técnico.
        young = self.env['edu.student'].create({'name': 'Novinho', 'birth_date': date(2013, 5, 1)})
        with self.assertRaisesRegex(UserError, 'idade mínima'):
            self._enroll(young, self.class_b)
        # Fora da idade regular: só aviso.
        older = self._enroll(
            self.env['edu.student'].create({'name': 'Adulto', 'birth_date': date(2000, 1, 1)}), self.class_b
        )
        self.assertIn('Fora da idade regular', older.warning)
        # Documentos da primeira matrícula (técnico: certificado, boletim, BI, 4 fotografias).
        self.assertEqual(len(older.document_ids), 4)
        self.assertFalse(older.documents_complete)
        # 60 dias depois do início do ano: aviso à direcção e à secretaria, sem anular.
        manager = self.env['res.users'].create(
            {
                'name': 'Directora',
                'login': 'dir_d',
                'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_manager').id])],
            }
        )
        Enrollment = self.env['edu.enrollment']
        with freeze_time(older.documents_deadline + timedelta(days=1)):
            Enrollment._cron_alerts()
        self.assertTrue(older.documents_overdue)
        self.assertEqual(older.state, 'active')
        message = self.year.message_ids[:1]
        self.assertIn('Processos de matrícula incompletos', message.body)
        self.assertIn(manager.partner_id, message.partner_ids)
        older.document_ids.write({'delivered': True})
        self.assertTrue(older.documents_complete)
        # A confirmação (rematrícula) não cria lista de documentos.
        renewal = Enrollment.create(
            {'student_id': self.students[0].id, 'class_id': self.class_b.id, 'enrollment_type': 'renewal'}
        )
        self.assertFalse(renewal.document_ids)

    def test_calendar_windows(self):
        """Prazos do calendário: candidaturas só no período de inscrição; matrícula de novos alunos fora do período só
        com motivo e até ao fim do 1.º mês do II trimestre."""
        Event = self.env['edu.calendar.event']
        Event.create(
            [
                {
                    'name': 'Inscrição',
                    'academic_year_id': self.year.id,
                    'phase': 'application',
                    'date_start': date(2026, 7, 23),
                    'date_end': date(2026, 8, 6),
                },
                {
                    'name': 'Matrícula de novos alunos',
                    'academic_year_id': self.year.id,
                    'phase': 'enrollment',
                    'date_start': date(2026, 8, 16),
                    'date_end': date(2026, 8, 20),
                },
            ]
        )
        secretary = self.env['res.users'].create(
            {'name': 'Sec', 'login': 'sec_cal', 'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_user').id])]}
        )
        application = self.env['edu.application'].create({'name': 'Tardia', 'desired_course_id': self.nursing.id})
        with freeze_time('2026-09-10'):
            with self.assertRaisesRegex(UserError, 'período de inscrição'):
                application.with_user(secretary).action_submit()
            student = self.env['edu.student'].create({'name': 'Atrasado', 'birth_date': date(2010, 1, 1)})
            late = self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': self.class_b.id})
            with self.assertRaisesRegex(UserError, 'motivo do atraso'):
                late.action_confirm()
            late.late_reason = 'Transferência de outra província'
            late.action_confirm()
            self.assertEqual(late.state, 'active')

    def test_audit_enrollment(self):
        """Auditoria da fase 5: vagas da seriação, período de matrícula do ano certo, transferências e anulações."""
        carla, ana, bento = self.students
        self.class_b.capacity = 30
        Application = self.env['edu.application']
        self.nursing.admission_vacancies = 2

        def candidates(*names):
            apps = Application.create(
                [
                    {
                        'name': name,
                        'desired_course_id': self.nursing.id,
                        'desired_class_number': 10,
                        'completed_class': 9,
                        'birth_date': date(2010, 3, 1),
                    }
                    for name in names
                ]
            )
            apps.action_submit()
            apps.write({'has_admission_score': True, 'admission_score': 14})
            return apps

        first = candidates('Um', 'Dois')
        Application.action_rank()
        first.write({'class_id': self.class_b.id})
        first.action_approve()
        # Os aprovados ocupam as vagas: os que chegam depois ficam suplentes.
        late = candidates('Três', 'Quatro')
        Application.action_rank()
        self.assertEqual(set(late.mapped('admission_result')), {'waitlist'})
        # Quem perde a nota sai da seriação.
        late[0].has_admission_score = False
        Application.action_rank()
        self.assertFalse(late[0].admission_result)
        # Um transferido não entra na seriação nem precisa de ser admitido.
        self.assertFalse(Application.new({'desired_course_id': self.nursing.id, 'transfer_in': True})._edu_ranked())

        # Transferência interna aprovada: o destino não sai do ano e, mudado pela secretaria, volta a pendente.
        enrollment = self._enroll(carla, self.class_a)
        secretary = self.env['res.users'].create(
            {'name': 'Sec', 'login': 'sec_aud', 'group_ids': [(6, 0, [self.env.ref('edu_core.group_edu_user').id])]}
        )
        transfer = self.env['edu.transfer'].create(
            {
                'student_id': carla.id,
                'enrollment_id': enrollment.id,
                'transfer_type': 'class_change',
                'to_class_id': self.class_b.id,
                'reason': 'Turno',
            }
        )
        transfer.action_approve()
        next_class = self._class(self.nursing, 'A', 10, year=self.next_year)
        with self.assertRaisesRegex(ValidationError, 'mesmo ano lectivo'):
            transfer.with_user(secretary).to_class_id = next_class
        other_class = self._class(self.nursing, 'D', 10)
        transfer.with_user(secretary).to_class_id = other_class
        self.assertEqual(transfer.state, 'pending')

        # Anular só matrículas em curso; o rascunho apaga-se.
        draft = self._enroll(ana, self.class_b, confirm=False)
        with self.assertRaisesRegex(UserError, 'rascunho'):
            draft._drop('x')
        # Depois de uma saída para outra escola, não se reactiva.
        exit_enrollment = self._enroll(bento, self.class_b)
        exit_transfer = self.env['edu.transfer'].create(
            {
                'student_id': bento.id,
                'enrollment_id': exit_enrollment.id,
                'transfer_type': 'external',
                'external_school': 'Outra escola',
                'vacancy_confirmed': True,
                'vacancy_reference': 'Ofício 1/2026',
                'reason': 'Mudança',
            }
        )
        exit_transfer.action_approve()
        exit_transfer.action_complete()
        with self.assertRaisesRegex(UserError, 'entrada por transferência'):
            exit_enrollment.action_reactivate()
        with self.assertRaisesRegex(UserError, 'fechada'):
            exit_enrollment._drop('outra vez')

        # Calendário com o período de 2027/2028 (Agosto de 2027): não serve para 2026/2027.
        self.env['edu.calendar.event'].create(
            {
                'name': 'Matrícula de novos alunos',
                'academic_year_id': self.year.id,
                'phase': 'enrollment',
                'date_start': date(2027, 8, 16),
                'date_end': date(2027, 8, 20),
            }
        )
        with freeze_time('2026-10-22'):
            student = self.env['edu.student'].create({'name': 'Atrasado', 'birth_date': date(2010, 1, 1)})
            new = self.env['edu.enrollment'].create({'student_id': student.id, 'class_id': self.class_b.id})
            with self.assertRaisesRegex(UserError, 'motivo do atraso'):
                new.action_confirm()
            # A entrada por transferência tem o seu prazo e conclui-se.
            incoming = self.env['edu.transfer'].create(
                {
                    'transfer_type': 'incoming',
                    'incoming_name': 'Vem de fora',
                    'origin_school': 'Escola de origem',
                    'to_class_id': self.class_b.id,
                    'origin_documents': True,
                    'reason': 'Mudança de residência',
                }
            )
            incoming.action_approve()
            incoming.action_complete()
            self.assertEqual(incoming.enrollment_id.state, 'active')

    def test_drop_deadline_skips_breaks(self):
        """Técnico: o 5.º dia útil do III trimestre não conta os feriados nem as pausas do calendário escolar."""
        enrollment = self._enroll(self.students[0], self.class_b)
        third = self.year.trimester_ids.filtered(lambda t: t.number == 3)
        before = enrollment._drop_deadline()
        self.env['edu.calendar.event'].create(
            {
                'name': 'Pausa pedagógica',
                'academic_year_id': self.year.id,
                'event_type': 'holiday',
                'date_start': third.date_start,
                'date_end': third.date_start + timedelta(days=13),
            }
        )
        after = enrollment._drop_deadline()
        self.assertGreater(after, third.date_start + timedelta(days=13))
        self.assertGreater(after, before)
