from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.addons.edu_fees.models.edu_fee_plan import ENROLLED, MONTHS
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_round, format_amount

MONTH_SHORT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
CATEGORY_LABELS = {
    'application': 'Inscrição',
    'enrollment': 'Matrícula',
    'confirmation': 'Confirmação',
    'transfer': 'Transferência',
    'tuition': 'Propina',
    'exam': 'Exame',
    'service': 'Serviço',
    'card': 'Cartão',
    'other': 'Outro',
    'late_fee': 'Multa',
}
TOP_DEBTORS = 8
RECENT_PAYMENTS = 8
DEBT_LIST_LIMIT = 300
# As formas de pagamento ao balcão, como no secPed, e o diário de cada uma.
PAY_JOURNALS = {'cash': 'cash', 'pos': 'bank', 'deposit': 'bank'}


def with_views(action):
    """Uma acção de janela para o doAction do cliente: precisa de ``views`` (os botões dos formulários recebem-na já
    completada pelo servidor; uma acção devolvida por um método chamado da página não)."""
    if action.get('type') == 'ir.actions.act_window' and not action.get('views'):
        action = {**action, 'views': [(False, mode) for mode in (action.get('view_mode') or 'list,form').split(',')]}
    return action


class EduTreasury(models.AbstractModel):
    """A tesouraria, como a «Administração Financeira» do secPed: o painel da cobrança (o que venceu e quanto se
    cobrou, o que está em atraso e de quantos alunos, o que pede atenção, facturado e cobrado por mês, os maiores
    atrasos e os últimos pagamentos), «Facturar e receber» (os alunos de uma turma com a conta-corrente, ou os em
    atraso da escola inteira) e a ficha financeira do aluno. Só para a tesouraria e a direcção."""

    _name = 'edu.treasury'
    _description = 'Tesouraria'

    def _check_access(self):
        if not self.env.user.has_group('edu_fees.group_edu_finance'):
            raise AccessError(self.env._('A tesouraria é só para a tesouraria e a direcção.'))

    def _money(self, amount):
        return format_amount(self.env, amount, self.env.company.currency_id)

    def _today(self):
        return fields.Date.context_today(self)

    def _invoice_domain(self):
        return [
            ('company_id', '=', self.env.company.id),
            ('edu_student_id', '!=', False),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ]

    # O painel

    @api.model
    def home_data(self):
        self._check_access()
        company = self.env.company
        today = self._today()
        grace = company.edu_gate_grace_days or 0
        Move = self.env['account.move']
        invoices = Move.search(self._invoice_domain())
        due = invoices.filtered(lambda m: m.invoice_date_due and m.invoice_date_due <= today)
        due_invoiced = sum(due.mapped('amount_total'))
        due_collected = due_invoiced - sum(due.mapped('amount_residual'))
        limit = today - timedelta(days=grace)
        overdue = invoices.filtered(
            lambda m: m.amount_residual > 0.005 and m.invoice_date_due and m.invoice_date_due < limit
        )
        upcoming = invoices.filtered(lambda m: m.invoice_date_due and m.invoice_date_due > today)
        pending = self.env['edu.fee.payment.request'].search(
            [('company_id', '=', company.id), ('state', '=', 'pending')], order='create_date'
        )
        return {
            'company': company.name,
            'today': today.strftime('%d/%m/%Y'),
            'grace_days': grace,
            'due_invoiced': due_invoiced,
            'due_invoiced_text': self._money(due_invoiced),
            'due_collected_text': self._money(due_collected),
            'collection_rate': round(100 * due_collected / due_invoiced, 1) if due_invoiced else None,
            'overdue_text': self._money(sum(overdue.mapped('amount_residual'))),
            'overdue_amount': sum(overdue.mapped('amount_residual')),
            'overdue_count': len(overdue),
            'students_in_debt': len(overdue.edu_student_id),
            'students_total': len(invoices.edu_student_id),
            'upcoming_text': self._money(sum(upcoming.mapped('amount_residual'))),
            'upcoming': sum(upcoming.mapped('amount_residual')),
            'pending_payments': len(pending),
            'pending_oldest_days': (today - pending[:1].create_date.date()).days if pending else 0,
            'attention': self._attention(company, pending),
            'monthly': self._monthly(company, today),
            'top_debtors': self._top_debtors(overdue),
            'recent_payments': self._recent_payments(company),
        }

    def _attention(self, company, pending):
        """O que pede acção: comprovativos por validar e a facturação certificada (DP 71/25)."""
        items = []
        if pending:
            items.append(
                {
                    'key': 'pending',
                    'text': self.env._(
                        '%s pagamento(s) enviado(s) pelos encarregados à espera de validação. Até lá, as facturas '
                        'continuam por pagar.',
                        len(pending),
                    ),
                    'action': 'requests',
                    'label': self.env._('Validar'),
                    'grave': False,
                }
            )
        if not company.vat:
            items.append(
                {
                    'key': 'vat',
                    'text': self.env._('A escola não tem NIF registado: as facturas não podem ser certificadas.'),
                    'grave': True,
                }
            )
        if company.account_fiscal_country_id.code == 'AO' and not company.l10n_ao_edi_enabled:
            items.append(
                {
                    'key': 'edi',
                    'text': self.env._(
                        'A facturação electrónica (AGT) não está ligada: as propinas não se geram e as facturas não '
                        'chegam à AGT.'
                    ),
                    'grave': True,
                }
            )
        Move = self.env['account.move']
        rejected = Move.search_count(
            [('company_id', '=', company.id), ('l10n_ao_edi_state', '=', 'invalid'), ('edu_student_id', '!=', False)]
        )
        if rejected:
            items.append(
                {
                    'key': 'rejected',
                    'text': self.env._(
                        '%s factura(s) rejeitada(s) pela AGT: corrigem-se e voltam a enviar-se.', rejected
                    ),
                    'action': 'agt',
                    'label': self.env._('Ver na AGT'),
                    'grave': True,
                }
            )
        waiting = Move.search_count(
            [
                ('company_id', '=', company.id),
                ('l10n_ao_edi_state', '=', 'to_send'),
                ('create_date', '<', fields.Datetime.now() - timedelta(days=1)),
            ]
        )
        if waiting:
            items.append(
                {
                    'key': 'waiting',
                    'text': self.env._('%s documento(s) há mais de um dia à espera de envio para a AGT.', waiting),
                    'action': 'agt',
                    'label': self.env._('Ver na AGT'),
                    'grave': False,
                }
            )
        return items

    def _monthly(self, company, today):
        """Os últimos seis meses: o facturado (pelo vencimento) e o cobrado (pela data do pagamento)."""
        first = today.replace(day=1) - relativedelta(months=5)
        months = [first + relativedelta(months=i) for i in range(6)]
        invoiced = defaultdict(float)
        for move in self.env['account.move'].search([*self._invoice_domain(), ('invoice_date_due', '>=', first)]):
            invoiced[move.invoice_date_due.replace(day=1)] += move.amount_total
        self.env['account.move'].flush_model()
        self.env['account.partial.reconcile'].flush_model()
        self.env.cr.execute(
            """
            SELECT date_trunc('month', apr.max_date)::date, SUM(apr.amount)
              FROM account_partial_reconcile apr
              JOIN account_move_line line ON line.id = apr.debit_move_id
              JOIN account_move move ON move.id = line.move_id
             WHERE move.edu_student_id IS NOT NULL AND move.move_type = 'out_invoice'
               AND move.company_id = %s AND apr.max_date >= %s
             GROUP BY 1
            """,
            [company.id, first],
        )
        collected = dict(self.env.cr.fetchall())
        return [
            {
                'month': m.strftime('%Y-%m'),
                'label': MONTH_SHORT[m.month - 1],
                'name': f'{MONTHS[m.month - 1]} {m.year}',
                'invoiced': invoiced.get(m, 0.0),
                'collected': float(collected.get(m, 0.0)),
                'invoiced_text': self._money(invoiced.get(m, 0.0)),
                'collected_text': self._money(float(collected.get(m, 0.0))),
            }
            for m in months
        ]

    def _top_debtors(self, overdue):
        by_student = defaultdict(lambda: [0.0, None])
        for move in overdue:
            cell = by_student[move.edu_student_id]
            cell[0] += move.amount_residual
            cell[1] = min(filter(None, [cell[1], move.invoice_date_due]))
        rows = sorted(by_student.items(), key=lambda item: -item[1][0])[:TOP_DEBTORS]
        return [
            {
                'student_id': student.id,
                'name': student.name,
                'class': student.current_class_id._editor_label() if student.current_class_id else '',
                'matricula': student.matricula_number or '',
                'amount': self._money(amount),
                'since': oldest.strftime('%d/%m/%Y') if oldest else '',
            }
            for student, (amount, oldest) in rows
        ]

    def _recent_payments(self, company):
        """Os últimos pagamentos de propinas (os imputados a facturas dos alunos)."""
        self.env['account.payment'].flush_model()
        self.env['account.partial.reconcile'].flush_model()
        self.env.cr.execute(
            """
            SELECT pay.id, MIN(move.edu_student_id)
              FROM account_partial_reconcile apr
              JOIN account_move_line dl ON dl.id = apr.debit_move_id
              JOIN account_move move ON move.id = dl.move_id
              JOIN account_move_line cl ON cl.id = apr.credit_move_id
              JOIN account_payment pay ON pay.move_id = cl.move_id
             WHERE move.edu_student_id IS NOT NULL AND move.company_id = %s
             GROUP BY pay.id
             ORDER BY MAX(pay.date) DESC, pay.id DESC
             LIMIT %s
            """,
            [company.id, RECENT_PAYMENTS],
        )
        pairs = self.env.cr.fetchall()
        payments = self.env['account.payment'].browse([p for p, _s in pairs])
        students = {p: self.env['edu.student'].browse(s) for p, s in pairs}
        return [
            {
                'id': payment.id,
                'student_id': students[payment.id].id,
                'student': students[payment.id].name,
                'amount': self._money(payment.amount),
                'date': payment.date.strftime('%d/%m/%Y'),
                'journal': payment.journal_id.name,
                'receipt': payment.l10n_ao_edi_document_no or '',
            }
            for payment in payments
        ]

    @api.model
    def run_overdue(self):
        """«Actualizar o vencimento»: as multas e a situação financeira, o que a tarefa diária faz de noite."""
        self._check_access()
        self.env['edu.late.fee.rule'].sudo()._cron_overdue()
        return True

    @api.model
    def open(self, key, res_id=False):
        self._check_access()
        if key == 'requests':
            return self.env['ir.actions.act_window']._for_xml_id('edu_fees.action_edu_fee_payment_request')
        if key == 'agt':
            return self.env['ir.actions.act_window']._for_xml_id('l10n_ao_edi.l10n_ao_edi_document_action')
        if key == 'debtors':
            return {
                'type': 'ir.actions.client',
                'tag': 'edu_roles.treasury_students',
                'name': self.env._('Facturar e receber'),
                'context': {'debt_only': True},
            }
        if key == 'student':
            return {
                'type': 'ir.actions.client',
                'tag': 'edu_roles.treasury_student',
                'name': self.env['edu.student'].browse(res_id).name,
                'context': {'student_id': res_id},
            }
        if key == 'payment':
            return self.env.ref('account.action_report_payment_receipt').preview_action(
                self.env['account.payment'].browse(res_id)
            )
        raise UserError(self.env._('Página desconhecida.'))

    # Facturar e receber

    def _balances(self, students):
        """A conta-corrente de cada aluno: em atraso (vencido por pagar), por pagar (com o que ainda vai vencer) e o
        já pago."""
        today = self._today()
        out = defaultdict(lambda: {'overdue': 0.0, 'open': 0.0, 'paid': 0.0, 'since': None})
        for move in self.env['account.move'].search([*self._invoice_domain(), ('edu_student_id', 'in', students.ids)]):
            cell = out[move.edu_student_id.id]
            cell['open'] += move.amount_residual
            cell['paid'] += move.amount_total - move.amount_residual
            if move.amount_residual > 0.005 and move.invoice_date_due and move.invoice_date_due < today:
                cell['overdue'] += move.amount_residual
                cell['since'] = min(filter(None, [cell['since'], move.invoice_date_due]))
        return out

    def _row(self, student, balance, number=None):
        return {
            'student_id': student.id,
            'number': number or '',
            'name': student.name,
            'matricula': student.matricula_number or '',
            'class': student.current_class_id._editor_label() if student.current_class_id else '',
            'overdue': balance['overdue'],
            'open': balance['open'],
            'paid': balance['paid'],
            'overdue_text': self._money(balance['overdue']) if balance['overdue'] > 0.005 else '',
            'open_text': self._money(balance['open']) if balance['open'] > 0.005 else '',
            'paid_text': self._money(balance['paid']) if balance['paid'] > 0.005 else '',
            'since': balance['since'].strftime('%d/%m/%Y') if balance['since'] else '',
        }

    @api.model
    def classes(self):
        """As turmas do ano em curso, por curso, com quantos alunos estão em atraso em cada uma."""
        self._check_access()
        year = self.env.company.edu_current_year_id
        classes = self.env['edu.class'].search([('academic_year_id', '=', year.id)])
        enrollments = self.env['edu.enrollment'].search([('class_id', 'in', classes.ids), ('state', 'in', ENROLLED)])
        balances = self._balances(enrollments.student_id)
        students = defaultdict(int)
        debtors = defaultdict(int)
        for enrollment in enrollments:
            students[enrollment.class_id.id] += 1
            if balances[enrollment.student_id.id]['overdue'] > 0.005:
                debtors[enrollment.class_id.id] += 1
        return {
            'year': year.name or '',
            'classes': [
                {
                    'id': c.id,
                    'name': c._editor_label(),
                    'course': c.course_id.name or '',
                    'students': students[c.id],
                    'debtors': debtors[c.id],
                }
                for c in classes.sorted(lambda c: (c.course_id.name or '', c.class_number, c.name))
            ],
        }

    @api.model
    def students(self, class_id=False, debt_only=False, query=''):
        """Os alunos de uma turma (pelo número) com a conta-corrente; ou, «só em atraso» sem turma, os em atraso da
        escola inteira, do maior atraso para o menor. A pesquisa procura pelo nome ou pelo n.º de matrícula."""
        self._check_access()
        query = (query or '').strip()
        Student = self.env['edu.student']
        if class_id:
            enrollments = self.env['edu.enrollment'].search(
                [('class_id', '=', class_id), ('state', 'in', ENROLLED)], order='order_number, id'
            )
            pairs = [(e.student_id, e.order_number) for e in enrollments]
        elif query or debt_only:
            domain = [('company_id', '=', self.env.company.id)]
            if query:
                domain += ['|', ('name', 'ilike', query), ('matricula_number', 'ilike', query)]
            if debt_only:
                domain.append(('edu_invoice_ids.amount_residual', '>', 0))
            pairs = [(s, None) for s in Student.search(domain, limit=DEBT_LIST_LIMIT, order='name')]
        else:
            return {'rows': [], 'totals': None}
        balances = self._balances(Student.browse([s.id for s, _n in pairs]))
        rows = [self._row(s, balances[s.id], n) for s, n in pairs]
        if class_id and query:
            needle = query.lower()
            rows = [r for r in rows if needle in r['name'].lower() or needle in r['matricula'].lower()]
        if debt_only:
            rows = [r for r in rows if r['overdue'] > 0.005]
            if not class_id:
                rows.sort(key=lambda r: -r['overdue'])
        return {
            'rows': rows,
            'totals': {
                'overdue': self._money(sum(r['overdue'] for r in rows)),
                'open': self._money(sum(r['open'] for r in rows)),
                'paid': self._money(sum(r['paid'] for r in rows)),
                'debtors': sum(1 for r in rows if r['overdue'] > 0.005),
            },
        }

    # A ficha financeira do aluno

    @api.model
    def student_data(self, student_id):
        """O que o aluno deve e desde quando, as facturas por pagar, os documentos fiscais (facturas, notas de crédito e
        recibos) e os dados que vão nas facturas (quem compra, o NIF e a morada)."""
        self._check_access()
        student = self.env['edu.student'].browse(student_id).exists()
        if not student or student.company_id != self.env.company:
            raise UserError(self.env._('Aluno não encontrado.'))
        today = self._today()
        balance = self._balances(student)[student.id]
        Move = self.env['account.move']
        moves = Move.search(
            [
                ('company_id', '=', self.env.company.id),
                ('edu_student_id', '=', student.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', 'in', ('posted', 'cancel')),
            ],
            order='invoice_date desc, id desc',
        )
        open_moves = moves.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted' and m.amount_residual > 0.005
        ).sorted(lambda m: (m.invoice_date_due or today, m.id))

        def label(move):
            line = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')[:1]
            name = line.name or move.name or ''
            return name[:1].upper() + name[1:]

        payments = self.env['account.payment'].browse()
        for move in moves.filtered(lambda m: m.move_type == 'out_invoice'):
            payments |= move._get_reconciled_payments()
        partner = student._edu_billing_partner()
        blocked, message = student._edu_gate('reenrollment')
        pending_voids = set(
            self.env['edu.approval.request']
            .search([('move_id', 'in', open_moves.ids), ('state', '=', 'pending')])
            .move_id.ids
        )
        return {
            'student': {
                'id': student.id,
                'name': student.name,
                'matricula': student.matricula_number or '',
                'class': student.current_class_id._editor_label() if student.current_class_id else '',
                'status': dict(student._fields['student_status']._description_selection(self.env)).get(
                    student.student_status, ''
                ),
            },
            'balance': {
                'overdue': self._money(balance['overdue']) if balance['overdue'] > 0.005 else '',
                'open': self._money(balance['open']),
                'paid': self._money(balance['paid']),
                'since': balance['since'].strftime('%d/%m/%Y') if balance['since'] else '',
                'has_open': balance['open'] > 0.005,
            },
            'gate': {'blocked': blocked, 'message': message or '', 'exempt': student.edu_gate_exempt},
            'open': [
                {
                    'id': m.id,
                    'number': m.name,
                    'label': label(m),
                    'category': CATEGORY_LABELS.get(m.edu_category, ''),
                    'due': m.invoice_date_due.strftime('%d/%m/%Y') if m.invoice_date_due else '',
                    'late_days': (today - m.invoice_date_due).days
                    if m.invoice_date_due and m.invoice_date_due < today
                    else 0,
                    'total': self._money(m.amount_total),
                    'residual': self._money(m.amount_residual),
                    'partial': m.payment_state == 'partial',
                    'voidable': m.payment_state == 'not_paid',
                    'void_pending': m.id in pending_voids,
                }
                for m in open_moves
            ],
            'void_approval': self.env.company.edu_void_approval,
            'documents': [
                {
                    'id': m.id,
                    'model': 'account.move',
                    'kind': self.env._('Nota de crédito') if m.move_type == 'out_refund' else self.env._('Factura'),
                    'number': m.name,
                    'label': label(m),
                    'date': m.invoice_date.strftime('%d/%m/%Y') if m.invoice_date else '',
                    'amount': self._money(m.amount_total),
                    'state': self._move_state(m),
                }
                for m in moves
            ]
            + [
                {
                    'id': p.id,
                    'model': 'account.payment',
                    'kind': self.env._('Recibo'),
                    'number': p.l10n_ao_edi_document_no or p.name,
                    'label': p.journal_id.name,
                    'date': p.date.strftime('%d/%m/%Y'),
                    'amount': self._money(p.amount),
                    'state': self.env._('Emitido') if p.l10n_ao_edi_document_no else self.env._('Sem recibo AGT'),
                }
                for p in payments.sorted(lambda p: (p.date, p.id), reverse=True)
            ],
            'billing': {
                'name': partner.name,
                'vat': partner.vat or '',
                'address': ', '.join(p for p in [partner.street, partner.city] if p),
                'is_guardian': partner != student.partner_id,
            },
            'guardians': [
                {'name': link.guardian_id.name, 'phone': link.guardian_id.phone or '', 'primary': link.is_primary}
                for link in student.guardian_link_ids
            ],
        }

    def _move_state(self, move):
        if move.state == 'cancel':
            return self.env._('Anulada')
        if move.move_type == 'out_refund':
            return self.env._('Emitida')
        return {
            'paid': self.env._('Paga'),
            'in_payment': self.env._('Paga'),
            'partial': self.env._('Paga em parte'),
            'reversed': self.env._('Anulada por nota de crédito'),
        }.get(move.payment_state, self.env._('Por pagar'))

    @api.model
    def student_action(self, student_id, key, invoice_ids=None, res_id=False):
        """As acções da ficha: receber (as facturas escolhidas primeiro), cobrar um serviço e imprimir um documento."""
        self._check_access()
        student = self.env['edu.student'].browse(student_id)
        if key == 'pay':
            return {
                'type': 'ir.actions.client',
                'tag': 'edu_roles.treasury_pay',
                'name': self.env._('Registar um pagamento'),
                'context': {'student_id': student.id, 'invoice_ids': invoice_ids or []},
            }
        if key == 'receive':
            return {
                'type': 'ir.actions.act_window',
                'name': self.env._('Receber pagamento'),
                'res_model': 'edu.fee.payment',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'new',
                'context': {
                    'default_student_id': student.id,
                    'default_selected_invoice_ids': invoice_ids or [],
                    'default_amount': sum(self.env['account.move'].browse(invoice_ids or []).mapped('amount_residual')),
                },
            }
        if key == 'charge':
            return {
                'type': 'ir.actions.client',
                'tag': 'edu_roles.treasury_charge',
                'name': self.env._('Cobrar'),
                'context': {'student_id': student.id},
            }
        if key == 'print_move':
            return self.env.ref('account.account_invoices').preview_action(self.env['account.move'].browse(res_id))
        if key == 'print_payment':
            return self.env.ref('account.action_report_payment_receipt').preview_action(
                self.env['account.payment'].browse(res_id)
            )
        raise UserError(self.env._('Acção desconhecida.'))

    # Registar um pagamento: as facturas por pagar e os serviços da escola, num só acto

    def _pay_journal(self, method):
        kind = PAY_JOURNALS.get(method)
        if not kind:
            raise UserError(self.env._('Forma de pagamento desconhecida.'))
        return self.env['account.journal'].search(
            [('type', '=', kind), ('company_id', '=', self.env.company.id)], limit=1
        )

    def _student(self, student_id):
        student = self.env['edu.student'].browse(student_id).exists()
        if not student or student.company_id != self.env.company:
            raise UserError(self.env._('Aluno não encontrado.'))
        return student

    @api.model
    def payment_data(self, student_id):
        """«Registar um pagamento», como no secPed: as facturas por pagar (das mais antigas para as mais recentes), os
        serviços da escola que se cobram e pagam no mesmo acto, as formas de pagamento e as regras da caixa."""
        self._check_access()
        student = self._student(student_id)
        today = self._today()
        company = self.env.company
        invoices = student._edu_open_invoices().filtered(lambda m: m.company_id == company)
        catalog = self.catalog(student_id)
        return {
            'student': catalog['student'],
            'invoices': [
                {
                    'id': m.id,
                    'number': m.name,
                    'label': self._label(m),
                    'due': m.invoice_date_due.strftime('%d/%m/%Y') if m.invoice_date_due else '',
                    'due_key': fields.Date.to_string(m.invoice_date_due or today),
                    'late': bool(m.invoice_date_due and m.invoice_date_due < today),
                    'residual': m.amount_residual,
                }
                for m in invoices.sorted(lambda m: (m.invoice_date_due or today, m.id))
            ],
            'services': [item for group in catalog['groups'] for item in group['items']],
            'methods': [
                {'key': key, 'label': label, 'available': bool(self._pay_journal(key))}
                for key, label in [
                    ('cash', self.env._('Numerário')),
                    ('pos', self.env._('TPA (cartão)')),
                    ('deposit', self.env._('Depósito no banco')),
                ]
            ],
            'cash_open': bool(self.env['edu.cash.session']._current()),
            'cash_approval': company.edu_cash_approval,
            'cash_threshold': company.edu_cash_approval_threshold,
            'currency': catalog['currency'],
        }

    def _label(self, move):
        line = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')[:1]
        name = line.name or move.name or ''
        return name[:1].upper() + name[1:]

    @api.model
    def register_payment(self, student_id, values):
        """Regista o pagamento ao balcão: os serviços escolhidos saem numa factura (com a chave: repetir não cobra outra
        vez) e paga-se tudo no mesmo recibo. Em numerário acima do limite da escola, fica à espera de outra pessoa o
        aprovar. Tudo ou nada: se o pagamento falhar, a factura dos serviços também não fica. ``values``: allocations
        ([{id, amount}]), service_ids, method, reference, notes e key."""
        self._check_access()
        student = self._student(student_id)
        allocations = values.get('allocations') or []
        service_ids = values.get('service_ids') or []
        method = values.get('method')
        reference = values.get('reference') or ''
        notes = values.get('notes') or ''
        key = values.get('key') or False
        company = self.env.company
        journal = self._pay_journal(method)
        if not journal:
            raise UserError(self.env._('A escola não tem um diário para esta forma de pagamento.'))
        if method in ('pos', 'deposit') and not reference.strip():
            # Sem a referência do talão do TPA ou do depósito, o pagamento não se confere na conciliação bancária.
            raise UserError(self.env._('Indique o n.º da operação do talão do TPA ou do depósito.'))
        Move = self.env['account.move']
        # A mesma factura indicada duas vezes conta uma só vez (com a soma), antes das verificações do pagamento.
        merged = {}
        for row in allocations:
            move = Move.browse(row['id']).exists()
            amount = float(row['amount'] or 0)
            if move and amount > 0:
                merged[move] = merged.get(move, 0.0) + amount
        rows = list(merged.items())
        open_invoices = student._edu_open_invoices()
        for move, _amount in rows:
            if move.edu_student_id != student or move.move_type != 'out_invoice' or move.state != 'posted':
                raise UserError(self.env._('A factura %s não é deste aluno.', move.name))
            if move not in open_invoices:
                raise UserError(self.env._('A factura %s já está paga.', move.name))
        sale = Move
        if service_ids:
            sale = student._edu_charge_services([(service_id, 1) for service_id in service_ids], key=key)
            if sale.amount_residual > 0.005:
                rows.append((sale, sale.amount_residual))
        if not rows:
            raise UserError(self.env._('Escolha pelo menos uma factura ou um serviço.'))
        total = sum(amount for _move, amount in rows)
        memo = ' · '.join(part for part in [(reference or '').strip(), (notes or '').strip()] if part)
        if method == 'cash' and company.edu_cash_approval and total > company.edu_cash_approval_threshold:
            self.env['edu.fee.payment.request'].create(
                {
                    'student_id': student.id,
                    'company_id': company.id,
                    'submitted_by_id': self.env.uid,
                    'method': 'cash',
                    'amount': total,
                    'date': self._today(),
                    'reference': memo or False,
                    'journal_id': journal.id,
                    'invoice_ids': [fields.Command.set([move.id for move, _amount in rows])],
                }
            )
            return {'status': 'pending', 'total': self._money(total)}
        payments = student._edu_pay_invoices(rows, journal, memo=memo or None)
        return {
            'status': 'done',
            'total': self._money(total),
            'receipts': [p.l10n_ao_edi_document_no or p.name for p in payments],
            'payment_ids': payments.ids,
        }

    # Cobrar: o balcão dos serviços e produtos

    @api.model
    def catalog(self, student_id):
        """O catálogo do aluno para o balcão, em grupos como no secPed (serviços, cartão de estudante e produtos), com o
        valor a pagar e a taxa do IVA de cada item."""
        self._check_access()
        student = self.env['edu.student'].browse(student_id).exists()
        if not student or student.company_id != self.env.company:
            raise UserError(self.env._('Aluno não encontrado.'))
        groups = [
            ('service', self.env._('Serviços')),
            ('card', self.env._('Cartão de estudante')),
            ('other', self.env._('Produtos')),
        ]
        items = defaultdict(list)
        for line in student._edu_service_catalog():
            rate = line.tax_id.amount if line.tax_id.amount_type == 'percent' else 0.0
            # O preço sem IVA da factura e o IVA arredondado por excesso (AGT): o balcão soma como a factura.
            net = line._price_unit(line.amount)
            items[line.category if line.category in ('card', 'other') else 'service'].append(
                {
                    'id': line.id,
                    'name': line.name,
                    'net': net,
                    'price': self._money(net + float_round(net * rate / 100, precision_digits=2, rounding_method='UP')),
                    'rate': rate,
                    'card': line.category == 'card',
                }
            )
        return {
            'student': {
                'id': student.id,
                'name': student.name,
                'class': student.current_class_id._editor_label() if student.current_class_id else '',
                'enrolled': bool(student.current_enrollment_id),
            },
            'groups': [{'key': key, 'label': label, 'items': items[key]} for key, label in groups if items[key]],
            'currency': self.env.company.currency_id.symbol,
            'today': fields.Date.to_string(self._today()),
        }

    @api.model
    def charge(self, student_id, items, due_date=False, key=False):
        """Emite a factura do balcão (vários itens numa só) e devolve-a para receber logo."""
        self._check_access()
        student = self.env['edu.student'].browse(student_id).exists()
        if not student or student.company_id != self.env.company:
            raise UserError(self.env._('Aluno não encontrado.'))
        move = student._edu_charge_services(
            [(item['id'], item['quantity']) for item in items],
            due_date=fields.Date.to_date(due_date) if due_date else None,
            key=key,
        )
        return {'id': move.id, 'number': move.name, 'total': self._money(move.amount_total)}

    # Controlo interno: a caixa e as aprovações

    def _age(self, moment):
        days = (fields.Datetime.now() - moment).days if moment else 0
        return self.env._('hoje') if days < 1 else self.env._('há %s dia(s)', days)

    @api.model
    def controls_data(self):
        """A tua caixa e as aprovações pendentes: anular uma factura, conceder uma bolsa e o numerário acima do limite.
        Quem pediu não decide o próprio pedido (o servidor recusa e a página não oferece o botão)."""
        self._check_access()
        company = self.env.company
        session = self.env['edu.cash.session']._current()
        approvals = []
        for request in self.env['edu.approval.request'].search(
            [('company_id', '=', company.id), ('state', '=', 'pending')], order='create_date'
        ):
            approvals.append(
                {
                    'kind': 'void',
                    'id': request.id,
                    'title': self.env._('Anular uma factura'),
                    'what': self.env._(
                        '%(number)s de %(student)s, %(amount)s',
                        number=request.move_id.name,
                        student=request.student_id.name or '',
                        amount=self._money(request.amount),
                    ),
                    'reason': request.reason,
                    'by': request.requested_by_id.name,
                    'age': self._age(request.create_date),
                    'mine': request.requested_by_id == self.env.user,
                }
            )
        for scholarship in self.env['edu.scholarship'].search(
            [('company_id', '=', company.id), ('state', '=', 'draft')], order='create_date'
        ):
            discount = (
                self.env._('100%')
                if scholarship.scholarship_type == 'full'
                else (
                    f'{scholarship.discount_percent:g}%'
                    if scholarship.discount_percent
                    else self._money(scholarship.discount_amount)
                )
            )
            approvals.append(
                {
                    'kind': 'scholarship',
                    'id': scholarship.id,
                    'title': self.env._('Conceder uma bolsa'),
                    'what': self.env._(
                        '%(type)s a %(student)s: %(discount)s de desconto na propina, desde %(start)s',
                        type=scholarship.type_label,
                        student=scholarship.student_id.name,
                        discount=discount,
                        start=scholarship.date_from.strftime('%d/%m/%Y'),
                    ),
                    'reason': scholarship.note or '',
                    'by': scholarship.requested_by_id.name or '',
                    'age': self._age(scholarship.create_date),
                    'mine': company.edu_scholarship_approval and scholarship.requested_by_id == self.env.user,
                }
            )
        for request in self.env['edu.fee.payment.request'].search(
            [('company_id', '=', company.id), ('state', '=', 'pending'), ('method', '=', 'cash')], order='create_date'
        ):
            approvals.append(
                {
                    'kind': 'cash',
                    'id': request.id,
                    'title': self.env._('Numerário acima do limite'),
                    'what': self.env._(
                        '%(amount)s de %(student)s, recebido a %(date)s',
                        amount=self._money(request.amount),
                        student=request.student_id.name,
                        date=request.date.strftime('%d/%m/%Y'),
                    ),
                    'reason': request.reference or '',
                    'by': request.submitted_by_id.name,
                    'age': self._age(request.create_date),
                    'mine': request.submitted_by_id == self.env.user,
                }
            )
        return {
            'session': {'opened': fields.Datetime.context_timestamp(self, session.opened_at).strftime('%d/%m/%Y %H:%M')}
            if session
            else None,
            'approvals': approvals,
            'threshold': self._money(company.edu_cash_approval_threshold),
        }

    @api.model
    def open_cash(self):
        self._check_access()
        self.env['edu.cash.session']._open()
        return True

    @api.model
    def close_cash(self, declared, notes=''):
        """Fecha a caixa com o numerário contado (sem ver o esperado) e diz a diferença."""
        self._check_access()
        session = self.env['edu.cash.session']._current()
        if not session:
            raise UserError(self.env._('A tua caixa não está aberta.'))
        try:
            declared = round(float(declared), 2)
        except (TypeError, ValueError):
            raise UserError(self.env._('Indique o numerário contado.')) from None
        session.action_close(declared, notes)
        return {
            'expected': self._money(session.expected_amount),
            'declared': self._money(session.declared_amount),
            'difference': self._money(session.difference),
            'exact': session.currency_id.is_zero(session.difference),
            'short': session.difference < 0,
        }

    @api.model
    def decide(self, kind, res_id, approve, notes=''):
        """Aprovar ou recusar um pedido. Aprovar uma anulação emite a nota de crédito; aprovar o numerário regista o
        pagamento e emite o recibo; aprovar a bolsa aplica-a às propinas seguintes."""
        self._check_access()
        notes = (notes or '').strip()
        if kind == 'void':
            self.env['edu.approval.request'].browse(res_id)._decide(approve, notes)
        elif kind == 'scholarship':
            scholarship = self.env['edu.scholarship'].browse(res_id)
            if approve:
                scholarship.action_approve()
            else:
                if not notes:
                    raise UserError(self.env._('Escreva porque recusa o pedido.'))
                if scholarship.requested_by_id == self.env.user and scholarship.company_id.edu_scholarship_approval:
                    raise UserError(self.env._('Quem pede não pode decidir o próprio pedido.'))
                scholarship.action_cancel()
                scholarship.message_post(body=self.env._('Bolsa recusada: %s', notes))
        elif kind == 'cash':
            request = self.env['edu.fee.payment.request'].browse(res_id)
            if approve:
                request.action_confirm()
            else:
                if request.submitted_by_id == self.env.user:
                    raise UserError(self.env._('Quem recebeu o numerário não pode decidir o próprio pagamento.'))
                request.reject_reason = notes
                request.action_reject()
        else:
            raise UserError(self.env._('Pedido desconhecido.'))
        return True

    @api.model
    def differences(self, days=30):
        """Os fechos de caixa com diferença nos últimos dias, e quantos fechos houve (sem isso, «nenhuma diferença» não
        distinguia «todas certas» de «ninguém fechou a caixa»). A tesouraria vê as suas; a direcção, todas."""
        self._check_access()
        since = fields.Datetime.now() - timedelta(days=days)
        Session = self.env['edu.cash.session']
        closed = Session.search(
            [('company_id', '=', self.env.company.id), ('state', '=', 'closed'), ('closed_at', '>=', since)]
        )
        with_difference = closed.filtered(lambda s: not s.currency_id.is_zero(s.difference))

        def when(moment):
            return fields.Datetime.context_timestamp(self, moment).strftime('%d/%m/%Y %H:%M')

        return {
            'days': days,
            'closed': len(closed),
            'all': self.env.user.has_group('edu_core.group_edu_manager'),
            'rows': [
                {
                    'id': s.id,
                    'operator': s.operator_id.name,
                    'opened': when(s.opened_at),
                    'closed': when(s.closed_at),
                    'expected': self._money(s.expected_amount),
                    'declared': self._money(s.declared_amount),
                    'difference': self._money(s.difference),
                    'short': s.difference < 0,
                    'notes': s.notes or '',
                }
                for s in with_difference
            ],
        }

    # Controlos internos: as regras

    @api.model
    def rules(self):
        self._check_access()
        company = self.env.company
        return {
            'threshold': company.edu_cash_approval_threshold,
            'threshold_text': self._money(company.edu_cash_approval_threshold),
            'cash_approval': company.edu_cash_approval,
            'void_approval': company.edu_void_approval,
            'scholarship_approval': company.edu_scholarship_approval,
            'can_edit': self.env.user.has_group('edu_core.group_edu_manager'),
            'changed_by': company.edu_controls_changed_by_id.name or '',
            'changed_date': fields.Datetime.context_timestamp(self, company.edu_controls_changed_date).strftime(
                '%d/%m/%Y %H:%M'
            )
            if company.edu_controls_changed_date
            else '',
        }

    @api.model
    def save_rules(self, values):
        """Só a direcção altera as regras (quem opera a caixa não decide o que fica à espera de outra pessoa)."""
        self._check_access()
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise AccessError(self.env._('Só a direcção altera os controlos internos.'))
        try:
            threshold = max(0.0, round(float(values.get('threshold') or 0), 2))
        except (TypeError, ValueError):
            raise UserError(self.env._('O limite do numerário tem de ser um valor.')) from None
        self.env.company.sudo().write(
            {
                'edu_cash_approval_threshold': threshold,
                'edu_cash_approval': bool(values.get('cash_approval')),
                'edu_void_approval': bool(values.get('void_approval')),
                'edu_scholarship_approval': bool(values.get('scholarship_approval')),
                'edu_controls_changed_by_id': self.env.uid,
                'edu_controls_changed_date': fields.Datetime.now(),
            }
        )
        return self.rules()

    @api.model
    def request_void(self, move_id, reason):
        """«Anular» na ficha do aluno: emite a nota de crédito, ou fica pedida a outro utilizador."""
        self._check_access()
        move = self.env['account.move'].browse(move_id)
        if move.company_id != self.env.company:
            raise UserError(self.env._('Factura não encontrada.'))
        return move.action_edu_request_void(reason)
