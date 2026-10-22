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
        # O resultado da matrícula imediatamente anterior (não o último que exista: uma retenção antiga, já repetida,
        # não volta a contar).
        before = self.student_id.enrollment_ids.filtered(
            lambda e: (
                e.academic_year_id.date_start < self.academic_year_id.date_start
                and e.state not in ('draft', 'dropped', 'transferred')
            )
        ).sorted(lambda e: e.academic_year_id.date_start, reverse=True)[:1]
        previous = before.sudo().year_result_id
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

    def _edu_is_terminal(self):
        """A última classe do plano do curso."""
        self.ensure_one()
        curriculum = self.class_id.curriculum_id
        return bool(curriculum) and self.class_number >= curriculum.class_to

    def _edu_close_year(self):
        """Fecha as matrículas pelo resultado do ano: transita, transita com disciplinas em atraso ou concluiu →
        «Concluída»; retido → «Retido». Quem ainda espera exames ou decisão fica em aberto. Devolve as que ficaram."""
        open_enrollments = self.browse()
        self.invalidate_recordset(['year_result_id'])  # o resultado pode ter sido decidido entretanto
        for enrollment in self.filtered(lambda e: e.state in ('active', 'irregular')):
            status = enrollment.sudo().year_result_id.status
            if status in ('promoted', 'conditional', 'graduated'):
                enrollment.state = 'completed'
            elif status == 'retained':
                enrollment.state = 'retained'
            else:
                open_enrollments |= enrollment
        return open_enrollments


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
