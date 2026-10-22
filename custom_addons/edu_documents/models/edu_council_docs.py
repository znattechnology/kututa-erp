from odoo import models
from odoo.exceptions import UserError

SUMMARY = [
    ('promoted', 'Transita'),
    ('conditional', 'Transita c/ atraso'),
    ('exam', 'Exame especial'),
    ('retained', 'Não transita'),
    ('absence', 'Reprovados por falta'),
    ('graduated', 'Concluído'),
    ('pending', 'Pendentes'),
]


class EduCouncilSession(models.Model):
    """A Acta do Conselho de Notas e a Lista de Presença, como no secPed-Express: só depois de realizado e só para o
    director de turma (e a direcção)."""

    _inherit = 'edu.council.session'

    def _check_documents(self):
        self.ensure_one()
        if self.state != 'realized':
            raise UserError(self.env._('A acta e a lista de presença só existem depois de o conselho ser encerrado.'))
        if not self._is_director():
            raise UserError(self.env._('Apenas o director de turma tem acesso a este documento.'))

    def action_print_acta(self):
        self._check_documents()
        return self.env.ref('edu_documents.action_report_council_acta').preview_action(self)

    def action_print_attendance(self):
        self._check_documents()
        return self.env.ref('edu_documents.action_report_council_attendance').preview_action(self)

    def _teachers_by_subject(self):
        """Disciplina → professor (o colocado na turma), pela ordem da pauta."""
        self.ensure_one()
        rows = []
        assignments = self.class_id.sudo().assignment_ids
        for line in self.class_id.subject_line_ids.filtered('weekly_hours').sorted(lambda li: li.subject_id.name or ''):
            teacher = assignments.filtered(lambda a, s=line.subject_id: a.subject_id == s)[:1].teacher_id
            rows.append({'subject': line.subject_id, 'teacher': teacher.name or ''})
        return rows

    def _acta_data(self):
        self.ensure_one()
        session = self.sudo()
        edu_class = session.class_id
        enrollments = edu_class.enrollment_ids.filtered(
            lambda e: e.state in ('active', 'irregular', 'completed', 'retained')
        )
        results = self.env['edu.year.result'].sudo().search([('enrollment_id', 'in', enrollments.ids)])
        counts = dict.fromkeys(dict(SUMMARY), 0)
        for result in results:
            if result.absence_excluded:
                counts['absence'] += 1
            elif result.status in counts:
                counts[result.status] += 1
        counts['pending'] += len(enrollments) - len(results)
        subject_results = self.env['edu.subject.result'].sudo().search([('enrollment_id', 'in', enrollments.ids)])
        subjects = []
        for row in session._teachers_by_subject():
            mine = subject_results.filtered(lambda r, s=row['subject']: r.subject_id == s and r.complete)
            approved = len(mine.filtered('passed'))
            subjects.append(
                {
                    'name': row['subject'].name,
                    'teacher': row['teacher'],
                    'students': len(mine),
                    'approved': approved,
                    'percent': round(100 * approved / len(mine)) if mine else 0,
                }
            )
        votes = [
            {
                'student': vote.student_id.name,
                'subject': vote.subject_id.name,
                'grade': f'{round(vote.base)} → {round(vote.base) + 2}',
                'favor': vote.favor,
                'against': vote.against,
                'result': 'Aprovado (+2)' if vote.state == 'applied' else 'Não aprovado',
            }
            for vote in session.vote_ids.filtered(lambda v: v.state in ('applied', 'rejected')).sorted('id')
        ]
        return {
            'total': len(enrollments),
            'summary': [(label, counts[key]) for key, label in SUMMARY],
            'subjects': subjects,
            'votes': votes,
        }
