from odoo import api, fields, models
from odoo.tools import SQL

from .absence_rules import GENERAL, OK, absence_limit, absence_status


class EduAbsenceSummary(models.Model):
    """Faltas por matrícula, disciplina e trimestre (só aulas dadas). No técnico, o limite é anual."""

    _name = 'edu.absence.summary'
    _description = 'Mapa de faltas'
    _auto = False
    _order = 'class_id, order_number, subject_id, trimester_id'
    _depends = {
        'edu.lesson.attendance': [
            'enrollment_id', 'student_id', 'order_number', 'class_id', 'company_id', 'subject_id', 'trimester_id',
            'state', 'lesson_state',
        ],
        'edu.class': ['academic_year_id'],
    }  # fmt: skip

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', readonly=True)
    student_id = fields.Many2one('edu.student', string='Aluno', readonly=True)
    order_number = fields.Integer(string='N.º', readonly=True, aggregator=False)
    class_id = fields.Many2one('edu.class', string='Turma', readonly=True)
    academic_year_id = fields.Many2one('edu.academic.year', string='Ano lectivo', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', readonly=True)
    trimester_id = fields.Many2one('edu.trimester', string='Trimestre', readonly=True)
    lessons = fields.Integer(string='Aulas', readonly=True)
    present = fields.Integer(string='Presenças', readonly=True)
    late = fields.Integer(string='Atrasos', readonly=True)
    absent = fields.Integer(string='Injustificadas', readonly=True)
    excused = fields.Integer(string='Justificadas', readonly=True)
    year_absent = fields.Integer(string='Injustificadas no ano', readonly=True)
    weekly_hours = fields.Integer(string='Tempos semanais', compute='_compute_status')
    limit = fields.Integer(string='Limite', compute='_compute_status')
    counted = fields.Integer(string='Contam', compute='_compute_status')
    status = fields.Selection(
        [('ok', 'Regular'), ('at_risk', 'Em risco'), ('failed', 'Reprovado por faltas')],
        string='Situação',
        compute='_compute_status',
        search='_search_status',
    )

    @property
    def _table_sql(self):
        return SQL("""(
            SELECT
                MIN(a.id) AS id,
                a.enrollment_id,
                a.student_id,
                a.order_number,
                a.class_id,
                c.academic_year_id,
                a.company_id,
                a.subject_id,
                a.trimester_id,
                COUNT(*) AS lessons,
                COUNT(*) FILTER (WHERE a.state = 'present') AS present,
                COUNT(*) FILTER (WHERE a.state = 'late') AS late,
                COUNT(*) FILTER (WHERE a.state = 'absent') AS absent,
                COUNT(*) FILTER (WHERE a.state = 'excused') AS excused,
                SUM(COUNT(*) FILTER (WHERE a.state = 'absent'))
                    OVER (PARTITION BY a.enrollment_id, a.subject_id) AS year_absent
            FROM edu_lesson_attendance a
            JOIN edu_class c ON c.id = a.class_id
            WHERE a.lesson_state = 'done'
            GROUP BY a.enrollment_id, a.student_id, a.order_number, a.class_id, c.academic_year_id,
                     a.company_id, a.subject_id, a.trimester_id
        )""")

    @api.depends('enrollment_id', 'subject_id', 'absent', 'year_absent')
    def _compute_status(self):
        for summary in self:
            edu_class = summary.class_id
            regime = edu_class._edu_regime()
            hours = edu_class._edu_weekly_hours(summary.subject_id)
            limit = absence_limit(hours, regime)
            counted = summary.absent if regime == GENERAL else summary.year_absent
            summary.weekly_hours = hours
            summary.limit = limit or 0
            summary.counted = counted
            summary.status = absence_status(counted, limit)

    def _search_status(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        values = {value} if isinstance(value, str) else set(value or [])
        # Em risco ou reprovado exige pelo menos 2 faltas injustificadas (o limite mínimo é 3).
        candidates = self.search([('year_absent', '>=', 2)])
        flagged = candidates.filtered(lambda s: s.status != OK)
        if values <= {'at_risk', 'failed'}:
            ids = flagged.filtered(lambda s: s.status in values).ids
            return [('id', 'in' if operator in ('=', 'in') else 'not in', ids)]
        excluded = flagged.filtered(lambda s: s.status not in values).ids
        return [('id', 'not in' if operator in ('=', 'in') else 'in', excluded)]


def status_label(status):
    return {'ok': 'Regular', 'at_risk': 'Em risco', 'failed': 'Reprovado por faltas'}.get(status or OK)
