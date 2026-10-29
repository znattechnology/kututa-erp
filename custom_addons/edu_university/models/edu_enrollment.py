from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import trusted
from odoo.exceptions import UserError

from .edu_uc_registration import PENDING


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    uc_registration_ids = fields.One2many('edu.uc.registration', 'enrollment_id', string='Unidades curriculares')
    uc_credits = fields.Float(string='Créditos inscritos', compute='_compute_uc_credits', digits=(5, 1))
    uc_backlog_count = fields.Integer(string='UCs em atraso', compute='_compute_uc_credits')

    @api.depends('uc_registration_ids.credits', 'uc_registration_ids.state', 'uc_registration_ids.is_backlog')
    def _compute_uc_credits(self):
        for enrollment in self:
            active = enrollment.uc_registration_ids.filtered(lambda r: r.state != 'dropped')
            enrollment.uc_credits = sum(active.mapped('credits'))
            enrollment.uc_backlog_count = len(active.filtered('is_backlog'))

    def _edu_uc_credit_excess(self):
        """Mensagem se os créditos de um semestre passam do limite do regulamento (as anuais contam metade)."""
        self.ensure_one()
        if self.level_subsystem != 'higher':
            return False
        regulation = self.env['edu.university.regulation']._get(self.company_id, self.course_id.level_id)
        limit = regulation.max_semester_credits
        if not limit:
            return False
        active = self.uc_registration_ids.filtered(lambda r: r.state != 'dropped' and not r.is_equivalence)
        annual = sum(active.filtered(lambda r: r.semester == 'annual').mapped('credits')) / 2
        for semester in ('1', '2'):
            total = annual + sum(active.filtered(lambda r, s=semester: r.semester == s).mapped('credits'))
            if total > limit:
                return self.env._(
                    '%(student)s fica com %(total)s créditos no %(semester)sº semestre; o regulamento permite '
                    '%(limit)s.',
                    student=self.student_id.name,
                    total=f'{total:g}',
                    semester=semester,
                    limit=f'{limit:g}',
                )
        return False

    def _edu_uc_missing_subjects(self):
        """As UCs obrigatórias do plano, do ano do estudante e dos anteriores, que ainda não aprovou."""
        self.ensure_one()
        lines = self.class_id.curriculum_id.line_ids.filtered(
            lambda line: line.is_compulsory and line.year_id.year <= self.class_number
        )
        passed = (
            self.env['edu.uc.registration']
            .sudo()
            .search([('student_id', '=', self.student_id.id), ('state', '=', 'passed')])
            .subject_id
        )
        return lines.subject_id - passed

    def action_confirm(self):
        result = super().action_confirm()
        self.filtered(lambda e: e.level_subsystem == 'higher' and e.state == 'active')._edu_uc_generate()
        return result

    def _edu_uc_pending_subjects(self):
        """UCs de anos anteriores por aprovar: a última inscrição do estudante nelas ficou por aprovar."""
        self.ensure_one()
        Registration = self.env['edu.uc.registration'].sudo()
        history = Registration.search(
            [
                ('student_id', '=', self.student_id.id),
                ('course_id', '=', self.course_id.id),
                ('enrollment_id', '!=', self.id),
                ('academic_year_id.date_start', '<', self.academic_year_id.date_start),
            ]
        )
        passed = history.filtered(lambda r: r.state == 'passed').subject_id
        return history.filtered(lambda r: r.state in PENDING).subject_id - passed

    def _edu_uc_generate(self):
        """Inscreve nas UCs obrigatórias e transversais do ano e nas UCs em atraso. As optativas escolhem-se depois.
        O que não pode entrar (precedência, prescrição, créditos) fica nos avisos da matrícula."""
        Registration = self.env['edu.uc.registration']
        for enrollment in self:
            # Pela ordem dos semestres: a precedência do 1.º semestre já está inscrita quando chega a do 2.º.
            lines = enrollment.class_id.curriculum_id.line_ids
            order = {line.subject_id: (line.year_id.year, line.semester or '', line.sequence) for line in lines}
            plan = enrollment.class_id.subject_line_ids.filtered('is_compulsory').subject_id
            pending = enrollment._edu_uc_pending_subjects()
            done = enrollment.uc_registration_ids.subject_id
            passed = (
                Registration.sudo()
                .search([('student_id', '=', enrollment.student_id.id), ('state', '=', 'passed')])
                .subject_id
            )
            warnings = []
            # Primeiro o que está em atraso (tem prioridade), depois o ano.
            todo = sorted(pending - done - passed, key=lambda s: order.get(s, ()))
            todo += sorted(plan - pending - done - passed, key=lambda s: order.get(s, ()))
            for subject in todo:
                try:
                    with self.env.cr.savepoint(), trusted(self.env):
                        Registration.with_context(edu_uc_generate=True).create(
                            {'enrollment_id': enrollment.id, 'subject_id': subject.id}
                        )
                except UserError as error:  # cada recusa fica nos avisos da matrícula
                    warnings.append(self.env._('Não inscrito em %(uc)s: %(why)s', uc=subject.name, why=error.args[0]))
            excess = enrollment._edu_uc_credit_excess()
            if excess:
                warnings.append(excess)
            # As disciplinas da matrícula passam a ser as UCs inscritas na turma (as optativas saem até se escolherem).
            own = enrollment.uc_registration_ids.filtered(lambda r, c=enrollment.class_id: r.class_id == c).subject_id
            with trusted(self.env):
                enrollment.with_context(edu_enrollment_reseed=True).subject_ids = own | (
                    enrollment.lower_subject_ids.subject_id
                )
                if warnings:
                    enrollment.warning = '\n'.join(filter(None, [enrollment.warning, *warnings]))
        return True

    def action_uc_equivalence(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Creditar UC por equivalência'),
            'res_model': 'edu.uc.equivalence',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_enrollment_id': self.id},
        }
