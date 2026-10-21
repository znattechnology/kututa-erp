import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

CATEGORIES = [
    ('enrollment', 'Matrícula / confirmação'),
    ('tuition', 'Propina'),
    ('exam', 'Exame'),
    ('service', 'Serviço a pedido'),
    ('card', 'Cartão de estudante'),
    ('other', 'Outro'),
]
RECURRENCES = [
    ('one_off', 'Uma vez'),
    ('monthly', 'Mensal'),
    ('quarterly', 'Trimestral'),
    ('annual', 'Anual'),
]
ON_REQUEST = ('service', 'card', 'other')
PRODUCTS = {
    'enrollment': 'edu_fees.product_enrollment',
    'tuition': 'edu_fees.product_tuition',
    'exam': 'edu_fees.product_exam',
    'service': 'edu_fees.product_service',
    'card': 'edu_fees.product_card',
    'other': 'edu_fees.product_service',
}
MONTHS = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro',
    'Dezembro',
]  # fmt: skip
ENROLLED = ('active', 'irregular')


def month_start(day):
    return day.replace(day=1)


def due_dates(recurrence, start, end, due_day, occurrences=None):
    """Datas de vencimento de uma linha do plano na janela de cobrança (dia limitado a 1–28)."""
    day = min(max(due_day or 8, 1), 28)
    first = month_start(start)
    if recurrence == 'monthly':
        dates = []
        current = first
        while current <= end and len(dates) < (occurrences or 999):
            dates.append(current.replace(day=day))
            current += relativedelta(months=1)
        return dates
    if recurrence == 'quarterly':
        count = occurrences or 3
        span = (end.year - first.year) * 12 + end.month - first.month + 1
        step = max(1, span // count)
        return [(first + relativedelta(months=step * index)).replace(day=day) for index in range(count)]
    return [first.replace(day=day)]


class EduFeePlan(models.Model):
    _name = 'edu.fee.plan'
    _description = 'Plano de propinas'
    _inherit = ['mail.thread']
    _order = 'academic_year_id desc, sequence, id'
    _check_company_auto = True

    name = fields.Char(string='Plano', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    academic_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano lectivo',
        required=True,
        check_company=True,
        default=lambda self: self.env.company.edu_current_year_id,
    )
    course_id = fields.Many2one('edu.course', string='Curso', check_company=True)
    class_number = fields.Integer(string='Classe', help='0 = todas.')
    class_id = fields.Many2one(
        'edu.class', string='Turma', check_company=True, domain="[('academic_year_id', '=', academic_year_id)]"
    )
    date_from = fields.Date(string='Cobrar de', help='Vazio: o início do ano lectivo.')
    date_to = fields.Date(string='Cobrar até', help='Vazio: o fim do ano lectivo.')
    line_ids = fields.One2many('edu.fee.plan.line', 'plan_id', string='Taxas')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'UNIQUE(company_id, academic_year_id, name)', 'Já existe um plano com este nome no ano lectivo.'
    )

    def _window(self):
        self.ensure_one()
        return self.date_from or self.academic_year_id.date_start, self.date_to or self.academic_year_id.date_end

    @api.model
    def _for_enrollment(self, enrollment):
        """Plano aplicável: o da turma, senão o da classe, senão o do curso, senão o geral (o mais recente)."""
        plans = self.search(
            [('academic_year_id', '=', enrollment.academic_year_id.id), ('company_id', '=', enrollment.company_id.id)],
            order='create_date desc, id desc',
        )
        tiers = [
            plans.filtered(lambda p: p.class_id == enrollment.class_id),
            plans.filtered(
                lambda p: (
                    not p.class_id
                    and p.class_number
                    and p.class_number == enrollment.class_number
                    and (not p.course_id or p.course_id == enrollment.course_id)
                )
            ),  # fmt: skip
            plans.filtered(lambda p: not p.class_id and not p.class_number and p.course_id == enrollment.course_id),
            plans.filtered(lambda p: not p.class_id and not p.class_number and not p.course_id),
        ]
        for tier in tiers:
            if tier:
                return tier[:1]
        return self.browse()

    # ------------------------------------------------------------------
    # Geração das cobranças
    # ------------------------------------------------------------------
    @api.model
    def _generate_for_enrollments(self, enrollments, today=None):
        """Cria as facturas em falta até ao mês corrente. Devolve as facturas criadas."""
        today = today or fields.Date.context_today(self)
        Move = self.env['account.move']
        created = Move
        for enrollment in enrollments.filtered(lambda e: e.state in ENROLLED):
            plan = self._for_enrollment(enrollment)
            if not plan:
                continue
            created |= plan._generate(enrollment, today)
        return created

    def _generate(self, enrollment, today):
        self.ensure_one()
        company = enrollment.company_id
        start, end = self._window()
        effective = max(month_start(start), month_start(enrollment.date or start))
        existing = set(
            self.env['account.move']
            .sudo()
            .search([('edu_enrollment_id', '=', enrollment.id), ('edu_generation_key', '!=', False)])
            .mapped('edu_generation_key')
        )
        created = self.env['account.move']
        for line in self.line_ids.filtered(lambda line: line.mandatory and line.category not in ON_REQUEST):
            if line.category == 'tuition' and company.edu_billing_mode == 'fee_free':
                continue
            for due in due_dates(line.recurrence, start, end, line.due_day, line.occurrences):
                if month_start(due) > month_start(today):
                    continue  # nunca se factura um mês futuro
                if line.recurrence in ('monthly', 'quarterly') and month_start(due) < effective:
                    continue  # quem entra a meio do ano começa no mês da matrícula
                key = f'{line.id}-{due.strftime("%Y%m")}-{enrollment.id}'
                if key in existing:
                    continue
                created |= line._create_invoice(enrollment, due, key)
                existing.add(key)
        return created

    @api.model
    def _cron_generate(self):
        Enrollment = self.env['edu.enrollment']
        for company in self.env['res.company'].search([('edu_is_school', '=', True)]):
            enrollments = Enrollment.search(
                [('company_id', '=', company.id), ('state', 'in', ENROLLED), ('academic_year_id.is_current', '=', True)]
            )
            for enrollment in enrollments:
                try:
                    with self.env.cr.savepoint():
                        self.with_company(company)._generate_for_enrollments(enrollment)
                except Exception:
                    _logger.exception('Propinas: erro na geração da matrícula %s', enrollment.id)


class EduFeePlanLine(models.Model):
    _name = 'edu.fee.plan.line'
    _description = 'Taxa do plano de propinas'
    _order = 'plan_id, sequence, id'
    _check_company_auto = True

    plan_id = fields.Many2one('edu.fee.plan', string='Plano', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='plan_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Designação', required=True)
    category = fields.Selection(CATEGORIES, string='Categoria', required=True, default='tuition')
    recurrence = fields.Selection(RECURRENCES, string='Periodicidade', required=True, default='monthly')
    occurrences = fields.Integer(
        string='N.º de prestações', help='Mensal ou trimestral: limite de prestações (0 = todas).'
    )
    due_day = fields.Integer(string='Dia de vencimento', default=8)
    amount = fields.Monetary(string='Valor a pagar', required=True, help='Valor final, com IVA incluído quando o há.')
    tax_id = fields.Many2one(
        'account.tax',
        string='IVA',
        compute='_compute_tax_id',
        store=True,
        readonly=False,
        check_company=True,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
        help='Ensino: isento (M21, art. 12.º, n.º 1, al. l) do CIVA). Cartão e bens: IVA 14%.',
    )
    product_id = fields.Many2one(
        'product.product', string='Artigo', compute='_compute_product_id', store=True, readonly=False, precompute=True
    )
    mandatory = fields.Boolean(string='Obrigatória', default=True)

    @api.depends('category', 'company_id')
    def _compute_tax_id(self):
        Template = self.env['account.chart.template']
        for line in self:
            if line.tax_id or not line.company_id:
                continue
            code = 'ao_iva_sale_14' if line.category in ('card', 'other') else 'ao_iva_sale_ise_m21'
            line.tax_id = Template.with_company(line.company_id).ref(code, raise_if_not_found=False)

    @api.depends('category')
    def _compute_product_id(self):
        for line in self:
            if not line.product_id:
                line.product_id = self.env.ref(PRODUCTS[line.category], raise_if_not_found=False)

    @api.constrains('amount', 'due_day', 'occurrences', 'recurrence')
    def _check_line(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(self.env._('O valor da taxa tem de ser positivo.'))
            if not 1 <= line.due_day <= 28:
                raise ValidationError(self.env._('O dia de vencimento vai de 1 a 28.'))
            if line.occurrences and line.recurrence not in ('monthly', 'quarterly'):
                raise ValidationError(self.env._('As prestações só se aplicam às taxas mensais e trimestrais.'))

    def _price_unit(self, amount):
        """Preço sem IVA a partir do valor a pagar (com IVA incluído)."""
        rate = self.tax_id.amount if self.tax_id and self.tax_id.amount_type == 'percent' else 0.0
        return self.currency_id.round(amount / (1 + rate / 100)) if rate else amount

    def _label(self, due):
        self.ensure_one()
        if self.recurrence == 'monthly':
            return f'{self.name} — {MONTHS[due.month - 1]} {due.year}'
        return self.name

    def _create_invoice(self, enrollment, due, key, quantity=1.0):
        """Factura da taxa para o aluno (com a bolsa, se a houver), publicada logo: o l10n_ao_edi certifica-a."""
        self.ensure_one()
        student = enrollment.student_id
        discount = 0.0
        note = False
        if self.category == 'tuition':
            scholarship, discount = self.env['edu.scholarship']._relief(
                student, enrollment.academic_year_id, due, self.amount
            )
            if scholarship:
                note = self.env._('%(type)s · desconto %(amount)s', type=scholarship.type_label, amount=discount)
        payable = max(self.amount - discount, 0.0)
        journal = enrollment.company_id.edu_fees_journal_id or self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', enrollment.company_id.id)], limit=1
        )
        line_vals = {
            'product_id': self.product_id.id,
            'name': self._label(due) + (f' ({note})' if note else ''),
            'quantity': quantity,
            'price_unit': self._price_unit(payable),
            'tax_ids': [fields.Command.set(self.tax_id.ids)],
        }
        move = (
            self.env['account.move']
            .with_company(enrollment.company_id)
            .create(
                {
                    'move_type': 'out_invoice',
                    'partner_id': student._edu_billing_partner().id,
                    'journal_id': journal.id,
                    'invoice_date': fields.Date.context_today(self),
                    'invoice_date_due': due,
                    'edu_student_id': student.id,
                    'edu_enrollment_id': enrollment.id,
                    'edu_fee_line_id': self.id,
                    'edu_category': self.category,
                    'edu_due_period': due,
                    'edu_generation_key': key,
                    'edu_discount': discount,
                    'invoice_line_ids': [fields.Command.create(line_vals)],
                }
            )
        )
        if payable:
            move.action_post()
        else:
            move.write({'edu_exempt': True})  # bolsa integral: fica registada, sem factura a pagar
        return move


class EduStudent(models.Model):
    _inherit = 'edu.student'

    def _edu_billing_partner(self):
        """Adquirente (DP 71/25, art. 10.º): o aluno com NIF, senão o encarregado principal com NIF, senão o aluno."""
        self.ensure_one()
        if self.partner_id.vat:
            return self.partner_id
        guardian = self.primary_guardian_id
        if guardian and guardian.partner_id.vat:
            return guardian.partner_id
        return self.partner_id
