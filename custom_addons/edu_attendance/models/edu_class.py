from odoo import api, fields, models

from .absence_rules import FAILED, GENERAL, PRIMARY, TECHNICAL


class EduClass(models.Model):
    _inherit = 'edu.class'

    lesson_ids = fields.One2many('edu.lesson', 'class_id', string='Aulas')
    lesson_count = fields.Integer(string='N.º de aulas', compute='_compute_lesson_count')

    @api.depends('lesson_ids')
    def _compute_lesson_count(self):
        for edu_class in self:
            edu_class.lesson_count = len(edu_class.lesson_ids)

    def _edu_regime(self):
        """Regime das faltas: o técnico-profissional tem regras próprias (Despacho 60/08); o limite por disciplina
        (DE 424/25, art. 25.º) é do ensino secundário, não do primário nem da iniciação."""
        self.ensure_one()
        level = self.level_id
        if level.subsystem == 'technical':
            return TECHNICAL
        if level.subsystem == 'general' and self.class_number <= 6:
            return PRIMARY
        return GENERAL

    def _edu_weekly_hours(self, subject):
        """Tempos semanais da disciplina no plano curricular da turma (a classe da turma, ou a mais
        próxima anterior, para as disciplinas em atraso)."""
        self.ensure_one()
        lines = self.curriculum_id.line_ids.filtered(
            lambda line: line.subject_id == subject and line.year_id.class_number <= self.class_number
        )
        return max(lines, key=lambda line: line.year_id.class_number).weekly_hours if lines else 0

    def _edu_absence_exclusions(self):
        """Matrículas reprovadas por faltas no ano (em qualquer disciplina e, no geral, em qualquer trimestre)."""
        self.ensure_one()
        self.env.flush_all()
        Summary = self.env['edu.absence.summary'].sudo()
        Summary.invalidate_model()
        # Pela matrícula (as faltas de uma disciplina feita noutra turma contam) e sem as disciplinas anuladas.
        summaries = Summary.search([('enrollment_id.class_id', '=', self.id)])
        return summaries.filtered(
            lambda s: s.status == FAILED and s.subject_id not in s.enrollment_id._dropped_subjects()
        ).enrollment_id

    def action_view_lessons(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Aulas da %s', self.display_name),
            'res_model': 'edu.lesson',
            'view_mode': 'list,form',
            'domain': [('class_id', '=', self.id)],
            'context': {'default_class_id': self.id},
        }

    def action_view_absences(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Faltas da %s', self.display_name),
            'res_model': 'edu.absence.summary',
            'view_mode': 'list,pivot',
            'domain': [('class_id', '=', self.id)],
        }
