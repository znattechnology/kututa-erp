from datetime import date

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'edu')
class TestEduRecords(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
                'requires_final_project': True,
            }
        )
        last = cls.course.curriculum_id.year_ids.filtered(lambda y: y.class_number == 13)
        cls.edu_class = cls.env['edu.class'].create(
            {'name': 'A', 'course_id': cls.course.id, 'curriculum_year_id': last.id}
        )
        cls.student = cls.env['edu.student'].create({'name': 'Ana Kiala', 'process_number': '1520'})
        cls.subjects = cls.edu_class.subject_line_ids.subject_id[:2]
        cls.enrollment = cls.env['edu.enrollment'].create(
            {'student_id': cls.student.id, 'class_id': cls.edu_class.id, 'subject_ids': [Command.set(cls.subjects.ids)]}
        )
        cls.enrollment.action_confirm()

    def _grades(self, score_by_subject):
        for subject, score in zip(self.subjects, score_by_subject, strict=True):
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

        # Técnico: a prova global da disciplina (sem ela, a disciplina não fica completa).
        last = self.year.trimester_ids.sorted('number')[-1]
        for subject, pg_score in zip(self.subjects, score_by_subject, strict=True):
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
                assessment.grade_ids.score = pg_score

    def test_graduation(self):
        self._grades([14, 17])
        self.edu_class.action_compute_year_results()
        result = self.enrollment.year_result_id
        self.assertEqual(result.status, 'graduated')
        project = self.env['edu.final.project'].create(
            {
                'name': 'Cuidados de enfermagem ao recém-nascido',
                'student_id': self.student.id,
                'enrollment_id': self.enrollment.id,
                'defense_date': date(2027, 7, 10),
                'grade': 18,
            }  # fmt: skip
        )
        action = result.action_register_graduation()
        graduation = self.env['edu.graduation'].browse(action['res_id'])
        with self.assertRaises(UserError):
            graduation.action_issue()  # o curso exige a PAP aprovada
        project.action_submit()
        project.action_evaluate()
        graduation.final_project_id = project
        graduation.action_issue()
        # PC = (14 + 17) / 2 = 15,5 → 16; final = (2 × 16 + 18) / 3 = 16,7 → 17.
        self.assertEqual((graduation.plan_average, graduation.final_grade), (16, 17))
        self.assertTrue(graduation.diploma_number.startswith(f'{date.today().year}/'))
        self.assertEqual(graduation.state, 'issued')
        self.assertEqual(len(graduation.final_result_ids), 2)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env['edu.student'].create({'name': 'Outro', 'process_number': '1520'})

    def test_graduation_internship_subject(self):
        """O estágio é uma disciplina do curso: entra no PC com (2 × PC + PAP) / 3 e só como EC com a fórmula do INP."""
        line = self.edu_class.subject_line_ids.filtered(lambda line: line.subject_id == self.subjects[1])
        line.component = 'internship'
        self._grades([14, 17])
        self.edu_class.action_compute_year_results()
        result = self.enrollment.year_result_id
        project = self.env['edu.final.project'].create(
            {
                'name': 'PAP',
                'student_id': self.student.id,
                'enrollment_id': self.enrollment.id,
                'defense_date': date(2027, 7, 10),
                'grade': 18,
            }
        )
        project.action_submit()
        project.action_evaluate()
        graduation = self.env['edu.graduation'].browse(result.action_register_graduation()['res_id'])
        graduation.final_project_id = project
        graduation.action_compute()
        self.assertEqual((graduation.plan_average, graduation.final_grade), (16, 17))
        # (4 × PC + EC + PAP) / 6 com PC = 14 e EC = 17 (a nota da disciplina de estágio): 91 / 6 = 15,2 → 15.
        result._policy().course_formula = 'internship'
        graduation.action_compute()
        self.assertEqual((graduation.plan_average, graduation.final_grade), (14, 15))

    def test_not_graduated(self):
        self._grades([8, 9])
        self.edu_class.action_compute_year_results()
        with self.assertRaises(ValidationError):
            self.env['edu.graduation'].create(
                {'student_id': self.student.id, 'year_result_id': self.enrollment.year_result_id.id}
            )

    def test_training_pages(self):
        """Estágios e PAP como no secPed: o estágio a vários alunos de uma vez pela turma finalista, um por aluno e ano
        (o reprovado pode repetir), só nos cursos que o prevêem; reabrir é da direcção; o tutor só regista as horas, o
        parecer e os relatórios."""
        Page = self.env['edu.training.page']
        other = self.env['edu.student'].create({'name': 'Bruno Lemos'})
        other_enrollment = self.env['edu.enrollment'].create(
            {'student_id': other.id, 'class_id': self.edu_class.id, 'subject_ids': [Command.set(self.subjects.ids)]}
        )
        other_enrollment.action_confirm()
        # O curso não prevê estágio: não aparece no «Novo» e o servidor recusa.
        self.assertFalse(Page.new_options('internship')['classes'])
        with self.assertRaises(UserError):
            Page.create_records('internship', {'enrollment_ids': [self.enrollment.id], 'entity': 'Hospital'})
        self.course.requires_internship = True
        self.assertEqual([c['id'] for c in Page.new_options('internship')['classes']], [self.edu_class.id])

        ids = Page.create_records(
            'internship',
            {
                'enrollment_ids': [self.enrollment.id, other_enrollment.id],
                'entity': 'Hospital Geral',
                'supervisor': 'Dr. Tomás',
            },
        )
        internships = self.env['edu.internship'].browse(ids)
        self.assertEqual(len(internships), 2)
        self.assertEqual(internships.academic_year_id, self.year)
        self.assertEqual(internships[0].display_name, f'Estágio de {internships[0].student_id.name} (Hospital Geral)')
        self.assertTrue(all(s['taken'] for s in Page.class_students('internship', self.edu_class.id)))
        with self.assertRaises(ValidationError):
            Page.create_records('internship', {'enrollment_ids': [self.enrollment.id], 'entity': 'Outra'})

        mine = internships.filtered(lambda i: i.student_id == self.student)
        Page.run_action('internship', mine.id, 'start')
        with self.assertRaises(UserError):
            Page.run_action('internship', mine.id, 'evaluate', '')  # sem nota não se fecha
        detail = Page.run_action('internship', mine.id, 'evaluate', '8')
        self.assertEqual((detail['state'], detail['grade']), ('failed', 8))
        # Reprovado: pode ter um novo estágio no mesmo ano.
        retry = self.env['edu.internship'].browse(
            Page.create_records('internship', {'enrollment_ids': [self.enrollment.id], 'entity': 'Centro de Saúde'})
        )
        self.assertEqual(retry.state, 'planned')

        clerk = new_test_user(self.env, 'clerk_tr', groups='edu_core.group_edu_user')
        with self.assertRaises(UserError):
            Page.with_user(clerk).run_action('internship', mine.id, 'reopen')
        with self.assertRaises(UserError):
            Page.with_user(clerk).remove('internship', retry.id)

        # O tutor vê só os seus estágios e grava só as horas e o parecer.
        tutor_user = new_test_user(self.env, 'tutor_tr', groups='edu_core.group_edu_teacher')
        tutor = self.env['hr.employee'].create({'name': 'Prof. Ana', 'user_id': tutor_user.id, 'edu_is_teacher': True})
        retry.tutor_id = tutor
        listing = Page.with_user(tutor_user).listing('internship')
        self.assertEqual([r['id'] for r in listing['rows']], retry.ids)
        self.assertFalse(listing['is_staff'])
        Page.with_user(tutor_user).save('internship', retry.id, {'hours': 120, 'appraisal': 'Assíduo', 'entity': 'X'})
        self.assertEqual((retry.hours, retry.appraisal, retry.entity), (120, 'Assíduo', 'Centro de Saúde'))
        with self.assertRaises(UserError):
            Page.with_user(tutor_user).run_action('internship', retry.id, 'evaluate', '15')
        detail = Page.with_user(tutor_user).add_report(retry.id, 'Relatório intercalar', False, None)
        self.assertEqual([r['name'] for r in detail['reports']], ['Relatório intercalar'])

        # As regras valem no modelo, não só na página: o tutor não fecha nem dá nota por chamada directa; a
        # secretaria não muda o estado à mão, não anula um estágio fechado nem o remove.
        with self.assertRaises(UserError):
            retry.with_user(tutor_user).write({'state': 'passed', 'grade': 20})
        with self.assertRaises(UserError):
            retry.with_user(tutor_user).action_evaluate(grade=20)
        with self.assertRaises(UserError):
            retry.with_user(clerk).write({'state': 'passed'})
        with self.assertRaises(UserError):
            mine.with_user(clerk).action_cancel()  # já está fechado (não aprovado)
        with self.assertRaises(UserError):
            mine.with_user(clerk).write({'grade': 15})
        with self.assertRaises(UserError):
            retry.with_user(clerk).unlink()

        # PAP: um aluno, tema obrigatório; o resultado exige a data da defesa.
        with self.assertRaises(UserError):
            Page.create_records(
                'project', {'enrollment_ids': [self.enrollment.id, other_enrollment.id], 'name': 'Tema'}
            )
        project = self.env['edu.final.project'].browse(
            Page.create_records(
                'project', {'enrollment_ids': [self.enrollment.id], 'name': 'Cuidados ao recém-nascido'}
            )
        )
        # A secretaria grava o júri (fichas de funcionários que não lê); só com professores.
        Page.with_user(clerk).save('project', project.id, {'jury_ids': [tutor.id]})
        self.assertEqual(project.jury_ids, tutor)
        stranger = self.env['hr.employee'].create({'name': 'Contabilista'})
        with self.assertRaises(UserError):
            Page.with_user(clerk).save('project', project.id, {'jury_ids': [stranger.id]})
        with self.assertRaises(UserError):
            Page.save('project', project.id, {'advisor_id': stranger.id})
        Page.run_action('project', project.id, 'submit', '2027-06-01')
        self.assertEqual((project.state, project.submitted_date), ('submitted', date(2027, 6, 1)))
        with self.assertRaises(UserError):
            Page.run_action('project', project.id, 'evaluate', '16')
        Page.save('project', project.id, {'defense_date': '2027-07-10'})
        self.assertEqual(Page.run_action('project', project.id, 'evaluate', '16')['state'], 'passed')
        with self.assertRaises(ValidationError):
            Page.create_records('project', {'enrollment_ids': [self.enrollment.id], 'name': 'Outro tema'})
