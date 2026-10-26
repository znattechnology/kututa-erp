import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import split_every

_logger = logging.getLogger(__name__)

CATEGORIES = [
    ('application', 'Inscrição / candidatura'),
    ('enrollment', 'Matrícula (primeira vez)'),
    ('confirmation', 'Confirmação de matrícula'),
    ('transfer', 'Transferência'),
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
ON_REQUEST = ('service', 'card', 'other', 'application', 'transfer')
# A matrícula cobra-se a quem entra na escola; a confirmação a quem continua (DE Conjunto 40/21 tabela as duas).
FIRST_ENROLLMENT_TYPES = ('new', 'transfer_in')
PRODUCTS = {
    'application': 'edu_fees.product_application',
    'enrollment': 'edu_fees.product_enrollment',
    'confirmation': 'edu_fees.product_confirmation',
    'transfer': 'edu_fees.product_transfer',
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
# A tarefa diária grava ao fim de cada lote de matrículas: uma falha não desfaz o que já foi facturado.
BATCH = 50


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
    date_from = fields.Date(
        string='Cobrar a partir de',
        help='O primeiro mês cobrado. Vazio: o início do ano lectivo. Os meses anteriores nunca se facturam.',
    )
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
        for tier in self._tiers(enrollment):
            if tier:
                return tier[:1]
        return self.browse()

    @api.model
    def _tiers(self, enrollment):
        """Os planos do ano que se aplicam à matrícula, do mais específico ao geral: turma, classe, curso, escola."""
        plans = self.search(
            [('academic_year_id', '=', enrollment.academic_year_id.id), ('company_id', '=', enrollment.company_id.id)],
            order='create_date desc, id desc',
        )
        return [
            plans.filtered(lambda p: p.class_id and p.class_id == enrollment.class_id),
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

    # ------------------------------------------------------------------
    # Geração das cobranças
    # ------------------------------------------------------------------
    @api.model
    def _edu_billing_issue(self, company, day=None):
        """Porque é que a escola ainda não pode emitir as propinas (ou False): numa escola angolana, a factura só
        sai certificada (AGT). Uma factura emitida sem a facturação electrónica ligada nunca chega à AGT e não se
        desfaz, por isso não se gera nenhuma até estar tudo pronto."""
        if company.account_fiscal_country_id.code != 'AO':
            return False
        day = day or fields.Date.context_today(self)
        if not company.l10n_ao_edi_enabled:
            return self.env._(
                'A facturação electrónica (AGT) de %s não está ligada: as facturas só se emitem depois de a ligar.',
                company.name,
            )
        try:
            company._l10n_ao_edi_check_configuration()
        except UserError as error:
            return error.args[0]
        if not self.env['l10n_ao_edi.series']._l10n_ao_edi_find(company, 'FT', day.year):
            return self.env._('Falta a série AGT activa das facturas (FT) de %s.', day.year)
        return False

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
        """Cria as facturas em falta da matrícula até ao mês de ``today``."""
        created = self.env['account.move']
        for line, due, key, due_date in self._pending(enrollment, today):
            created |= line._create_invoice(enrollment, due, key, due_date=due_date)
        return created

    def _pending(self, enrollment, today):
        """As cobranças em falta da matrícula até ao mês de ``today``: (linha, mês, chave, vencimento)."""
        self.ensure_one()
        company = enrollment.company_id
        start, end = self._window()
        effective = max(month_start(start), month_start(enrollment.date or start))
        moves = (
            self.env['account.move']
            .sudo()
            .search([('edu_enrollment_id', '=', enrollment.id), ('edu_generation_key', '!=', False)])
        )
        # A chave é da matrícula, da categoria e do período (não da linha do plano): mudar de turma ou de plano não
        # volta a facturar o que já foi facturado. As facturas antigas contam pela categoria e pelo período.
        existing = set(moves.mapped('edu_generation_key')) | {
            f'{m.edu_category}-{m.edu_due_period.strftime("%Y%m")}-{enrollment.id}' for m in moves if m.edu_due_period
        }
        pending = []
        seen = {}
        for line in self.line_ids.filtered(lambda line: line.mandatory and line.category not in ON_REQUEST):
            # Duas taxas da mesma categoria no plano distinguem-se pela ordem.
            index = seen[line.category] = seen.get(line.category, -1) + 1
            tag = line.category + (f'{index + 1}' if index else '')
            if line.category == 'tuition' and company.edu_billing_mode == 'fee_free':
                continue
            first = enrollment.enrollment_type in FIRST_ENROLLMENT_TYPES
            if (line.category == 'enrollment' and not first) or (line.category == 'confirmation' and first):
                continue
            for due in due_dates(line.recurrence, start, end, line.due_day, line.occurrences):
                if month_start(due) > month_start(today):
                    continue  # nunca se factura um mês futuro
                if line.recurrence in ('monthly', 'quarterly') and month_start(due) < effective:
                    continue  # quem entra a meio do ano começa no mês da matrícula
                key = f'{tag}-{due.strftime("%Y%m")}-{enrollment.id}'
                if key in existing:
                    continue
                # Quem se matricula depois do vencimento não nasce devedor: vence no dia da matrícula.
                pending.append((line, due, key, max(due, enrollment.date or due)))
                existing.add(key)
        return pending

    @api.model
    def _cron_generate(self):
        Enrollment = self.env['edu.enrollment']
        Cron = self.env['ir.cron']
        for company in self.env['res.company'].search([('edu_is_school', '=', True)]):
            issue = self._edu_billing_issue(company)
            if issue:
                _logger.warning('Propinas de %s não geradas: %s', company.name, issue)
                continue
            enrollments = Enrollment.search(
                [('company_id', '=', company.id), ('state', 'in', ENROLLED), ('academic_year_id.is_current', '=', True)]
            )
            Cron._commit_progress(remaining=len(enrollments))
            for ids in split_every(BATCH, enrollments.ids):
                for enrollment in Enrollment.browse(ids):
                    try:
                        with self.env.cr.savepoint():
                            self.with_company(company)._generate_for_enrollments(enrollment)
                    except Exception:
                        _logger.exception('Propinas: erro na geração da matrícula %s', enrollment.id)
                if not Cron._commit_progress(len(ids)):
                    return  # sem tempo: a tarefa volta a correr e continua onde ficou


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
        """O IVA segue a categoria (pode alterar-se à mão depois de escolher a categoria)."""
        Template = self.env['account.chart.template']
        for line in self:
            if not line.company_id:
                continue
            code = 'ao_iva_sale_14' if line.category in ('card', 'other') else 'ao_iva_sale_ise_m21'
            line.tax_id = Template.with_company(line.company_id).ref(code, raise_if_not_found=False)

    @api.depends('category')
    def _compute_product_id(self):
        for line in self:
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

    def _payable(self, enrollment, due):
        """O valor a pagar da taxa no mês (com a bolsa, só na propina): (valor, desconto, nota da bolsa)."""
        self.ensure_one()
        discount = 0.0
        note = False
        if self.category == 'tuition':
            scholarship, discount = self.env['edu.scholarship']._relief(
                enrollment.student_id, enrollment.academic_year_id, due, self.amount
            )
            if scholarship:
                note = self.env._('%(type)s · desconto %(amount)s', type=scholarship.type_label, amount=discount)
        return max(self.amount - discount, 0.0), discount, note

    def _create_invoice(self, enrollment, due, key, quantity=1.0, due_date=None):
        """Factura da taxa para o aluno (com a bolsa, se a houver), publicada logo: o l10n_ao_edi certifica-a."""
        self.ensure_one()
        student = enrollment.student_id
        payable, discount, note = self._payable(enrollment, due)
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
                    'invoice_date_due': due_date or due,
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

    def _edu_service_catalog(self):
        """O que se cobra a pedido ao aluno (batas, declarações, certificados, o cartão…): as taxas a pedido dos planos
        do ano que se aplicam à matrícula. O mesmo nome em dois planos conta uma vez, com o valor do mais específico."""
        self.ensure_one()
        Line = self.env['edu.fee.plan.line']
        enrollment = self.current_enrollment_id
        if not enrollment:
            return Line
        catalog = Line
        names = set()
        for tier in self.env['edu.fee.plan']._tiers(enrollment):
            for line in tier.line_ids:
                if line.category not in ON_REQUEST and line.mandatory:
                    continue
                name = line.name.strip().lower()
                if name not in names:
                    names.add(name)
                    catalog |= line
        return catalog

    def _edu_charge_services(self, items, due_date=None, key=None):
        """Venda ao balcão, como no secPed: vários serviços e produtos do catálogo numa só factura. ``items`` são pares
        (taxa, quantidade). Repetir com a mesma chave devolve a factura já emitida (um erro de rede não cobra duas
        vezes). O cartão cobra-se sozinho: cada factura paga do cartão dá um cartão."""
        self.ensure_one()
        enrollment = self.current_enrollment_id
        if not enrollment:
            raise UserError(self.env._('O aluno não tem matrícula activa.'))
        Move = self.env['account.move']
        if key:
            key = f'SALE-{self.id}-{key}'
            existing = Move.search([('edu_generation_key', '=', key)], limit=1)
            if existing:
                return existing
        catalog = self._edu_service_catalog()
        lines = []
        for line_id, quantity in items:
            line = catalog.filtered(lambda line, line_id=line_id: line.id == line_id)
            if not line:
                raise UserError(self.env._('Esse serviço não está no catálogo do aluno.'))
            if int(quantity) < 1:
                raise UserError(self.env._('A quantidade tem de ser pelo menos 1.'))
            lines.append((line, int(quantity)))
        if not lines:
            raise UserError(self.env._('Escolha pelo menos um serviço ou produto.'))
        fees = self.env['edu.fee.plan.line'].browse([line.id for line, _quantity in lines])
        if 'card' in fees.mapped('category') and (len(lines) > 1 or lines[0][1] > 1):
            raise UserError(
                self.env._('O cartão de estudante cobra-se sozinho: retire os outros itens e cobre-o à parte.')
            )
        issue = self.env['edu.fee.plan']._edu_billing_issue(enrollment.company_id)
        if issue:
            raise UserError(issue)
        today = fields.Date.context_today(self)
        journal = enrollment.company_id.edu_fees_journal_id or self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', enrollment.company_id.id)], limit=1
        )
        categories = set(fees.mapped('category'))
        move = Move.with_company(enrollment.company_id).create(
            {
                'move_type': 'out_invoice',
                'partner_id': self._edu_billing_partner().id,
                'journal_id': journal.id,
                'invoice_date': today,
                'invoice_date_due': max(due_date or today, today),
                'edu_student_id': self.id,
                'edu_enrollment_id': enrollment.id,
                'edu_fee_line_id': fees.id if len(fees) == 1 else False,
                'edu_category': categories.pop() if len(categories) == 1 else 'service',
                'edu_due_period': today,
                'edu_generation_key': key or False,
                'invoice_line_ids': [
                    fields.Command.create(
                        {
                            'product_id': line.product_id.id,
                            'name': line.name,
                            'quantity': quantity,
                            'price_unit': line._price_unit(line.amount),
                            'tax_ids': [fields.Command.set(line.tax_id.ids)],
                        }
                    )
                    for line, quantity in lines
                ],
            }
        )
        move.action_post()
        return move

    def _edu_pay_invoices(self, allocations, journal, day=None, memo=None):
        """Pagamento ao balcão com o valor escolhido para cada factura (como no secPed): ``allocations`` são pares
        (factura, valor). Um pagamento por adquirente (o aluno ou o encarregado), com um recibo que lista o que liquidou
        em cada factura. As facturas pagas por inteiro reconciliam-se primeiro; as pagas em parte ficam com o valor
        exacto (uma parcial com esse montante, como o Odoo as cria)."""
        self.ensure_one()
        currency = self.company_id.currency_id
        day = day or fields.Date.context_today(self)
        by_partner = {}
        for move, value in allocations:
            amount = currency.round(value)
            if move.edu_student_id != self or move.state != 'posted' or move.move_type != 'out_invoice':
                raise UserError(self.env._('A factura %s não é deste aluno.', move.name))
            if amount <= 0:
                continue
            if currency.compare_amounts(amount, move.amount_residual) > 0:
                raise UserError(
                    self.env._(
                        'O valor de %(invoice)s passa o que falta pagar dela (%(due)s).',
                        invoice=move.name,
                        due=currency.format(move.amount_residual),
                    )
                )
            by_partner.setdefault(move.partner_id, []).append((move, amount))
        if not by_partner:
            raise UserError(self.env._('Escolha pelo menos uma factura ou um serviço.'))
        Payment = self.env['account.payment']
        payments = Payment
        for partner, rows in by_partner.items():
            payment = Payment.create(
                {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': partner.id,
                    'amount': sum(amount for _move, amount in rows),
                    'date': day,
                    'journal_id': journal.id,
                    'memo': memo or self.env._('Propinas de %s', self.name),
                }
            )
            payment.action_post()
            credit = payment.move_id.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')
            rows.sort(key=lambda row: currency.compare_amounts(row[1], row[0].amount_residual) < 0)
            for move, amount in rows:
                debit = move.line_ids.filtered(
                    lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
                )
                if currency.compare_amounts(amount, move.amount_residual) == 0:
                    (credit | debit).reconcile()
                else:
                    self.env['account.partial.reconcile'].create(
                        {
                            'debit_move_id': debit[:1].id,
                            'credit_move_id': credit.id,
                            'amount': amount,
                            'debit_amount_currency': amount,
                            'credit_amount_currency': amount,
                        }
                    )
            payments |= payment
        # O recibo das facturas liquidadas (só com a facturação electrónica ligada; sem ela não faz nada).
        payments._l10n_ao_edi_issue_receipt()
        return payments
