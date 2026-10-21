from odoo import fields, models
from odoo.exceptions import UserError


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    subject_result_ids = fields.One2many('edu.subject.result', 'enrollment_id', string='Pauta')
    year_result_id = fields.Many2one('edu.year.result', string='Resultado do ano', compute='_compute_year_result_id')

    def _compute_year_result_id(self):
        Result = self.env['edu.year.result'].sudo()
        for enrollment in self:
            enrollment.year_result_id = Result.search([('enrollment_id', '=', enrollment.id)], limit=1)

    def _edu_locked_subjects(self):
        """Disciplinas com notas lançadas não se retiram da matrícula."""
        locked = super()._edu_locked_subjects()
        grades = self.env['edu.grade'].sudo().search([('enrollment_id', '=', self.id), ('graded', '=', True)])
        return locked | grades.subject_id

    def _edu_check_enrollment_allowed(self):
        """Retenções e resultado do ano anterior (RAA, art. 25.º): retido não sobe de classe; com disciplinas em
        atraso, não entra na 9.ª nem na 12.ª e, nas outras, no máximo com 2; ao fim de 2 retenções no nível, decide a
        direcção."""
        result = super()._edu_check_enrollment_allowed()
        Result = self.env['edu.year.result'].sudo()
        previous = Result.search(
            [
                ('student_id', '=', self.student_id.id),
                ('academic_year_id.date_start', '<', self.academic_year_id.date_start),
            ],
            order='id desc',
        ).sorted(lambda r: r.academic_year_id.date_start, reverse=True)[:1]
        if previous:
            if previous.status == 'retained' and self.class_number > previous.class_id.class_number:
                raise UserError(
                    self.env._(
                        '%(student)s ficou retido(a) na %(number)sª classe: matricula-se na mesma classe.',
                        student=self.student_id.name,
                        number=previous.class_id.class_number,
                    )
                )
            pending = previous.requirement_ids.filtered(lambda r: r.state == 'pending' or not r.passed)
            if pending and self.class_number > previous.class_id.class_number:
                policy = previous._policy()
                terminal = policy._is_exam_class(self.class_number)
                if terminal or len(pending) > 2:
                    raise UserError(
                        self.env._(
                            '%(student)s tem %(count)s disciplina(s) por aprovar da classe anterior: %(subjects)s.',
                            student=self.student_id.name,
                            count=len(pending),
                            subjects=', '.join(pending.subject_id.mapped('name')),
                        )
                    )
            if previous.requires_review and not previous.manual:
                raise UserError(
                    self.env._('%s excede o número de retenções no nível: decide a direcção.', self.student_id.name)
                )
        return result


class EduClass(models.Model):
    _inherit = 'edu.class'

    def _edu_can_renumber(self):
        return super()._edu_can_renumber() and not self.env['edu.grade'].sudo().search_count(
            [('class_id', '=', self.id), ('graded', '=', True)], limit=1
        )

    def action_compute_year_results(self):
        results = self.env['edu.year.result']._compute_for_classes(self)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Resultados do ano'),
            'res_model': 'edu.year.result',
            'view_mode': 'list,form',
            'domain': [('id', 'in', results.ids)],
        }

    def action_open_council(self):
        self.ensure_one()
        session = self.env['edu.council.session'].search([('class_id', '=', self.id)], limit=1) or self.env[
            'edu.council.session'
        ].create({'class_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.council.session',
            'res_id': session.id,
            'view_mode': 'form',
        }

    def action_view_pauta(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Pauta da %s', self.display_name),
            'res_model': 'edu.subject.result',
            'view_mode': 'list,pivot',
            'domain': [('class_id', '=', self.id)],
        }
