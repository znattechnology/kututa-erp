from odoo import fields, models
from odoo.addons.edu_core.tools.trust import trusted
from odoo.exceptions import UserError

# Épocas do superior → nota de exame da inscrição na UC.
UC_KINDS = {
    'uc_normal': 'exam_normal',
    'uc_appeal': 'exam_appeal',
    'uc_special': 'exam_special',
    'uc_improvement': 'exam_improvement',
}


class EduExamPeriod(models.Model):
    _inherit = 'edu.exam.period'

    kind = fields.Selection(
        selection_add=[
            ('uc_normal', 'Época normal (superior)'),
            ('uc_appeal', 'Época de recurso (superior)'),
            ('uc_special', 'Época especial (superior)'),
            ('uc_improvement', 'Melhoria de nota (superior)'),
        ],
        ondelete={kind: 'set default' for kind in UC_KINDS},
    )


class EduExamSession(models.Model):
    _inherit = 'edu.exam.session'

    def _edu_uc_candidates(self):
        """As inscrições convocadas, pela situação de cada uma e pelo regulamento académico."""
        self.ensure_one()
        domain = [
            ('subject_id', '=', self.subject_id.id),
            ('academic_year_id', '=', self.academic_year_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'dropped'),
            ('enrollment_id.state', 'in', ('active', 'irregular')),
        ]
        if self.class_ids:
            domain.append(('class_id', 'in', self.class_ids.ids))
        registrations = self.env['edu.uc.registration'].search(domain)
        kind = self.kind

        def eligible(registration):
            regulation = registration._regulation()
            status = registration.frequency_status
            if kind == 'uc_normal':
                return status == 'admitted' and not registration.has_exam_normal
            if kind == 'uc_appeal':
                allowed = status == 'admitted' or (status == 'excluded' and regulation.appeal_for_excluded)
                return allowed and registration.state != 'passed' and not registration.has_exam_appeal
            if kind == 'uc_special':
                enrollment = registration.enrollment_id
                if registration.state == 'passed' or registration.has_exam_special:
                    return False
                if regulation.special_final_year_only and not enrollment._edu_is_terminal():
                    return False
                missing = enrollment.uc_registration_ids.filtered(lambda r: r.state != 'passed')
                return len(missing) <= regulation.special_max_ucs
            return registration.state == 'passed' and not registration.has_exam_improvement

        return registrations.filtered(eligible)

    def action_summon(self):
        uc_sessions = self.filtered(lambda s: s.kind in UC_KINDS)
        for session in uc_sessions:
            if session.state != 'scheduled':
                raise UserError(self.env._('A sessão já foi realizada ou anulada.'))
            present = session.seat_ids.uc_registration_id
            summoned = session._edu_uc_candidates() - present
            self.env['edu.exam.seat'].create(
                [
                    {
                        'session_id': session.id,
                        'enrollment_id': registration.enrollment_id.id,
                        'uc_registration_id': registration.id,
                    }
                    for registration in summoned
                ]
            )
            if session.kind != 'uc_normal':
                summoned._edu_charge(session.kind)
            session._check_conflicts()
        return super(EduExamSession, self - uc_sessions).action_summon()


class EduExamSeat(models.Model):
    _inherit = 'edu.exam.seat'

    uc_registration_id = fields.Many2one('edu.uc.registration', string='Inscrição na UC', index=True)

    def _push_score(self):
        """Na época do superior, a nota vai para a inscrição na UC. Quem falta não tem esse exame (do normal passa
        ao recurso; no recurso, no especial e na melhoria fica como estava)."""
        registration = self.uc_registration_id
        field = UC_KINDS.get(self.session_id.kind)
        if not (registration and field):
            return super()._push_score()
        if self.attended:
            with trusted(self.env):
                registration.sudo().write({field: self.score})
        return None
