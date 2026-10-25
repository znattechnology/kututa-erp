from odoo import api, fields, models

ENROLLED = ('active', 'irregular', 'completed', 'retained')


class EduAcademicYear(models.Model):
    """Os números do ano lectivo para os cartões da secretaria: a fase (por começar, em curso, terminado), o tempo
    decorrido, os alunos matriculados e os trimestres com o estado."""

    _inherit = 'edu.academic.year'

    edu_phase = fields.Selection(
        [('upcoming', 'Por começar'), ('running', 'A decorrer'), ('done', 'Terminado')],
        string='Fase',
        compute='_compute_edu_progress',
    )
    edu_progress = fields.Integer(string='Tempo decorrido (%)', compute='_compute_edu_progress')
    edu_days_left = fields.Integer(string='Dias até ao fim', compute='_compute_edu_progress')
    edu_span = fields.Char(string='Período', compute='_compute_edu_progress')
    edu_student_count = fields.Integer(string='Alunos matriculados', compute='_compute_edu_student_count')
    edu_trimesters = fields.Json(string='Trimestres (cartão)', compute='_compute_edu_trimesters')

    @api.depends('date_start', 'date_end')
    def _compute_edu_progress(self):
        today = fields.Date.context_today(self)
        for year in self:
            if not year.date_start or not year.date_end:
                year.edu_phase, year.edu_progress, year.edu_days_left, year.edu_span = 'upcoming', 0, 0, ''
                continue
            year.edu_span = f'{year.date_start.strftime("%d/%m/%Y")} a {year.date_end.strftime("%d/%m/%Y")}'
            total = max((year.date_end - year.date_start).days, 1)
            elapsed = min(max((today - year.date_start).days, 0), total)
            year.edu_progress = round(100 * elapsed / total)
            year.edu_days_left = max((year.date_end - today).days, 0)
            year.edu_phase = 'upcoming' if today < year.date_start else 'done' if today > year.date_end else 'running'

    def _compute_edu_student_count(self):
        groups = (
            self.env['edu.enrollment']
            .sudo()
            ._read_group(
                [('academic_year_id', 'in', self.ids), ('state', 'in', ENROLLED)], ['academic_year_id'], ['__count']
            )
        )
        counts = {year.id: count for year, count in groups}
        for year in self:
            year.edu_student_count = counts.get(year.id, 0)

    @api.depends(
        'trimester_ids.date_start', 'trimester_ids.date_end', 'trimester_ids.state', 'trimester_ids.is_current'
    )
    def _compute_edu_trimesters(self):
        for year in self:
            year.edu_trimesters = [
                {
                    'id': t.id,
                    'name': t.name or '',
                    'span': f'{t.date_start.strftime("%d/%m")} a {t.date_end.strftime("%d/%m")}',
                    'closed': t.state == 'closed',
                    'current': t.is_current,
                }
                for t in year.trimester_ids.sorted('number')
            ]
