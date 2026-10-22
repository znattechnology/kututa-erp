from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

ENROLLED = ('active', 'irregular')


class EduStudent(models.Model):
    _inherit = 'edu.student'

    edu_invoice_ids = fields.One2many('account.move', 'edu_student_id', string='Facturas escolares')
    edu_scholarship_ids = fields.One2many('edu.scholarship', 'student_id', string='Bolsas')
    edu_overdue_amount = fields.Monetary(
        string='Dívida vencida', compute='_compute_edu_standing', currency_field='edu_currency_id'
    )
    edu_open_amount = fields.Monetary(
        string='Em aberto', compute='_compute_edu_standing', currency_field='edu_currency_id'
    )
    edu_in_debt = fields.Boolean(
        string='Com dívida vencida', compute='_compute_edu_standing', search='_search_edu_in_debt'
    )
    edu_gate_exempt = fields.Boolean(string='Isento do bloqueio', compute='_compute_edu_standing')
    edu_currency_id = fields.Many2one(related='company_id.currency_id', string='Moeda da escola')

    def _edu_open_invoices(self):
        return (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('edu_student_id', 'in', self.ids),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                ]
            )
        )

    @api.depends(
        'edu_invoice_ids.amount_residual',
        'edu_invoice_ids.payment_state',
        'edu_invoice_ids.state',
        'edu_invoice_ids.invoice_date_due',
        'edu_scholarship_ids.state',
        'birth_date',
    )
    def _compute_edu_standing(self):
        today = fields.Date.context_today(self)
        invoices = self._edu_open_invoices()
        for student in self:
            cutoff = today - timedelta(days=student.company_id.edu_gate_grace_days or 0)
            mine = invoices.filtered(lambda m, s=student: m.edu_student_id == s)
            student.edu_open_amount = sum(mine.mapped('amount_residual'))
            student.edu_overdue_amount = sum(
                mine.filtered(lambda m, c=cutoff: m.invoice_date_due < c).mapped('amount_residual')
            )
            student.edu_in_debt = student.edu_overdue_amount > 0.01
            student.edu_gate_exempt = student._edu_is_exempt()

    def _search_edu_in_debt(self, operator, value):
        if operator not in ('=', '!='):
            return NotImplemented
        today = fields.Date.context_today(self)
        invoices = (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('edu_student_id', '!=', False),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                    ('invoice_date_due', '<', today),
                ]
            )
        )
        debtors = invoices.edu_student_id.filtered('edu_in_debt')
        positive = (operator == '=') == bool(value)
        return [('id', 'in' if positive else 'not in', debtors.ids)]

    def _edu_is_exempt(self):
        """Isentos do bloqueio: bolseiros do Estado e alunos abaixo da idade mínima."""
        self.ensure_one()
        government = (
            self.env['edu.scholarship']
            .sudo()
            .search_count(
                [('student_id', '=', self.id), ('scholarship_type', '=', 'government'), ('state', '=', 'approved')]
            )
        )
        if government:
            return True
        minimum = self.company_id.edu_gate_min_age
        return bool(
            minimum
            and self.birth_date
            and relativedelta(fields.Date.context_today(self), self.birth_date).years < minimum
        )

    def _edu_gate(self, point):
        """(bloqueia, aviso) para a operação: rematrícula, documentos ou exames."""
        self.ensure_one()
        if not self.edu_in_debt or self.edu_gate_exempt:
            return False, False
        company = self.company_id
        message = self.env._(
            'Situação financeira pendente: %(amount)s vencidos.',
            amount=self.edu_currency_id.format(self.edu_overdue_amount),
        )
        flag = {'reenrollment': company.edu_gate_reenrollment, 'documents': company.edu_gate_documents,
                'exams': company.edu_gate_exams}.get(point)  # fmt: skip
        return company.edu_gate_mode == 'block' and bool(flag), message

    @api.model
    def _edu_update_standing(self):
        """Matrícula irregular com dívida vencida (e activa de novo quando a dívida é paga)."""
        Enrollment = self.env['edu.enrollment'].sudo()
        for company in self.env['res.company'].search([('edu_mark_irregular', '=', True)]):
            enrollments = Enrollment.search(
                [('company_id', '=', company.id), ('state', 'in', ENROLLED), ('academic_year_id.is_current', '=', True)]
            )
            for enrollment in enrollments:
                in_debt = enrollment.student_id.edu_in_debt
                if in_debt and enrollment.state == 'active':
                    enrollment.write({'state': 'irregular', 'edu_irregular_debt': True})
                elif not in_debt and enrollment.state == 'irregular' and enrollment.edu_irregular_debt:
                    # Só desfaz o que marcou: a marcação manual da secretaria fica.
                    enrollment.write({'state': 'active', 'edu_irregular_debt': False})

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action.update({'domain': [('edu_student_id', '=', self.id)], 'context': {'default_move_type': 'out_invoice'}})
        return action

    def action_receive_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Receber pagamento'),
            'res_model': 'edu.fee.payment',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_student_id': self.id},
        }

    def action_charge_service(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Cobrar serviço'),
            'res_model': 'edu.fee.service',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_student_id': self.id},
        }


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    edu_irregular_debt = fields.Boolean(
        string='Irregular por dívida', readonly=True, copy=False, help='Marcada pela tesouraria automática.'
    )

    def _edu_check_enrollment_allowed(self):
        result = super()._edu_check_enrollment_allowed()
        blocked, message = self.student_id._edu_gate('reenrollment')
        if blocked:
            raise UserError(message)
        return result

    def _edu_enrollment_warnings(self):
        warnings = super()._edu_enrollment_warnings()
        _blocked, message = self.student_id._edu_gate('reenrollment')
        return [*warnings, message] if message else warnings

    def _edu_drop_warnings(self):
        """As facturas por pagar não se anulam sozinhas (são documentos fiscais): ficam na conta do encarregado e a
        tesouraria decide se emite nota de crédito. Depois da anulação deixam de se gerar propinas."""
        warnings = super()._edu_drop_warnings()
        invoices = (
            self.env['account.move']
            .sudo()
            .search(
                [
                    ('edu_enrollment_id', '=', self.id),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'not in', ('paid', 'in_payment', 'reversed')),
                ]
            )
        )
        if invoices:
            total = sum(invoices.mapped('amount_residual'))
            warnings.append(
                self.env._(
                    '%(count)s factura(s) por pagar (%(total)s Kz): ficam na conta do encarregado; a tesouraria decide '
                    'se emite nota de crédito. Deixam de se gerar propinas.',
                    count=len(invoices),
                    total=f'{total:,.2f}'.replace(',', ' '),
                )
            )
        return warnings

    def action_confirm(self):
        result = super().action_confirm()
        if not self.env.context.get('edu_fees_skip_generation'):
            # As cobranças do mês (matrícula e propina) nascem com a matrícula.
            self.env['edu.fee.plan'].sudo()._generate_for_enrollments(self.filtered(lambda e: e.state in ENROLLED))
        return result


class EduTransfer(models.Model):
    _inherit = 'edu.transfer'

    def _complete_external(self):
        """A taxa de transferência (se o plano de propinas a tiver) cobra-se na saída."""
        result = super()._complete_external()
        enrollment = self.enrollment_id
        plan = self.env['edu.fee.plan'].sudo()._for_enrollment(enrollment)
        for line in plan.line_ids.filtered(lambda line: line.category == 'transfer'):
            line._create_invoice(enrollment, self.effective_date, f'{line.id}-transfer-{self.id}')
        return result


class EduDocument(models.Model):
    _inherit = 'edu.document'

    def _check_requirements(self):
        result = super()._check_requirements()
        blocked, message = self.student_id._edu_gate('documents')
        if blocked:
            raise UserError(message)
        if message:
            self.message_post(body=message)
        return result


class EduExamSession(models.Model):
    _inherit = 'edu.exam.session'

    def action_summon(self):
        result = super().action_summon()
        for session in self:
            blocked = session.seat_ids.filtered(lambda seat: seat.student_id._edu_gate('exams')[0])
            if blocked:
                session.message_post(
                    body=self.env._(
                        'Não convocados por dívida vencida: %s.', ', '.join(blocked.mapped('student_id.name'))
                    )
                )
                blocked.unlink()
        return result
