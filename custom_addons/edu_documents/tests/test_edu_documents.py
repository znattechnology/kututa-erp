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
        action = document.action_print()
        # Os documentos escolares não passam pelo assistente do layout das facturas.
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(document.print_count, 1)

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
        document = self._document('grades')
        html = self._render('edu_documents.action_report_declaration_grades', document)
        self.assertIn('15 (QUINZE) VALORES', html)
        self.assertIn('edu-pos', html)
        term = self._document('term')
        html = self._render('edu_documents.action_report_term', term)
        self.assertIn('TERMO DE FREQUÊNCIA E APROVEITAMENTO', html)
        self.assertIn('CT1', html)
        transfer = self._document('transfer_declaration')
        self.assertIn('15 (Quinze) Valores', self._render('edu_documents.action_report_declaration_transfer', transfer))

    def test_certificate_and_diploma(self):
        self._grades(14)
        self.edu_class.action_compute_year_results()
        result = self.enrollment.year_result_id
        self.assertEqual(result.status, 'graduated')
        graduation = self.env['edu.graduation'].browse(result.action_register_graduation()['res_id'])
        graduation.write({'book_number': '3', 'page_number': '45'})
        with self.assertRaises(UserError):
            self._document('certificate', graduation_id=graduation.id)  # conclusão por emitir
        graduation.action_issue()
        certificate = self._document('certificate', graduation_id=graduation.id)
        html = self._render('edu_documents.action_report_certificate', certificate)
        for text in ('Decreto n.º 90/04', 'Componente sócio-cultural', '14 (Catorze) Valores',
                     'folha n.º 45', 'selo branco'):  # fmt: skip
            self.assertIn(text, html)
        diploma = self._document('diploma', graduation_id=graduation.id)
        html = self._render('edu_documents.action_report_diploma', diploma)
        self.assertIn('Formação Média Técnica', html)
        self.assertIn(graduation.diploma_number, html)

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
        for label in ('>NPP<', '>NPT<', '>CT<', '>FJ<', '>FI<', '>CF<', '>PG<', '>CA<', 'Neg.', 'Resultado'):
            self.assertIn(label, html)
        self.assertIn('ep-neg', html)
        self.assertIn('NPP - Nota do Professor', html)
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
        lp = self.subjects.filtered(lambda s: s.code == 'LP')
        mini = self.env['edu.pauta.print'].create(
            {'class_id': self.edu_class.id, 'kind': 'mini', 'subject_id': lp.id, 'trimester_id': trimesters[-1].id}
        )
        html = self._render('edu_documents.action_report_mini_pauta', mini)
        self.assertIn('MINI-PAUTA', html)
        self.assertIn('CT3', html)
        # Só até ao trimestre escolhido, e sem a classificação final antes do último trimestre.
        first = self.edu_class.academic_year_id.trimester_ids.sorted('number')[:1]
        mini.trimester_id = first
        html = self._render('edu_documents.action_report_mini_pauta', mini)
        self.assertIn('CT1', html)
        self.assertNotIn('CT2', html)
        self.assertNotIn('>CF<', html)
        self.assertEqual(mini.action_preview()['report_type'], 'qweb-html')
        self.assertEqual(self.edu_class.action_print_class_list()['report_type'], 'qweb-html')
        self.assertIn('RELAÇÃO NOMINAL', self._render('edu_documents.action_report_class_list', self.edu_class))
        self.assertIn('HORÁRIO ESCOLAR', self._render('edu_documents.action_report_class_schedule', self.edu_class))
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
        guide = self._document('transfer_guide', transfer_id=transfer.id)
        html = self._render('edu_documents.action_report_transfer_guide', guide)
        self.assertIn('DIRECÇÃO DO INSTITUTO MÉDIO DE SAÚDE DE LUANDA', html)
        self.assertIn('vai transferida para', html)
