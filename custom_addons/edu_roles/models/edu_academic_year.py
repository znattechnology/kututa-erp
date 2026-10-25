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


class EduTrimester(models.Model):
    """Os números do trimestre para os cartões da secretaria: o período, a fase, o tempo decorrido e as notas
    lançadas (as classificações do trimestre face às esperadas: cada aluno em cada disciplina)."""

    _inherit = 'edu.trimester'

    edu_span = fields.Char(string='Período', compute='_compute_edu_progress')
    edu_phase = fields.Selection(
        [('upcoming', 'Por começar'), ('running', 'A decorrer'), ('done', 'Terminado')],
        string='Fase',
        compute='_compute_edu_progress',
    )
    edu_progress = fields.Integer(string='Tempo decorrido (%)', compute='_compute_edu_progress')
    edu_days_left = fields.Integer(string='Dias até ao fim', compute='_compute_edu_progress')
    edu_grades = fields.Integer(string='Notas lançadas (%)', compute='_compute_edu_grades')
    edu_closed_info = fields.Char(string='Fecho', compute='_compute_edu_progress')

    @api.depends('date_start', 'date_end', 'state', 'closed_date', 'closed_by_id')
    def _compute_edu_progress(self):
        today = fields.Date.context_today(self)
        for trimester in self:
            start, end = trimester.date_start, trimester.date_end
            trimester.edu_closed_info = ''
            if trimester.state == 'closed' and trimester.closed_date:
                closed = fields.Datetime.context_timestamp(trimester, trimester.closed_date).strftime('%d/%m/%Y')
                who = trimester.closed_by_id.name
                trimester.edu_closed_info = f'Fechado a {closed} por {who}' if who else f'Fechado a {closed}'
            if not start or not end:
                trimester.edu_span, trimester.edu_phase = '', 'upcoming'
                trimester.edu_progress = trimester.edu_days_left = 0
                continue
            trimester.edu_span = f'{start.strftime("%d/%m/%Y")} a {end.strftime("%d/%m/%Y")}'
            total = max((end - start).days, 1)
            trimester.edu_progress = round(100 * min(max((today - start).days, 0), total) / total)
            trimester.edu_days_left = max((end - today).days, 0)
            trimester.edu_phase = 'upcoming' if today < start else 'done' if today > end else 'running'

    def _compute_edu_grades(self):
        Enrollment = self.env['edu.enrollment'].sudo()
        Result = self.env['edu.term.result'].sudo()
        for trimester in self:
            enrollments = Enrollment.search(
                [('academic_year_id', '=', trimester.academic_year_id.id), ('state', 'in', ENROLLED)]
            )
            expected = sum(len(e.subject_ids) for e in enrollments)
            launched = Result.search_count(
                [('enrollment_id', 'in', enrollments.ids), ('trimester_id', '=', trimester.id), ('has_mt', '=', True)]
            )
            trimester.edu_grades = round(100 * min(launched, expected) / expected) if expected else 0
