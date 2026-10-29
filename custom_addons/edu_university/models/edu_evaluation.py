from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .edu_uc_registration import ASSESSMENT_TYPES


class EduAssessment(models.Model):
    _inherit = 'edu.assessment'

    assessment_type = fields.Selection(
        selection_add=[('frequency', 'Prova de frequência'), ('coursework', 'Trabalho')],
        ondelete={'frequency': 'set default', 'coursework': 'set default'},
    )

    @api.constrains('class_id', 'subject_id', 'trimester_id', 'assessment_type', 'max_score')
    def _check_assessment(self):
        """No superior há tantas provas de frequência e trabalhos quantos o docente marcar; os tipos do geral e do
        técnico (prova trimestral, prova global, exame nacional) não se usam, e os do superior só aí."""
        higher = self.filtered(lambda a: a.class_id.level_id.subsystem == 'higher')
        for assessment in higher:
            if assessment.assessment_type not in ASSESSMENT_TYPES:
                raise ValidationError(
                    self.env._('No ensino superior a avaliação é por provas de frequência e trabalhos.')
                )
            if assessment.trimester_id.academic_year_id != assessment.academic_year_id:
                raise ValidationError(self.env._('O semestre não é do ano académico da turma.'))
            if assessment.subject_id not in assessment.class_id.subject_line_ids.subject_id:
                raise ValidationError(self.env._('%s não faz parte do plano da turma.', assessment.subject_id.name))
            if not 0 < assessment.max_score <= 20:
                raise ValidationError(self.env._('A cotação vai até 20 valores.'))
        for assessment in self - higher:
            if assessment.assessment_type in ('frequency', 'coursework'):
                raise ValidationError(self.env._('As provas de frequência e os trabalhos são do ensino superior.'))
        return super(EduAssessment, self - higher)._check_assessment()


class EduTermResult(models.Model):
    _inherit = 'edu.term.result'

    @api.model
    def _recompute_keys(self, keys):
        """No superior não há médias trimestrais: as notas alimentam a inscrição na UC."""
        enrollments = self.env['edu.enrollment'].sudo().browse({key[0] for key in keys})
        higher = set(enrollments.filtered(lambda e: e.level_subsystem == 'higher').ids)
        if higher:
            pairs = {(enrollment_id, subject_id) for enrollment_id, subject_id, _t in keys if enrollment_id in higher}
            self.env['edu.uc.registration']._edu_uc_refresh_keys(pairs)
        return super()._recompute_keys({key for key in keys if key[0] not in higher})
