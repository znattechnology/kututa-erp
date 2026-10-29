from odoo import models
from odoo.exceptions import UserError


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    def _edu_uc_transcript(self):
        """As UCs do curso aprovadas até ao ano desta matrícula (a aprovação mais recente de cada uma)."""
        self.ensure_one()
        registrations = (
            self.env['edu.uc.registration']
            .sudo()
            .search(
                [
                    ('student_id', '=', self.student_id.id),
                    ('course_id', '=', self.course_id.id),
                    ('state', '=', 'passed'),
                    ('academic_year_id.date_start', '<=', self.academic_year_id.date_start),
                ]
            )
        )
        latest = {}
        for registration in registrations.sorted(lambda r: r.academic_year_id.date_start):
            latest[registration.subject_id] = registration
        return registrations.browse([r.id for r in latest.values()]).sorted(
            lambda r: (r.course_year, r.semester or '', r.curriculum_line_id.sequence, r.subject_id.name)
        )


class EduDocument(models.Model):
    _inherit = 'edu.document'

    def _check_requirements(self):
        """No superior, a declaração com notas é das UCs aprovadas até ao ano da matrícula (também a meio do curso)."""
        self.ensure_one()
        if self.document_type == 'grades' and self.enrollment_id.level_subsystem == 'higher':
            if not self.enrollment_id._edu_uc_transcript():
                raise UserError(self.env._('O estudante ainda não tem UCs aprovadas neste curso.'))
            return None
        return super()._check_requirements()
