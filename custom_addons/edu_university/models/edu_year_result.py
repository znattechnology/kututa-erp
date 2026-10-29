from odoo import models
from odoo.addons.edu_core.tools.trust import trusted
from odoo.exceptions import UserError

from ..tools.grading_higher import round_grade


class EduYearResult(models.Model):
    """No superior o resultado do ano sai das UCs: passa com, no máximo, as UCs por aprovar que o regulamento
    permite (do ano e dos anteriores); conclui no último ano com todas aprovadas, o trabalho final incluído."""

    _inherit = 'edu.year.result'

    def _edu_is_higher(self):
        self.ensure_one()
        return self.enrollment_id.level_subsystem == 'higher'

    def _decide(self, excluded_absence=False):
        higher = self.filtered(lambda r: r._edu_is_higher())
        for result in higher.filtered(lambda r: not r.manual):
            result._edu_uc_decide()
        return super(EduYearResult, self - higher)._decide(excluded_absence=excluded_absence)

    def _edu_uc_decide(self):
        self.ensure_one()
        enrollment = self.enrollment_id
        regulation = self.env['edu.university.regulation']._get(enrollment.company_id, enrollment.course_id.level_id)
        registrations = enrollment.uc_registration_ids
        undecided = registrations.filtered(lambda r: r.state == 'enrolled')
        pending = enrollment._edu_uc_missing_subjects()
        passed = registrations.filtered(lambda r: r.state == 'passed')
        credits = sum(passed.mapped('credits'))
        average = (
            round_grade(sum(r.final_grade * r.credits for r in passed) / credits, regulation.rounding)
            if credits
            else 0.0
        )
        names = ', '.join(pending.mapped('name'))
        if undecided:
            status = 'pending'
            reason = self.env._('UCs ainda por decidir: %s.', ', '.join(undecided.subject_id.mapped('name')))
        elif enrollment._edu_is_terminal() and not pending:
            status, reason = 'graduated', self.env._('Todas as UCs do curso aprovadas.')
        elif enrollment._edu_is_terminal():
            status, reason = 'retained', self.env._('Para concluir o curso falta aprovar: %s.', names)
        elif not pending:
            status, reason = 'promoted', False
        elif len(pending) <= regulation.max_backlog:
            status = 'conditional'
            reason = self.env._('Passa com %(count)s UC(s) em atraso: %(names)s.', count=len(pending), names=names)
        else:
            status = 'retained'
            reason = self.env._(
                '%(count)s UCs por aprovar (o regulamento permite %(max)s): %(names)s.',
                count=len(pending),
                max=regulation.max_backlog,
                names=names,
            )
        with trusted(self.env):
            self.sudo().write(
                {
                    'status': status,
                    'reason': reason,
                    'average': average,
                    'negative_count': len(pending),
                    'negative_subject_ids': [(6, 0, pending.ids)],
                    'requires_review': False,
                }
            )

    def _edu_terminal(self):
        self.ensure_one()
        if self._edu_is_higher():
            return self.enrollment_id._edu_is_terminal()
        return self._policy()._rules(self.class_id).terminal

    def action_manual_promote(self):
        if self[:1] and self[:1]._edu_is_higher():
            return self._set_manual('graduated' if self[:1]._edu_terminal() else 'promoted')
        return super().action_manual_promote()

    def manual_decide(self, status, reason):
        self.ensure_one()
        if not self._edu_is_higher():
            return super().manual_decide(status, reason)
        if not (reason or '').strip():
            raise UserError(self.env._('Escreva o fundamento da decisão.'))
        terminal = self._edu_terminal()
        if status == 'promoted' and terminal:
            status = 'graduated'
        allowed = ('graduated',) if terminal else ('promoted', 'conditional')
        if status not in (*allowed, 'retained'):
            raise UserError(self.env._('Esta decisão não se aplica a este ano do curso.'))
        return self._set_manual(status, reason.strip())
