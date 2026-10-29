from odoo import api, models


class EduClass(models.Model):
    """No superior a turma é do ano do curso: «2.º ano A · EI», não «2ª A»."""

    _inherit = 'edu.class'

    def _edu_is_higher(self):
        return self.course_id.level_id.subsystem == 'higher'

    @api.depends(
        'name',
        'class_number',
        'course_id.code',
        'course_id.name',
        'academic_year_id.name',
        'course_id.level_id.subsystem',
    )
    def _compute_complete_name(self):
        higher = self.filtered(lambda c: c._edu_is_higher())
        for edu_class in higher:
            parts = [
                f'{edu_class.class_number}.º ano {edu_class.name or ""}'.strip(),
                edu_class.course_id.code or edu_class.course_id.name,
            ]
            if edu_class.academic_year_id:
                parts.append(edu_class.academic_year_id.name)
            edu_class.complete_name = ' · '.join(p for p in parts if p)
        return super(EduClass, self - higher)._compute_complete_name()

    def _editor_label(self):
        if self._edu_is_higher():
            return ' · '.join(p for p in [f'{self.class_number}.º ano {self.name}', self.course_id.code] if p)
        return super()._editor_label()
