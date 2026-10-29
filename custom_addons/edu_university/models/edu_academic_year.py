from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Calendário académico geral do subsistema de ensino superior: dois semestres por ano académico.
SEMESTERS = 2


class EduAcademicYear(models.Model):
    _inherit = 'edu.academic.year'

    edu_is_higher = fields.Boolean(related='company_id.edu_is_higher')

    def action_generate_trimesters(self):
        higher = self.filtered('edu_is_higher')
        for year in higher:
            if year.trimester_ids:
                raise UserError(self.env._('O ano académico %s já tem semestres.', year.name))
            middle = year.date_start + timedelta(days=((year.date_end - year.date_start).days + 1) // 2 - 1)
            self.env['edu.trimester'].create(
                [
                    {'academic_year_id': year.id, 'number': 1, 'date_start': year.date_start, 'date_end': middle},
                    {
                        'academic_year_id': year.id,
                        'number': 2,
                        'date_start': middle + timedelta(days=1),
                        'date_end': year.date_end,
                    },
                ]
            )
        return super(EduAcademicYear, self - higher).action_generate_trimesters()


class EduTrimester(models.Model):
    """No ensino superior, o período lectivo do ano é o semestre."""

    _inherit = 'edu.trimester'

    edu_is_higher = fields.Boolean(related='academic_year_id.company_id.edu_is_higher')

    @api.depends('number')
    def _compute_name(self):
        higher = self.filtered('edu_is_higher')
        for semester in higher:
            if semester.number and not semester.name:
                semester.name = self.env._('%sº Semestre', semester.number)
        return super(EduTrimester, self - higher)._compute_name()

    @api.constrains('number', 'date_start', 'date_end')
    def _check_dates(self):
        higher = self.filtered('edu_is_higher')
        for semester in higher:
            year = semester.academic_year_id
            if not 1 <= semester.number <= SEMESTERS:
                raise ValidationError(self.env._('O ano académico tem dois semestres (1 e 2).'))
            if semester.date_end < semester.date_start:
                raise ValidationError(self.env._('O semestre termina antes de começar.'))
            if semester.date_start < year.date_start or semester.date_end > year.date_end:
                raise ValidationError(
                    self.env._(
                        'O %(semester)s sai das datas do ano académico %(year)s.',
                        semester=semester.name,
                        year=year.name,
                    )
                )
            overlap = self.search_count(
                [
                    ('academic_year_id', '=', year.id),
                    ('id', '!=', semester.id),
                    ('date_start', '<=', semester.date_end),
                    ('date_end', '>=', semester.date_start),
                ]
            )
            if overlap:
                raise ValidationError(self.env._('Os semestres de %s sobrepõem-se.', year.name))
        return super(EduTrimester, self - higher)._check_dates()
