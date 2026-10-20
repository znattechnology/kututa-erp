from collections import defaultdict
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.l10n_ao_reports_engine import (
    CLOSING_TRANSFERS,
    NET_RESULT_TRANSFER,
    RESULT_TRANSFERS,
    TAX_RESULT_ACCOUNTS,
    TAX_RESULT_DEFAULT,
    TAX_TRANSFER,
)

CLOSING_JOURNAL_CODE = 'APR'
RETAINED_EARNINGS_ACCOUNT = '81.1.1'


class L10nAoReportsClosing(models.TransientModel):
    _name = 'l10n_ao_reports.closing'
    _description = 'Encerramento do exercício (PGC)'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company.root_id,
        domain=lambda self: [('id', 'in', self.env.companies.ids), ('parent_id', '=', False)],
        help='O encerramento é da entidade (empresa-mãe) e inclui as sucursais.',
    )
    operation = fields.Selection(
        [
            ('close', 'Apuramento de resultados (classes 6 e 7 → 82 a 88)'),
            ('transfer', 'Transferência do resultado líquido para resultados transitados (88 → 81)'),
        ],
        string='Operação',
        required=True,
        default='close',
    )
    year = fields.Integer(
        string='Exercício',
        required=True,
        default=lambda self: self._default_year(),
        help='Ano em que termina o exercício.',
    )
    date_from = fields.Date(compute='_compute_dates')
    date_to = fields.Date(compute='_compute_dates')
    date = fields.Date(
        string='Data do lançamento',
        compute='_compute_date',
        store=True,
        readonly=False,
        help='Apuramento: último dia do exercício. Transferência: normalmente o primeiro dia do exercício seguinte, '
        'depois da aprovação das contas.',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diário',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help='Por omissão, o diário «Apuramento de resultados» (APR), criado se não existir.',
    )
    result_amount = fields.Monetary(
        string='Resultado líquido', compute='_compute_result_amount', currency_field='currency_id'
    )
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.model
    def _default_year(self):
        company = self.env.company.root_id
        previous_end = company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_from'] - timedelta(
            days=1
        )
        return previous_end.year

    @api.depends('company_id', 'year')
    def _compute_dates(self):
        for wizard in self:
            if not wizard.year:
                wizard.date_from = wizard.date_to = False
                continue
            company = wizard.company_id
            # O último dia do exercício pode não existir no ano (29/02): usa-se o dia 1 do mês.
            dates = company.compute_fiscalyear_dates(date(wizard.year, int(company.fiscalyear_last_month), 1))
            wizard.date_from, wizard.date_to = dates['date_from'], dates['date_to']

    @api.depends('operation', 'date_to')
    def _compute_date(self):
        for wizard in self:
            if not wizard.date_to:
                wizard.date = False
            elif wizard.operation == 'transfer':
                wizard.date = wizard.date_to + timedelta(days=1)
            else:
                wizard.date = wizard.date_to

    @api.depends('company_id', 'date_from', 'date_to')
    def _compute_result_amount(self):
        engine = self.env['l10n_ao_reports.engine']
        for wizard in self:
            if not wizard.date_to:
                wizard.result_amount = 0.0
                continue
            values = engine._income_statement_values(wizard.company_id, wizard.date_from, wizard.date_to)
            wizard.result_amount = sum(values.values())

    # ------------------------------------------------------------------
    def _account(self, code):
        account = (
            self.env['account.account']
            .with_company(self.company_id)
            .search([('code', '=', code), ('company_ids', 'in', self.company_id.id)], limit=1)
        )
        if not account:
            raise UserError(
                self.env._(
                    'Falta a conta %(code)s do PGC na empresa %(company)s.', code=code, company=self.company_id.name
                )
            )
        return account

    def _closing_journal(self):
        if self.journal_id:
            return self.journal_id
        journal_model = self.env['account.journal']
        journal = journal_model.search(
            [('company_id', '=', self.company_id.id), ('code', '=', CLOSING_JOURNAL_CODE), ('type', '=', 'general')],
            limit=1,
        )
        return journal or journal_model.create(
            {
                'name': 'Apuramento de resultados',
                'code': CLOSING_JOURNAL_CODE,
                'type': 'general',
                'company_id': self.company_id.id,
            }
        )

    def _existing(self, operation, year):
        """Lançamentos de encerramento em vigor (nem cancelados nem estornados)."""
        moves = self.env['account.move'].search(
            [
                ('company_id', '=', self.company_id.id),
                ('l10n_ao_closing_type', '=', operation),
                ('l10n_ao_closing_year', '=', year),
                ('state', '!=', 'cancel'),
            ]
        )
        return moves.filtered(lambda move: not move.reversal_move_ids.filtered(lambda r: r.state == 'posted'))

    def _group_balances(self, date_from, date_to):
        """Saldo por grupo de 2 dígitos e por conta das classes 6, 7 e 82 a 88 no intervalo."""
        engine = self.env['l10n_ao_reports.engine']
        groups = defaultdict(float)
        accounts = defaultdict(float)
        for (account, _p), (_d, _c, balance) in engine._account_totals(
            self.company_id, date_from=date_from, date_to=date_to, posted_only=True
        ).items():
            code = account.code
            if code[:1] in '67' or code[:2] in ('82', '83', '84', '85', '86', '87', '88'):
                groups[code[:2]] += balance
                accounts[code] += balance
        return groups, accounts

    def _check_access(self):
        if self.company_id not in self.env.companies:
            raise UserError(self.env._('Não tem acesso à empresa %s.', self.company_id.name))
        if self.company_id.parent_id:
            raise UserError(self.env._('Escolha a empresa-mãe: o encerramento inclui as sucursais.'))

    def _check_lock_dates(self):
        locks = self.company_id._get_lock_date_violations(self.date, sale=False, purchase=False, tax=False)
        if locks:
            raise UserError(
                self.env._(
                    'A data %(date)s está num período bloqueado (%(locks)s): o lançamento seria datado noutro '
                    'exercício. Altere as datas de bloqueio da empresa primeiro.',
                    date=self.date.strftime('%d/%m/%Y'),
                    locks=self.company_id._format_lock_dates(locks),
                )
            )

    def _check_close(self):
        currency = self.company_id.currency_id
        # O apuramento é sempre no último dia do exercício: os saldos cobrem o exercício inteiro.
        self.date = self.date_to
        self._check_lock_dates()
        previous, _accounts = self._group_balances(None, self.date_from - timedelta(days=1))
        pending = sorted(g for g, balance in previous.items() if g[:1] in '67' and not currency.is_zero(balance))
        if pending:
            raise UserError(
                self.env._(
                    'Há proveitos e custos de exercícios anteriores por apurar (contas %s). '
                    'Faça primeiro o apuramento do exercício anterior.',
                    ', '.join(pending),
                )
            )
        drafts = (
            self.env['account.move']
            .sudo()
            .search_count(
                [
                    ('company_id', 'child_of', self.company_id.id),
                    ('state', '=', 'draft'),
                    ('date', '>=', self.date_from),
                    ('date', '<=', self.date_to),
                ]
            )
        )
        if drafts:
            raise UserError(
                self.env._(
                    'Há %s lançamentos em rascunho no exercício. Lance-os ou elimine-os antes do apuramento.', drafts
                )
            )

    def _close_lines(self):
        """Linhas do apuramento: classes 6 e 7 → 82 a 86 (pelas x.9), 82 a 87 → 88."""
        currency = self.company_id.currency_id
        groups, accounts = self._group_balances(self.date_from, self.date_to)
        unknown = sorted(
            g for g, b in groups.items() if g[:1] in '67' and g not in CLOSING_TRANSFERS and not currency.is_zero(b)
        )
        if unknown:
            raise UserError(self.env._('Contas sem regra de apuramento no PGC: %s.', ', '.join(unknown)))
        lines = defaultdict(float)  # código -> saldo a lançar
        results = defaultdict(float, {g: groups.get(g, 0.0) for g in RESULT_TRANSFERS})
        for group, (transfer_code, result_code) in CLOSING_TRANSFERS.items():
            amount = groups.get(group, 0.0)
            if currency.is_zero(amount):
                continue
            lines[transfer_code] -= amount
            lines[result_code] += amount
            results[result_code[:2]] += amount
        for group, (transfer_code, net_code) in RESULT_TRANSFERS.items():
            amount = results[group]
            if currency.is_zero(amount):
                continue
            lines[transfer_code] -= amount
            lines[net_code] += amount
        tax_total = groups.get('87', 0.0)
        if not currency.is_zero(tax_total):
            lines[TAX_TRANSFER] -= tax_total
            special = {code: 0.0 for code in TAX_RESULT_ACCOUNTS}
            for code, balance in accounts.items():
                for prefix in special:
                    if code.startswith(prefix):
                        special[prefix] += balance
            for prefix, net_code in TAX_RESULT_ACCOUNTS.items():
                lines[net_code] += special[prefix]
            lines[TAX_RESULT_DEFAULT] += tax_total - sum(special.values())
        return {code: amount for code, amount in lines.items() if not currency.is_zero(amount)}

    def _create_move(self, operation, lines, ref):
        move = self.env['account.move'].create(
            {
                'move_type': 'entry',
                'journal_id': self._closing_journal().id,
                'date': self.date,
                'ref': ref,
                'l10n_ao_closing_type': operation,
                'l10n_ao_closing_year': self.year,
                'line_ids': [
                    fields.Command.create(
                        {
                            'account_id': self._account(code).id,
                            'name': ref,
                            'debit': amount if amount > 0 else 0.0,
                            'credit': -amount if amount < 0 else 0.0,
                        }
                    )
                    for code, amount in sorted(lines.items())
                ],
            }
        )
        move.action_post()
        if move.date != self.date:
            raise UserError(self.env._('O lançamento ficou com a data %s, fora do exercício.', move.date))
        return move

    def action_confirm(self):
        self.ensure_one()
        self._check_access()
        if self.operation == 'close':
            self._check_close()
            lines = self._close_lines()
            existing = self._existing('close', self.year)
            if not lines:
                if existing:
                    raise UserError(self.env._('O exercício %s já foi apurado e não há nada a apurar.', self.year))
                raise UserError(self.env._('Não há proveitos nem custos lançados no exercício %s.', self.year))
            # Um segundo apuramento no mesmo exercício só leva o que foi lançado depois do primeiro.
            label = 'Apuramento complementar' if existing else 'Apuramento'
            move = self._create_move('close', lines, f'{label} de resultados do exercício {self.year}')
        else:
            move = self._transfer()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }

    def _transfer(self):
        if not self._existing('close', self.year):
            raise UserError(self.env._('Faça primeiro o apuramento de resultados do exercício %s.', self.year))
        if self._existing('transfer', self.year):
            raise UserError(self.env._('O resultado do exercício %s já foi transferido.', self.year))
        if self.date <= self.date_to:
            raise UserError(self.env._('A transferência faz-se no exercício seguinte, depois da aprovação das contas.'))
        self._check_lock_dates()
        # O resultado do exercício é o que os apuramentos desse exercício deixaram na 88.
        closing_lines = self._existing('close', self.year).line_ids.filtered(
            lambda line: line.account_id.code.startswith('88')
        )
        net = sum(closing_lines.mapped('balance'))
        if self.company_id.currency_id.is_zero(net):
            raise UserError(self.env._('O resultado líquido (88) do exercício %s é nulo.', self.year))
        return self._create_move(
            'transfer',
            {NET_RESULT_TRANSFER: -net, RETAINED_EARNINGS_ACCOUNT: net},
            f'Transferência do resultado líquido do exercício {self.year} para resultados transitados',
        )
