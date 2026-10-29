from odoo import api, fields, models

# Emolumentos do superior: cobram-se sozinhos quando acontece o que os justifica.
UC_TRIGGERS = [
    ('backlog', 'Inscrição em UC em atraso'),
    ('uc_appeal', 'Exame de recurso'),
    ('uc_special', 'Exame especial'),
    ('uc_improvement', 'Melhoria de nota'),
]


class EduFeePlanLine(models.Model):
    _inherit = 'edu.fee.plan.line'

    uc_trigger = fields.Selection(
        UC_TRIGGERS,
        string='Cobrar automaticamente na',
        help='Ensino superior: factura-se ao estudante, por UC, quando se inscreve numa UC em atraso ou é convocado '
        'para a época.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Os emolumentos por UC não entram na geração das propinas (só as obrigatórias) nem no balcão.
        for vals in vals_list:
            if vals.get('uc_trigger'):
                vals['mandatory'] = False
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('uc_trigger'):
            vals = dict(vals, mandatory=False)
        result = super().write(vals)
        if vals.get('mandatory'):
            self.filtered('uc_trigger').mandatory = False
        return result


class EduStudent(models.Model):
    _inherit = 'edu.student'

    def _edu_service_catalog(self):
        return super()._edu_service_catalog().filtered(lambda line: not line.uc_trigger)


class EduUcRegistration(models.Model):
    _inherit = 'edu.uc.registration'

    def _edu_charge(self, trigger):
        """Factura (uma vez por inscrição e motivo) as taxas do plano da matrícula com este gatilho. Sem planos com
        o gatilho, ou sem a facturação pronta (séries AGT, diário), não cobra e deixa nota na matrícula."""
        Move = self.env['account.move'].sudo()
        Plan = self.env['edu.fee.plan'].sudo()
        today = fields.Date.context_today(self)
        for registration in self:
            enrollment = registration.enrollment_id.sudo()
            # O plano mais específico (turma, ano, curso, instituição) que tem o emolumento.
            tiers = [
                tier.line_ids.filtered(lambda line, t=trigger: line.uc_trigger == t) for tier in Plan._tiers(enrollment)
            ]
            lines = next((tier for tier in tiers if tier), self.env['edu.fee.plan.line'])
            if not lines:
                continue
            issue = Plan._edu_billing_issue(enrollment.company_id)
            if issue:
                enrollment.message_post(
                    body=self.env._(
                        'Emolumento não cobrado (%(uc)s): %(issue)s', uc=registration.subject_id.name, issue=issue
                    )
                )
                continue
            for line in lines:
                key = f'UC-{trigger}-{registration.id}-{line.id}'
                if not Move.search_count([('edu_generation_key', '=', key)], limit=1):
                    move = line._create_invoice(enrollment, today, key)
                    move.invoice_line_ids[:1].name = f'{line.name} — {registration.subject_id.name}'
        return True
