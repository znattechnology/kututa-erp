from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    edu_fees_journal_id = fields.Many2one(
        'account.journal',
        string='Diário das propinas',
        check_company=True,
        domain="[('type', '=', 'sale')]",
        help='Por omissão, o primeiro diário de vendas.',
    )
    edu_gate_mode = fields.Selection(
        [('warn', 'Avisar'), ('block', 'Bloquear')],
        string='Devedores',
        default='warn',
        help='Avisar: as operações seguem com aviso. Bloquear: as operações marcadas ficam impedidas.',
    )
    edu_gate_grace_days = fields.Integer(string='Tolerância da dívida (dias)', default=8)
    edu_gate_min_age = fields.Integer(
        string='Isentos abaixo de (anos)', default=15, help='Os alunos mais novos não são bloqueados.'
    )
    edu_gate_reenrollment = fields.Boolean(string='Bloquear a rematrícula', default=True)
    edu_gate_documents = fields.Boolean(string='Bloquear os documentos', default=True)
    edu_gate_exams = fields.Boolean(string='Bloquear os exames', default=True)
    edu_gate_grades = fields.Boolean(
        string='Esconder as notas no portal', default=True, help='O aluno e o encarregado não vêem as notas no portal.'
    )
    edu_mark_irregular = fields.Boolean(
        string='Marcar a matrícula como irregular',
        default=True,
        help='Com dívida vencida (depois da tolerância), a matrícula passa a «irregular» e volta a «activa» quando a '
        'dívida é paga.',
    )
    edu_scholarship_approval = fields.Boolean(
        string='Bolsas aprovadas por outro utilizador', default=True, help='Quem regista a bolsa não a pode aprovar.'
    )
    # Controlo interno (o «FinanceControlConfig» do secPed): o que precisa de um segundo utilizador.
    edu_cash_approval_threshold = fields.Monetary(
        string='Numerário acima de',
        currency_field='currency_id',
        default=150000.0,
        help='Um pagamento em numerário acima deste valor fica por confirmar até outro utilizador o aprovar. 0: todos.',
    )
    edu_cash_approval = fields.Boolean(string='Numerário alto aprovado por outro utilizador', default=True)
    edu_void_approval = fields.Boolean(
        string='Anulações aprovadas por outro utilizador',
        default=True,
        help='Anular uma factura (nota de crédito) fica pedido até outro utilizador o aprovar.',
    )
    edu_controls_changed_by_id = fields.Many2one('res.users', string='Controlos alterados por', readonly=True)
    edu_controls_changed_date = fields.Datetime(string='Controlos alterados em', readonly=True)
