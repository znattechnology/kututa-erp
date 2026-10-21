from odoo import api, fields, models

from ..models.report_helpers import Helpers


class EduPautaPrint(models.TransientModel):
    """Impressão da mini-pauta (disciplina e trimestre) e da pauta da turma (trimestral ou final)."""

    _name = 'edu.pauta.print'
    _description = 'Impressão de pautas'

    class_id = fields.Many2one('edu.class', string='Turma', required=True)
    company_id = fields.Many2one(related='class_id.company_id')
    academic_year_id = fields.Many2one(related='class_id.academic_year_id')
    kind = fields.Selection(
        [('mini', 'Mini-pauta (disciplina)'), ('final', 'Pauta da turma')],
        string='Documento',
        required=True,
        default='final',
    )
    subject_id = fields.Many2one('edu.subject', string='Disciplina')
    trimester_id = fields.Many2one(
        'edu.trimester', string='Trimestre', domain="[('academic_year_id', '=', academic_year_id)]"
    )
    regime = fields.Char(compute='_compute_regime')

    @api.depends('class_id')
    def _compute_regime(self):
        for wizard in self:
            policy = self.env['edu.evaluation.policy']._get(wizard.class_id.company_id, wizard.class_id.level_id)
            wizard.regime = policy.regime

    def _policy(self):
        return self.env['edu.evaluation.policy']._get(self.class_id.company_id, self.class_id.level_id)

    def _enrollments(self):
        return self.class_id.enrollment_ids.filtered(lambda e: e.state != 'draft').sorted('order_number')

    def _subjects(self):
        results = self.env['edu.subject.result'].search([('class_id', '=', self.class_id.id)])
        return Helpers.ordered(results).subject_id or self.class_id.subject_line_ids.subject_id

    def _results(self):
        return {
            (r.enrollment_id.id, r.subject_id.id): r
            for r in self.env['edu.subject.result'].search([('class_id', '=', self.class_id.id)])
        }

    def _terms(self):
        domain = [('class_id', '=', self.class_id.id), ('subject_id', '=', self.subject_id.id)]
        return {(t.enrollment_id.id, t.trimester_id.number): t for t in self.env['edu.term.result'].search(domain)}

    def _absences(self):
        domain = [('class_id', '=', self.class_id.id), ('subject_id', '=', self.subject_id.id)]
        if self.trimester_id:
            domain.append(('trimester_id', '=', self.trimester_id.id))
        rows = self.env['edu.absence.summary'].search(domain)
        totals = {}
        for row in rows:
            excused, absent = totals.get(row.enrollment_id.id, (0, 0))
            totals[row.enrollment_id.id] = (excused + row.excused, absent + row.absent)
        return totals

    def _year_results(self):
        return {
            r.enrollment_id.id: r for r in self.env['edu.year.result'].search([('class_id', '=', self.class_id.id)])
        }

    def action_print(self):
        self.ensure_one()
        report = (
            'edu_documents.action_report_mini_pauta' if self.kind == 'mini' else 'edu_documents.action_report_pauta'
        )
        return self.env.ref(report).report_action(self)
