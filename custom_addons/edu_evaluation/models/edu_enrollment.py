from odoo import api, fields, models
from odoo.exceptions import UserError


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    subject_result_ids = fields.One2many('edu.subject.result', 'enrollment_id', string='Pauta')
    year_result_id = fields.Many2one('edu.year.result', string='Resultado do ano', compute='_compute_year_result_id')
    conditional_alerted = fields.Boolean(readonly=True, copy=False)

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
                # Matrícula condicional com até 2 disciplinas em atraso; na 9.ª e na 12.ª só fica efectiva com a
                # aprovação no exame extraordinário até ao fim do I trimestre (DE 424/25, art. 25.º, n.os 4–6, 12–14).
                if len(pending) > 2:
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

    def _edu_pending_requirements(self):
        """Disciplinas em atraso da classe anterior ainda por aprovar (a matrícula é condicional enquanto as houver)."""
        self.ensure_one()
        before = self.student_id.enrollment_ids.filtered(
            lambda e: (
                e.academic_year_id.date_start < self.academic_year_id.date_start
                and e.state not in ('draft', 'dropped', 'transferred')
            )
        ).sorted(lambda e: e.academic_year_id.date_start, reverse=True)[:1]
        result = before.sudo().year_result_id
        if not result or self.class_number <= before.class_number:
            return self.env['edu.exam.requirement']
        return result.requirement_ids.filtered(lambda r: r.state == 'pending' or not r.passed)

    def _edu_conditional_deadline(self):
        """Na 9.ª e na 12.ª, o fim do I trimestre; nas outras classes não há prazo para efectivar."""
        self.ensure_one()
        policy = self.env['edu.evaluation.policy']._get(self.company_id, self.class_id.level_id)
        if not policy._is_exam_class(self.class_number):
            return False
        first = self.academic_year_id.trimester_ids.filtered(lambda t: t.number == 1)[:1]
        return first.date_end if first else False

    def _edu_enrollment_warnings(self):
        warnings = super()._edu_enrollment_warnings()
        pending = self._edu_pending_requirements()
        if pending:
            deadline = self._edu_conditional_deadline()
            warnings.append(
                self.env._(
                    'Matrícula condicional: %(count)s disciplina(s) em atraso (%(subjects)s)%(deadline)s.',
                    count=len(pending),
                    subjects=', '.join(pending.subject_id.mapped('name')),
                    deadline=self.env._(
                        '; só fica efectiva com a aprovação no exame extraordinário até %s',
                        deadline.strftime('%d/%m/%Y'),
                    )
                    if deadline
                    else '',
                )
            )
        return warnings

    @api.model
    def _edu_alerts(self, today):
        alerts = super()._edu_alerts(today)
        late = self.browse()
        for enrollment in self.search(
            [
                ('state', 'in', ('active', 'irregular')),
                ('academic_year_id.is_current', '=', True),
                ('conditional_alerted', '=', False),
            ]
        ):
            deadline = enrollment._edu_conditional_deadline()
            if deadline and deadline < today and enrollment._edu_pending_requirements():
                late |= enrollment
        late.write({'conditional_alerted': True})
        alerts.append(
            (
                self.env._(
                    'Matrículas condicionais por efectivar: o I trimestre terminou e há disciplinas em atraso sem '
                    'aprovação no exame extraordinário (DE 424/25, art. 25.º).'
                ),
                late,
            )
        )
        return alerts

    def _edu_propose_lower_subjects(self, previous):
        """Técnico (Decreto Executivo n.º 60/08, arts. 9.º e 10.º): ao transitar, as disciplinas de continuação com 6 ou
        menos valores na classe anterior — ou com negativa nos dois anos anteriores (trienais) — fazem-se numa turma
        dessa classe, havendo vaga. Cria essas inscrições e devolve as notas a mostrar (o que não teve turma)."""
        self.ensure_one()
        if self.level_subsystem != 'technical' or self.class_number <= previous.class_number:
            return []
        continuing = self.class_id.subject_line_ids.subject_id
        notes = []
        older = self.student_id.enrollment_ids.filtered(
            lambda e: e.academic_year_id.date_start < previous.academic_year_id.date_start
        ).sorted(lambda e: e.academic_year_id.date_start, reverse=True)[:1]
        for result in previous.sudo().subject_result_ids.filtered(lambda r: r.complete and r.subject_id in continuing):
            subject = result.subject_id
            before = older.sudo().subject_result_ids.filtered(lambda r, s=subject: r.subject_id == s and r.complete)
            two_negatives = result.final < 10 and before and before[:1].final < 10
            if result.final > 6 and not two_negatives:
                continue
            classes = self.env['edu.class'].search(
                [
                    ('academic_year_id', '=', self.academic_year_id.id),
                    ('course_id', '=', self.course_id.id),
                    ('class_number', '=', previous.class_number),
                ]
            )
            target = classes.filtered(lambda c: c.name == previous.class_id.name)[:1] or classes[:1]
            if not target:
                notes.append(
                    self.env._(
                        '%(subject)s: sem turma da %(number)sª para a fazer.',
                        subject=subject.name,
                        number=previous.class_number,
                    )
                )
                continue
            reason = (
                self.env._('Negativa em dois anos seguidos')
                if two_negatives and result.final > 6
                else self.env._('%s valores na classe anterior', f'{result.final:g}')
            )
            self.env['edu.enrollment.lower.subject'].create(
                {'enrollment_id': self.id, 'subject_id': subject.id, 'class_id': target.id, 'reason': reason}
            )
            notes.append(
                self.env._('%(subject)s na %(class)s', subject=subject.name, **{'class': target._editor_label()})
            )
        return notes

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
