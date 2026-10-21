from odoo import fields, models

from .absence_rules import FAILED


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    absence_alert_ids = fields.One2many('edu.absence.alert', 'enrollment_id', string='Avisos de faltas')

    def _edu_absence_alert(self, subject, trimester, summary):
        """Uma actividade para o director de turma por disciplina, trimestre e situação (em risco, reprovado)."""
        self.ensure_one()
        Alert = self.env['edu.absence.alert']
        key = [
            ('enrollment_id', '=', self.id),
            ('subject_id', '=', subject.id),
            ('trimester_id', '=', trimester.id),
            ('status', '=', summary.status),
        ]
        if Alert.search_count(key):
            return
        Alert.create(
            {'enrollment_id': self.id, 'subject_id': subject.id, 'trimester_id': trimester.id, 'status': summary.status}
        )
        failed = summary.status == FAILED
        message = self.env._(
            '%(student)s: %(count)s faltas injustificadas a %(subject)s (limite %(limit)s). %(situation)s',
            student=self.student_id.name,
            count=summary.counted,
            subject=subject.name,
            limit=summary.limit,
            situation=self.env._('Reprovado(a) por faltas.')
            if failed
            else self.env._('Em risco de reprovar por faltas.'),
        )
        self.message_post(body=message)
        director = self.class_id.director_id.user_id
        if director:
            self.activity_schedule(
                'edu_attendance.mail_activity_type_absence', user_id=director.id, note=message, summary=message[:80]
            )


class EduAbsenceAlert(models.Model):
    _name = 'edu.absence.alert'
    _description = 'Aviso de faltas'

    enrollment_id = fields.Many2one('edu.enrollment', required=True, ondelete='cascade', index=True)
    subject_id = fields.Many2one('edu.subject', required=True, ondelete='cascade')
    trimester_id = fields.Many2one('edu.trimester', ondelete='cascade')
    status = fields.Selection([('at_risk', 'Em risco'), ('failed', 'Reprovado por faltas')], required=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True)
