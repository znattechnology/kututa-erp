from odoo import fields, models

from .edu_fee_plan import CATEGORIES


class AccountMove(models.Model):
    _inherit = 'account.move'

    edu_student_id = fields.Many2one('edu.student', string='Aluno', index=True, copy=False)
    edu_enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', index=True, copy=False)
    edu_fee_line_id = fields.Many2one('edu.fee.plan.line', string='Taxa', copy=False)
    edu_category = fields.Selection(CATEGORIES + [('late_fee', 'Multa')], string='Categoria escolar', copy=False)
    edu_due_period = fields.Date(string='Vencimento da taxa', copy=False)
    edu_generation_key = fields.Char(string='Chave de geração', copy=False, index=True)
    edu_discount = fields.Monetary(string='Desconto da bolsa', copy=False)
    edu_exempt = fields.Boolean(string='Isenta pela bolsa', copy=False)
    edu_late_fee_origin_id = fields.Many2one('account.move', string='Factura em atraso', copy=False, index=True)

    _edu_generation_key_uniq = models.UniqueIndex(
        '(company_id, edu_generation_key) WHERE edu_generation_key IS NOT NULL',
        'Esta cobrança já foi gerada.',
    )
