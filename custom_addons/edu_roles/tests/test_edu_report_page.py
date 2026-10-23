from datetime import date

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduReportPage(TransactionCase):
    """Relatórios como no secPed: notas do trimestre contra a nota mínima, resultado final com os que faltam e
    classificações por disciplina só com as completas (uma por fechar não é um zero)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['edu.academic.year'].create(
            {'name': '2030/2031', 'date_start': date(2030, 9, 1), 'date_end': date(2031, 7, 31), 'is_current': True}
        )
        cls.year.action_generate_trimesters()
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
            {'name': 'A', 'course_id': course.id, 'curriculum_year_id': tenth.id, 'academic_year_id': cls.year.id}
        )
        cls.subject = cls.edu_class.subject_line_ids.subject_id[:1]
        cls.enrollments = cls.env['edu.enrollment']
        for name in ('Ana', 'Bruno', 'Carla'):
            student = cls.env['edu.student'].create({'name': name})
            enrollment = cls.env['edu.enrollment'].create(
                {
                    'student_id': student.id,
                    'class_id': cls.edu_class.id,
                    'subject_ids': [Command.set(cls.subject.ids)],
                    'late_reason': 'Teste',
                }
            )
            enrollment.action_confirm()
            cls.enrollments |= enrollment

    def test_report(self):
        Page = self.env['edu.report.page']
        first = self.year.trimester_ids.sorted('number')[0]
        for enrollment, mt in zip(self.enrollments, (14, 8, 12), strict=True):
            self.env['edu.term.result'].create(
                {
                    'enrollment_id': enrollment.id,
                    'subject_id': self.subject.id,
                    'trimester_id': first.id,
                    'mt': mt,
                    'has_mt': True,
                }
            )
        # Duas classificações fechadas (16 aprovada, 8 não) e uma por fechar, a 0.
        for enrollment, final, complete in zip(self.enrollments, (16, 8, 0), (True, True, False), strict=True):
            self.env['edu.subject.result'].create(
                {
                    'enrollment_id': enrollment.id,
                    'subject_id': self.subject.id,
                    'final': final,
                    'complete': complete,
                    'passed': complete and final >= 10,
                }
            )
        for enrollment, status, average in zip(self.enrollments[:2], ('promoted', 'retained'), (15, 8), strict=True):
            self.env['edu.year.result'].create({'enrollment_id': enrollment.id, 'status': status, 'average': average})

        data = Page.report(self.year.id, 'class', first.id)
        self.assertEqual((data['enrollments']['total'], data['enrollments']['classes']), (3, 1))
        grades = data['grades']
        self.assertEqual((grades['grades'], grades['pct'], grades['with_negative']), (3, 67, 1))
        self.assertEqual(grades['rows'][0]['average'], 11.3)
        # Os gráficos: a distribuição das notas (14, 8 e 12) e a evolução por trimestre e por ano.
        self.assertEqual([grades['histogram'][v] for v in (8, 12, 14)], [1, 1, 1])
        self.assertEqual(sum(grades['histogram']), 3)
        self.assertEqual([(t['grades'], t['pct']) for t in grades['by_trimester']], [(3, 67), (0, None), (0, None)])
        trend = {t['name']: t['pct'] for t in data['years_trend']}
        self.assertEqual(trend['2030/2031'], 50)
        final = data['final']
        self.assertEqual((final['evaluated'], final['approved'], final['pct'], final['missing']), (2, 1, 50, 1))
        subjects = data['subjects']
        # Média só das completas: (16 + 8) / 2 = 12, e não 8 com o zero da que está por fechar.
        self.assertEqual((subjects['count'], subjects['incomplete']), (2, 1))
        self.assertEqual((subjects['rows'][0]['average'], subjects['rows'][0]['pct']), (12, 50))
        self.assertFalse(data['attendance']['calls'])
        # Por subsistema não há média (escalas diferentes).
        self.assertIsNone(Page.report(self.year.id, 'subsystem')['grades']['rows'][0]['average'])

        xlsx = Page.export_xlsx(self.year.id, 'course')
        self.assertTrue(xlsx['datas'] and xlsx['name'].endswith('.xlsx'))
        action = Page.print_pdf(self.year.id, 'course')
        html = (
            self.env['ir.actions.report']
            ._render_qweb_html('edu_roles.report_school_figures', None, data=action['data'])[0]
            .decode()
        )
        self.assertIn('RELATÓRIOS DA ESCOLA', html)
        self.assertIn('Classificações por disciplina', html)
