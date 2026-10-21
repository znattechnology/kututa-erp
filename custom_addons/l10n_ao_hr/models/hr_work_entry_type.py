from odoo import fields, models


class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    l10n_ao_justified = fields.Boolean(
        string='Falta justificada',
        default=True,
        help='As faltas injustificadas descontam no salário e contam para o limite disciplinar '
        '(LGT, arts. 219.º e 230.º).',
    )
    l10n_ao_max_days_event = fields.Integer(
        string='Máximo por evento (dias)', help='Por exemplo, 8 dias seguidos por casamento (LGT, art. 222.º).'
    )
    l10n_ao_max_days_month = fields.Integer(string='Máximo por mês (dias)')
    l10n_ao_max_days_year = fields.Integer(string='Máximo por ano (dias)')
    l10n_ao_payroll_code = fields.Char(
        string='Código na folha',
        help='Identifica o tipo de ausência no processamento salarial (por exemplo UNJUSTIFIED, UNPAID, SICK).',
    )
