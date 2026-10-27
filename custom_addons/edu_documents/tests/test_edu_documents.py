from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduDocuments(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                'edu_is_school': True,
                'edu_director_name': 'Mariano Hungulo',
                'edu_pedagogical_director_name': 'Julina Cacocolo',
                'edu_document_city': 'Sumbe',
                'edu_letterhead_subtitle': 'II Ciclo do Ensino Técnico Profissional de Saúde',
            }
        )
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
        year13 = cls.course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 13)
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': cls.course.id, 'curriculum_year_id': year13.id}
        )
        cls.student = cls.env['edu.student'].create(
            {
                'name': 'Ana Kiala',
                'gender': 'female',
                'birth_date': date(2007, 5, 10),
                'father_name': 'João Kiala',
                'mother_name': 'Maria Kiala',
                'birthplace': 'Sumbe',
                'birth_municipality': 'Sumbe',
                'birth_state_id': cls.env.ref('l10n_ao.state_ao_cus').id,
                'id_number': '006543210CS045',
                'process_number': '1520',
            }
        )
        cls.subjects = cls.edu_class.subject_line_ids.subject_id.filtered(lambda s: s.code in ('LP', 'PTEC'))
        cls.enrollment = cls.env['edu.enrollment'].create(
            {'student_id': cls.student.id, 'class_id': cls.edu_class.id, 'subject_ids': [Command.set(cls.subjects.ids)]}
        )
        cls.enrollment.action_confirm()

    def _render(self, xmlid, records):
        report = self.env.ref(xmlid)
        html = self.env['ir.actions.report']._render_qweb_html(report.report_name, records.ids)[0]
        return html.decode()

    def _grades(self, score):
        for subject in self.subjects:
            for trimester in self.year.trimester_ids:
                for kind in ('continuous', 'trimester_test'):
                    # Técnico: o último trimestre não tem prova trimestral (só a NPP; há a prova global).
                    last = trimester == self.year.trimester_ids.sorted('number')[-1:]
                    if kind == 'trimester_test' and last and self.edu_class.level_id.subsystem == 'technical':
                        continue
                    assessment = self.env['edu.assessment'].create(
                        {
                            'name': kind,
                            'class_id': self.edu_class.id,
                            'subject_id': subject.id,
                            'trimester_id': trimester.id,
                            'assessment_type': kind,
                        }  # fmt: skip
                    )
                    assessment.action_fill_students()
                    assessment.grade_ids.score = score

        # Técnico: a prova global da disciplina (sem ela, a disciplina não fica completa).
        last = self.year.trimester_ids.sorted('number')[-1]
        for subject in self.subjects:
            line = self.edu_class.subject_line_ids.filtered(lambda line, s=subject: line.subject_id == s)
            if self.edu_class.level_id.subsystem == 'technical' and line.has_global_exam:
                assessment = self.env['edu.assessment'].create(
                    {
                        'name': 'PG',
                        'class_id': self.edu_class.id,
                        'subject_id': subject.id,
                        'trimester_id': last.id,
                        'assessment_type': 'global_exam',
                    }  # fmt: skip
                )
                assessment.action_fill_students()
                assessment.grade_ids.score = score

    def _document(self, kind, **vals):
        document = self.env['edu.document'].create(
            {'document_type': kind, 'student_id': self.student.id, 'enrollment_id': self.enrollment.id, **vals}
        )
        document.action_issue()
        return document

    def test_frequency_declaration(self):
        document = self._document('frequency', purpose='efeitos de bolsa de estudo')
        self.assertEqual(document.name, 'DSN/Nº01/2026-2027')
        self.assertEqual(self._document('frequency').name, 'DSN/Nº02/2026-2027')
        html = self._render('edu_documents.action_report_declaration_frequency', document)
        for text in ('Ana Kiala', 'filha de', 'nascida a 10 de Maio de 2007', '13ª (Décima Terceira) Classe',
                     'efeitos de bolsa de estudo', 'A SUBDIRECTORA PEDAGÓGICA', '//MARIANO HUNGULO//',
                     'DSN/Nº01/2026-2027', 'Província de Cuanza Sul'):  # fmt: skip
            self.assertIn(text, html)
        # Como no secPed: título com o tipo, cabeçalho de Estado, «Está a frequentar» no ano em curso, o regime e o
        # rodapé do Anexo V; o que falta na ficha (o processo n.º, o emissor do BI) sai como linha a preencher.
        for text in ('DECLARAÇÃO DE FREQUÊNCIA', 'Ministério da Educação', 'Está a frequentar', 'em regime',
                     'Anexo V · Despacho n.º 60/08', 'processo n.º', 'edu-blank'):  # fmt: skip
            self.assertIn(text, html)
        action = document.action_print()
        # Os documentos escolares não passam pelo assistente do layout das facturas; ver não conta como impressão.
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(document.print_count, 0)
        Report = self.env['ir.actions.report']
        Report._render_qweb_pdf('edu_documents.action_report_declaration_frequency', document.ids)
        self.assertEqual(document.print_count, 1)
        self.assertNotIn('2.ª VIA', self._render('edu_documents.action_report_declaration_frequency', document))
        Report._render_qweb_pdf('edu_documents.action_report_declaration_frequency', document.ids)
        self.assertIn('2.ª VIA', self._render('edu_documents.action_report_declaration_frequency', document))
        # Os dados que faltam completam-se no documento e ficam na ficha do aluno.
        self.assertFalse(document.identity_complete)
        draft = self.env['edu.document'].create(
            {'document_type': 'enrollment', 'student_id': self.student.id, 'enrollment_id': self.enrollment.id}
        )
        draft.student_process_number = '1520-A'
        self.assertEqual(self.student.process_number, '1520-A')
        draft.action_issue()
        self.assertTrue(draft.name.startswith('DM/'))
        html = self._render('edu_documents.action_report_declaration_enrollment', draft)
        self.assertIn('DECLARAÇÃO DE MATRÍCULA', html)
        self.assertIn('se encontra regularmente matriculada', html)

    def test_preview(self):
        # Visualizar mostra o documento na própria aplicação (HTML), sem o emitir nem contar como impressão.
        draft = self.env['edu.document'].create(
            {'document_type': 'frequency', 'student_id': self.student.id, 'enrollment_id': self.enrollment.id}
        )
        action = draft.action_preview()
        self.assertEqual((action['type'], action['report_type']), ('ir.actions.report', 'qweb-html'))
        self.assertEqual(action['report_name'], 'edu_documents.report_declaration_frequency')
        self.assertEqual(action['context']['active_ids'], [draft.id])
        self.assertEqual((draft.state, draft.print_count), ('draft', 0))
        self.assertIn('RASCUNHO', self._render('edu_documents.action_report_declaration_frequency', draft))

    def test_grades_and_term(self):
        with self.assertRaises(UserError):
            self._document('grades')  # ainda sem classificações finais
        self._grades(15)
        # Sem a decisão do ano (conselho por fechar), a declaração com notas não sai (como no secPed).
        with self.assertRaisesRegex(UserError, 'feche o conselho'):
            self._document('grades')
        self.edu_class.action_compute_year_results()
        document = self._document('grades')
        html = self._render('edu_documents.action_report_declaration_grades', document)
        self.assertIn('15 (QUINZE) VALORES', html)
        self.assertIn('edu-pos', html)
        term = self._document('term')
        html = self._render('edu_documents.action_report_term', term)
        self.assertIn('TERMO DE FREQUÊNCIA E APROVEITAMENTO DO CURSO TÉCNICO DE', html)
        for text in ('CT1', 'SITUAÇÃO NO FIM DO ANO', 'COMPORTAMENTO', 'Coordenador(a) de Turma', 'REGIME:'):
            self.assertIn(text, html)
        # Histórico do aluno, como no secPed: um ano por linha, o resumo, o termo do ano e o termo do curso.
        result = self.enrollment.year_result_id
        self.assertEqual(self.student.year_result_ids, result)
        self.assertIn('1 ano lectivo: concluiu o curso.', self.student.history_summary)
        self.assertEqual(self.student.action_view_history()['res_model'], 'edu.student')
        result.action_print_year_term()
        year_term = (
            self.env['ir.actions.report']._render_qweb_html('edu_documents.report_year_term', result.ids)[0].decode()
        )
        for text in ('REGISTO ACADÉMICO DO ANO', 'Assiduidade', 'F. J.', 'Resultado final', 'Director(a) de Turma'):
            self.assertIn(text, year_term)
        self.student.action_print_course_term()
        self.student.action_print_course_term()
        # Reaproveita o termo já emitido (não cria outro).
        self.assertEqual(len(self.student.document_ids.filtered(lambda d: d.document_type == 'term')), 1)
        transfer = self._document('transfer_declaration')
        self.assertIn('15 (Quinze) Valores', self._render('edu_documents.action_report_declaration_transfer', transfer))

    def test_certificate_and_diploma(self):
        self._grades(14)
        self.edu_class.action_compute_year_results()
        result = self.enrollment.year_result_id
        self.assertEqual(result.status, 'graduated')
        # Lista dos exames especiais: por disciplina, com a nota anterior e o que falta.
        requirement = self.env['edu.exam.requirement'].create(
            {
                'year_result_id': result.id,
                'subject_result_id': self.enrollment.subject_result_ids[:1].id,
                'kind': 'improvement',
            }
        )
        self.assertEqual(requirement.action_print_listing()['report_type'], 'qweb-html')
        html = self._render('edu_documents.action_report_listing_exam_requirement', requirement)
        for text in ('EXAMES ESPECIAIS', self.student.name, 'Melhoria de nota', 'Por realizar', '14'):
            self.assertIn(text, html)
        requirement.unlink()
        # Registar conclusões pela turma da classe final, como no secPed.
        wizard = self.env['edu.graduation.register'].create({'academic_year_id': self.year.id})
        self.assertIn(self.edu_class, wizard.final_class_ids)
        wizard.class_id = self.edu_class
        self.assertEqual(wizard.result_ids, result)
        wizard.action_register_all()
        result.invalidate_recordset(['graduation_id'])
        graduation = result.graduation_id
        self.assertTrue(graduation)
        self.course.training_area = 'Saúde'
        graduation.write({'book_number': '3', 'page_number': '45'})
        with self.assertRaises(UserError):
            self._document('certificate', graduation_id=graduation.id)  # conclusão por emitir
        graduation.action_issue()
        certificate = self._document('certificate', graduation_id=graduation.id)
        html = self._render('edu_documents.action_report_certificate', certificate)
        for text in ('Decreto n.º 90/04', 'Componente sócio-cultural', '14 (Catorze) Valores',
                     'folha n.º 45', 'selo branco'):  # fmt: skip
            self.assertIn(text, html)
        for text in ('em regime pós-laboral', 'Área de Formação de Saúde', 'Classificação final do curso = ('):
            self.assertIn(text, html)
        # Imprimir o diploma directamente da conclusão: emite o documento uma vez e reaproveita-o.
        graduation.action_print_diploma()
        graduation.action_print_diploma()
        diploma = graduation.document_ids.filtered(lambda d: d.document_type == 'diploma')
        self.assertEqual(len(diploma), 1)
        # Ver não emite o diploma; imprimir o PDF dá-lhe o número.
        self.assertEqual(diploma.state, 'draft')
        self.env['ir.actions.report']._render_qweb_pdf('edu_documents.action_report_diploma', diploma.ids)
        self.assertEqual((diploma.state, diploma.print_count), ('issued', 1))
        html = self._render('edu_documents.action_report_diploma', diploma)
        self.assertIn('Formação Média Técnica', html)
        self.assertIn(graduation.diploma_number, html)
        # Verificar e assinar (irreversível; quem marca fica registado).
        self.assertEqual(graduation.diploma_state, 'to_verify')
        with self.assertRaises(UserError):
            graduation.action_mark_signed()
        graduation.action_mark_verified()
        graduation.action_mark_signed()
        self.assertEqual((graduation.diploma_state, graduation.signed_by_id), ('signed', self.env.user))

    def test_class_documents(self):
        self._grades(9)
        trimesters = self.edu_class.academic_year_id.trimester_ids.sorted('number')
        wizard = self.env['edu.pauta.print'].create({'class_id': self.edu_class.id, 'kind': 'final'})
        # Por omissão, o trimestre em curso (ou o último, num ano fechado).
        self.assertEqual(wizard.trimester_id, trimesters.filtered('is_current')[:1] or trimesters[-1:])
        wizard.trimester_id = trimesters[-1]
        html = self._render('edu_documents.action_report_pauta', wizard)
        # Estrutura do secPed: cabeçalho oficial, colunas do trimestre e bloco final, Neg. e Resultado, legenda.
        self.assertIn('MAPA DE APROVEITAMENTO DO IIIº TRIMESTRE', html)
        self.assertIn('REPÚBLICA DE ANGOLA', html)
        self.assertIn('Visto', html)
        # Técnico: P1 e P2; no 3.º trimestre a PG no lugar da P2 (e «—» nas disciplinas sem prova global).
        for label in ('>P1<', '>PG<', '>CT<', '>FJ<', '>FI<', '>CF<', '>CA<', '>CFD<', 'Neg.', 'Resultado'):
            self.assertIn(label, html)
        self.assertNotIn('>P2<', html)
        self.assertNotIn('>NPP<', html)
        # Todas as disciplinas do plano aparecem, mesmo as que o aluno não tem (sem notas).
        self.assertEqual(wizard._subjects(), wizard._subjects() | self.edu_class.subject_line_ids.subject_id)
        self.assertIn('ep-neg', html)
        # Notas coloridas e com uma casa decimal, como na pauta do secPed (o CT do técnico não arredonda: 2,63 → 2,6).
        cells = [cell for row in wizard._pauta_data()['rows'] for found in row['cells'].values() for cell in found]
        decimals = [text for text, tone in cells if ',' in text]
        self.assertTrue(decimals)
        self.assertEqual([text for text in decimals if len(text.split(',')[1]) != 1], [])
        self.assertTrue(all(tone in ('pos', 'neg') for text, tone in cells if ',' in text))
        self.assertIn('P1 - Nota do Professor', html)
        self.assertIn('aprovação mínima 10 valores', html)
        self.assertIn('Professor', html)
        # Visualização: uma só tabela com scroll horizontal; PDF: dividida por folhas A3, como no secPed.
        self.assertIn('class="ep-scroll"', html)
        self.assertNotIn('Folha 1/', html)
        pdf_html = (
            self.env['ir.actions.report']
            ._render_qweb_html('edu_documents.report_pauta', wizard.ids, data={'report_type': 'pdf'})[0]
            .decode()
        )
        self.assertIn('Folha 1/', pdf_html)
        self.assertNotIn('class="ep-scroll"', pdf_html)
        # Pauta de um trimestre: as colunas do trimestre, sem a classificação do ano nem a situação.
        wizard.trimester_id = trimesters[0]
        html = self._render('edu_documents.action_report_pauta', wizard)
        self.assertIn('MAPA DE APROVEITAMENTO DO Iº TRIMESTRE', html)
        self.assertIn('>CT<', html)
        self.assertNotIn('>CA<', html)
        self.assertNotIn('Resultado', html)
        self.assertNotIn('Transita', html)
        # Mini-pauta como a do secPed: mapa condensado da turma no trimestre (letra e nome por disciplina, CT/CF
        # com FJ e FI, média), A4 horizontal, cabeçalho e assinaturas da pauta.
        mini = self.env['edu.pauta.print'].create(
            {'class_id': self.edu_class.id, 'kind': 'mini', 'trimester_id': trimesters[-1].id}
        )
        html = self._render('edu_documents.action_report_mini_pauta', mini)
        self.assertIn('MAPA DE APROVEITAMENTO REFERENTE AO III TRIMESTRE', html)
        for text in ('A)', 'Língua Portuguesa', '>CF<', '>FJ<', '>FI<', 'Méd.', 'Director(a) de Turma', 'Visto'):
            self.assertIn(text, html)
        self.assertIn('mp-neg', html)
        mini.trimester_id = trimesters[0]
        html = self._render('edu_documents.action_report_mini_pauta', mini)
        self.assertIn('REFERENTE AO I TRIMESTRE', html)
        self.assertIn('>CT1<', html)
        self.assertNotIn('>CF<', html)
        self.assertEqual(mini.action_preview()['report_type'], 'qweb-html')
        self.assertEqual(self.edu_class.action_print_class_list()['report_type'], 'qweb-html')
        self.assertIn('RELAÇÃO NOMINAL', self._render('edu_documents.action_report_class_list', self.edu_class))
        # Horário no estilo da pauta: título, grelha Hora × dias e as assinaturas da direcção.
        schedule = self._render('edu_documents.action_report_class_schedule', self.edu_class)
        for text in ('HORÁRIO DA TURMA', 'REPÚBLICA DE ANGOLA', '>Hora<', '>Segunda<', '>Sexta<', 'ANO LECTIVO:'):
            self.assertIn(text, schedule)
        self.assertNotIn('>Sábado<', schedule)
        # Docentes: corpo docente, horário do professor, atribuições e directores de turma.
        teacher = self.env['hr.employee'].create({'name': 'Rita Docente', 'edu_is_teacher': True})
        subject = self.edu_class.subject_line_ids.subject_id[:1]
        self.env['edu.teaching.assignment'].create(
            {'class_id': self.edu_class.id, 'subject_id': subject.id, 'teacher_id': teacher.id}
        )
        public = self.env['hr.employee.public'].browse(teacher.id)
        self.assertEqual(public.action_print_teachers()['report_type'], 'qweb-html')
        html = self._render('edu_documents.action_report_teachers', public)
        for text in ('CORPO DOCENTE', 'Rita Docente', subject.name, 'Tempos/semana'):
            self.assertIn(text, html)
        self.assertIn('HORÁRIO DO PROFESSOR', self._render('edu_documents.action_report_teacher_schedule', public))
        assignments = self.env['edu.teaching.assignment'].search([('class_id', '=', self.edu_class.id)])
        html = self._render('edu_documents.action_report_assignments', assignments)
        for text in ('ATRIBUIÇÕES DE DISCIPLINAS', 'Rita Docente', 'Sem professor', 'Ano todo'):
            self.assertIn(text, html)
        html = self._render('edu_documents.action_report_class_directors', self.edu_class)
        for text in ('DIRECTORES DE TURMA', 'Sem director', '0 DE 1 TURMAS COM DIRECTOR'):
            self.assertIn(text, html)
        # Listas das matrículas, com o cabeçalho e as assinaturas da pauta.
        self.assertEqual(self.enrollment.action_print_listing()['report_type'], 'qweb-html')
        # Sem linhas escolhidas, imprime o que a lista mostra com os filtros.
        Enrollment = self.env['edu.enrollment'].with_context(active_model='edu.enrollment')
        action = Enrollment.with_context(active_domain=[('id', '=', self.enrollment.id)]).action_print_listing()
        self.assertEqual(action['context']['active_ids'], self.enrollment.ids)
        with self.assertRaises(UserError):
            Enrollment.with_context(active_domain=[('id', '=', 0)]).action_print_listing()
        html = self._render('edu_documents.action_report_listing_enrollment', self.enrollment)
        for text in ('LISTA DE MATRÍCULAS', self.student.name, 'REPÚBLICA DE ANGOLA'):
            self.assertIn(text, html)
        html = self._render('edu_documents.action_report_listing_student', self.student)
        self.assertIn('LISTA DE ALUNOS', html)
        application = self.env['edu.application'].create(
            {'name': 'Candidata Teste', 'desired_course_id': self.course.id, 'desired_class_number': 10}
        )
        application.action_submit()
        html = self._render('edu_documents.action_report_listing_application', application)
        self.assertIn('LISTA DE CANDIDATURAS', html)
        receipt = self._render('edu_documents.action_report_application_receipt', application)
        for text in ('COMPROVATIVO DE CANDIDATURA', application.reference, 'não constitui garantia de admissão'):
            self.assertIn(text, receipt)
        # Plano curricular: a matriz por componentes com o cabeçalho da pauta, a partir do curso.
        self.assertEqual(self.course.action_print_curriculum()['report_type'], 'qweb-html')
        plan = self._render('edu_documents.action_report_curriculum', self.course.curriculum_id)
        for text in ('PLANO CURRICULAR', 'REPÚBLICA DE ANGOLA', 'Sociocultural', 'Tempos por semana', 'CURSO:'):
            self.assertIn(text, plan)
        # Com o edu_fees, o cartão só se imprime depois de emitido (taxa paga e fotografia): testado lá.
        if 'edu.student.card' not in self.env:
            self.assertIn(
                'Pessoal e intransmissível', self._render('edu_documents.action_report_student_card', self.student)
            )

    def test_transfer_guide(self):
        transfer = self.env['edu.transfer'].create(
            {
                'student_id': self.student.id,
                'enrollment_id': self.enrollment.id,
                'transfer_type': 'external',
                'external_school': 'Instituto Médio de Saúde de Luanda',
                'reason': 'Mudança de residência',
            }  # fmt: skip
        )
        with self.assertRaisesRegex(UserError, 'concluída'):
            self._document('transfer_guide', transfer_id=transfer.id).action_issue()
        transfer.action_approve()
        transfer.write({'vacancy_confirmed': True})
        transfer.action_complete()
        self.assertEqual(transfer.action_print_transfer_guide()['report_type'], 'qweb-html')
        guide = transfer.document_ids.filtered(lambda d: d.document_type == 'transfer_guide')
        self.assertEqual(guide.state, 'issued')
        html = self._render('edu_documents.action_report_transfer_guide', guide)
        listing = self._render('edu_documents.action_report_listing_transfer', transfer)
        self.assertIn('TRANSFERÊNCIAS', listing)
        self.assertIn('Instituto Médio de Saúde de Luanda', listing)
        self.assertIn('DIRECÇÃO DO INSTITUTO MÉDIO DE SAÚDE DE LUANDA', html)
        self.assertIn('vai transferida para', html)

    def test_exam_calendar_print(self):
        """Calendário de provas da turma e escala de vigilância do professor, com o cabeçalho da pauta."""
        room = self.env['edu.room'].create({'name': 'Sala 7', 'code': 'S7'})
        teacher = self.env['hr.employee'].create({'name': 'Zeca Vigilante', 'edu_is_teacher': True})
        period = self.env['edu.exam.period'].create(
            {'name': 'Provas do I Trimestre', 'date_start': date(2026, 12, 9), 'date_end': date(2026, 12, 18)}
        )
        period.planner_mark(self.subjects[0].id, '2026-12-09', 8.0, 10.0, self.edu_class.ids)
        session = period.session_ids
        self.env['edu.exam.period'].planner_set_room(session.id, room.id)
        self.env['edu.exam.period'].planner_set_supervisor(session.id, teacher.id)
        period.planner_print('class', self.edu_class.id)
        document = self.env['edu.exam.calendar.print'].search([], order='id desc', limit=1)
        html = self._render('edu_documents.action_report_exam_calendar', document)
        for text in ('CALENDÁRIO DE PROVAS', 'Quarta-feira, 9 de Dezembro', '08:00–10:00', 'Zeca Vigilante', 'Sala 7'):
            self.assertIn(text, html)
        period.planner_print('teacher', teacher.id)
        document = self.env['edu.exam.calendar.print'].search([], order='id desc', limit=1)
        html = self._render('edu_documents.action_report_exam_calendar', document)
        self.assertIn('ESCALA DE VIGILÂNCIA', html)
        self.assertIn('13ª A', html)
        # Lista das sessões de exame: por dia, com a sala e o vigilante.
        self.assertEqual(session.action_print_listing()['report_type'], 'qweb-html')
        html = self._render('edu_documents.action_report_listing_exam_session', session)
        for text in ('SESSÕES DE EXAME', 'Quarta-feira, 9 de Dezembro', '08:00–10:00', 'Zeca Vigilante', 'Sala 7'):
            self.assertIn(text, html)

    def test_grade_grid_print(self):
        """Na grelha «Notas da turma», a secretaria visualiza e imprime a pauta da turma do trimestre."""
        trimester = self.edu_class.academic_year_id.trimester_ids.sorted('number')[:1]
        Grid = self.env['edu.grade.grid']
        preview = Grid.grid_print(self.edu_class.id, trimester.id, True)
        self.assertEqual(preview['report_type'], 'qweb-html')
        self.assertEqual(preview['report_name'], 'edu_documents.report_pauta')
        self.assertEqual(Grid.grid_print(self.edu_class.id, trimester.id, False)['report_type'], 'qweb-pdf')

    def test_mini_pauta_page(self):
        """Página «Mini-pauta», como no secPed: ano, turma e trimestre; abre a mini-pauta que já existe."""
        Page = self.env['edu.mini.pauta']
        options = Page.page_options()
        self.assertIn(self.edu_class.id, [c['id'] for c in options['classes']])
        trimester = options['trimesters'][0]['id']
        action = Page.page_open(self.edu_class.id, trimester, True)
        self.assertEqual(
            (action['report_name'], action['report_type']), ('edu_documents.report_mini_pauta', 'qweb-html')
        )
        self.assertEqual(Page.page_open(self.edu_class.id, trimester, False)['report_type'], 'qweb-pdf')
        with self.assertRaises(UserError):
            Page.page_open(self.edu_class.id, False, True)

    def test_declarations_page(self):
        """Página «Declarações», como no secPed: o aluno pela turma ou pelo nome, os dados de identificação, ver
        (rascunho, sem número), emitir e imprimir (com número) e a 2.ª via."""
        Page = self.env['edu.declaration.page']
        Picker = self.env['edu.student.picker']
        options = Page.page_options()
        self.assertIn(self.edu_class.id, [c['id'] for c in Picker.picker_options()['classes']])
        self.assertEqual(
            [t['key'] for t in options['types']], ['frequency', 'grades', 'enrollment', 'transfer_declaration']
        )
        rows = Picker.class_students(self.edu_class.id)
        self.assertIn(self.enrollment.id, [r['enrollment_id'] for r in rows])
        found = Picker.search_students(self.year.id, self.student.name[:4])
        self.assertIn(self.enrollment.id, [r['enrollment_id'] for r in found])
        self.assertEqual(Picker.search_students(self.year.id, 'a'), [])

        data = Page.student_data(self.enrollment.id, 'frequency')
        self.assertFalse(data['blocked'])
        self.assertTrue(data['blocked'] is False and Page.student_data(self.enrollment.id, 'grades')['blocked'])
        identity = {**data['identity'], 'process_number': '77-B'}
        action = Page.preview(self.enrollment.id, 'frequency', identity, 'efeitos de bolsa')
        self.assertEqual(action['report_type'], 'qweb-html')
        self.assertEqual(self.student.process_number, '77-B')
        draft = self.env['edu.document'].search([('enrollment_id', '=', self.enrollment.id), ('state', '=', 'draft')])
        self.assertEqual((len(draft), draft.purpose), (1, 'efeitos de bolsa'))
        # Ver outra vez reaproveita o rascunho; emitir dá-lhe o número.
        Page.preview(self.enrollment.id, 'frequency', identity, '')
        Page.issue_and_print(self.enrollment.id, 'frequency', identity, '')
        self.assertEqual(draft.state, 'issued')
        self.assertTrue(draft.name.startswith('DSN/'))
        documents = Page.student_data(self.enrollment.id, 'frequency')['documents']
        self.assertEqual([d['id'] for d in documents], draft.ids)
        Page.reprint(draft.id)
        self.assertEqual(draft.print_count, 0)
        # O PDF (o «Imprimir» da janela) é que conta.
        self.env['ir.actions.report']._render_qweb_pdf('edu_documents.action_report_declaration_frequency', draft.ids)
        self.assertEqual(draft.print_count, 1)
        with self.assertRaises(UserError):
            Page.preview(self.enrollment.id, 'grades', identity, '')

    def test_student_history_page(self):
        """Histórico do aluno, como no secPed: um ano por linha, o ano em curso, o resultado no passado, os termos."""
        Page = self.env['edu.history.page']
        data = Page.student_history(self.student.id)
        self.assertEqual([r['result'] for r in data['rows']], ['Em curso'])
        self.assertFalse(data['has_results'])
        with self.assertRaises(UserError):
            Page.print_course_term(self.student.id)
        result = self.env['edu.year.result'].create({'enrollment_id': self.enrollment.id})
        result.action_manual_promote()
        data = Page.student_history(self.student.id)
        row = data['rows'][0]
        self.assertEqual((row['year'], row['class'], row['result']), ('2026/2027', '13ª A', 'Concluiu'))
        self.assertEqual(row['year_result_id'], result.id)
        self.assertFalse(data['has_attendance'])
        self.assertEqual(Page.print_year_term(result.id)['report_type'], 'qweb-html')
        self.assertEqual(Page.print_course_term(self.student.id)['report_type'], 'qweb-html')
        self.assertEqual(Page.subject_history(self.student.id)['type'], 'ir.actions.act_window')

    def test_graduations_page(self):
        """Diplomas e certificados, como no secPed: registar conclusões pela turma da classe final, a lista por ano
        e curso com o resumo, emitir, o diploma e o certificado, verificar e assinar."""
        self._grades(14)
        self.edu_class.action_compute_year_results()
        result = self.enrollment.year_result_id
        Page = self.env['edu.graduation.page']
        options = Page.page_options()
        self.assertEqual(options['year_id'], self.year.id)
        self.assertTrue(options['is_manager'])
        self.assertEqual(Page.graduations(self.year.id)['summary']['total'], 0)
        self.assertIn(self.edu_class.id, [c['id'] for c in Page.final_classes(self.year.id)])
        finishers = Page.finishers(self.edu_class.id)
        self.assertEqual([(f['result_id'], f['registered']) for f in finishers], [(result.id, False)])
        self.assertEqual(Page.register([result.id]), {'done': 1, 'errors': []})
        self.assertTrue(Page.finishers(self.edu_class.id)[0]['registered'])
        self.assertEqual(Page.register([result.id])['done'], 0)

        data = Page.graduations(self.year.id, self.course.id)
        row = data['rows'][0]
        self.assertEqual((row['diploma_state'], row['diploma_label']), ('draft', 'Por emitir'))
        self.assertEqual(data['summary'], {'total': 1, 'signed': 0, 'to_verify': 0, 'to_sign': 0, 'draft': 1})
        with self.assertRaises(UserError):
            Page.print_document(row['id'], 'diploma')
        row = Page.issue(row['id'])
        self.assertEqual(row['diploma_label'], 'Por verificar')
        self.assertTrue(row['diploma_number'])
        self.assertEqual(Page.print_document(row['id'], 'diploma')['report_type'], 'qweb-html')
        self.assertEqual(Page.print_document(row['id'], 'certificate')['report_type'], 'qweb-html')
        self.assertEqual(Page.verify(row['id'])['diploma_label'], 'Por assinar')
        self.assertEqual(Page.sign(row['id'])['diploma_label'], 'Assinado')
        self.assertEqual(Page.graduations(False)['summary']['signed'], 1)

    def test_student_history_decision(self):
        """A direcção altera a decisão do ano no Histórico do aluno, com o fundamento; volta-se à automática."""
        result = self.env['edu.year.result'].create({'enrollment_id': self.enrollment.id})
        result.action_recompute()
        Page = self.env['edu.history.page']
        row = Page.student_history(self.student.id)['rows'][0]
        self.assertFalse(row['manual'])
        self.assertTrue(row['terminal'])
        with self.assertRaises(UserError):
            Page.decide(result.id, 'retained', '  ')
        with self.assertRaises(UserError):
            Page.decide(result.id, 'conditional', 'Acta n.º 3')  # numa classe terminal não há «com atraso»
        data = Page.decide(result.id, 'promoted', 'Recurso deferido, despacho n.º 12')
        row = data['rows'][0]
        self.assertEqual((row['status'], row['result'], row['manual']), ('graduated', 'Concluiu', True))
        self.assertIn('Recurso deferido', row['decision_note'])
        self.assertEqual(result.decided_by_id, self.env.user)
        self.assertTrue(result.decided_date)
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'secretaria_decisao',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        self.assertFalse(Page.with_user(clerk).student_history(self.student.id)['can_decide'])
        with self.assertRaises(UserError):
            Page.with_user(clerk).decide(result.id, 'retained', 'Sem direito')
        row = Page.reset_decision(result.id)['rows'][0]
        self.assertFalse(row['manual'])
        self.assertFalse(result.decided_date)

    def test_appeals_page(self):
        """Reapreciações, conforme a lei: registar o pedido (aluno, disciplina, pauta, requerente, documentos), admitir,
        deliberação sem provimento → Conselho Pedagógico, deferido corrige a nota, informar o interessado."""
        self._grades(9)
        first = self.year.trimester_ids.sorted('number')[0]
        first.action_close()
        Page = self.env['edu.appeal.page']
        options = Page.request_options(self.enrollment.id)
        self.assertTrue(options['technical'])
        self.assertEqual([m['id'] for m in options['moments']], [first.id, 0])
        subject = self.subjects[0]
        detail = Page.create_request(
            {
                'enrollment_id': self.enrollment.id,
                'subject_id': subject.id,
                'trimester_id': first.id,
                'requester_type': 'guardian',
                'requester_name': 'Maria Kiala',
                'posting_date': options['today'],
                'reason': 'A prova trimestral foi mal corrigida.',
                'attachments': [{'name': 'requerimento.txt', 'datas': 'UmVxdWVyaW1lbnRv'}],
            }
        )
        self.assertEqual((detail['state'], detail['requester']), ('pending', 'Encarregado de educação: Maria Kiala'))
        self.assertEqual([a['name'] for a in detail['attachments']], ['requerimento.txt'])
        self.assertEqual(Page.appeals('open')['open_count'], 1)
        appeal_id = detail['id']
        detail = Page.admit(appeal_id, False)
        self.assertEqual(detail['state'], 'review')
        self.assertTrue(detail['grades'])
        detail = Page.deliberate(
            appeal_id, {'outcome': 'deny', 'text': 'O conselho manteve a nota.', 'minutes_ref': '7'}
        )
        self.assertEqual(detail['state'], 'appealed')
        grade = self.env['edu.grade'].browse(detail['grades'][0]['id'])
        detail = Page.deliberate(
            appeal_id, {'outcome': 'grant', 'text': 'Provido.', 'grade_id': grade.id, 'new_score': 12}
        )
        self.assertEqual((detail['state'], grade.score), ('granted', 12))
        self.assertIn('→ 12', detail['grade'])
        detail = Page.notify(appeal_id, False)
        self.assertTrue(detail['notified'])
        done = Page.appeals('done')
        self.assertEqual([r['id'] for r in done['rows']], [appeal_id])
