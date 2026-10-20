import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, modules
from odoo.exceptions import UserError, ValidationError
from odoo.tools import date_utils

_logger = logging.getLogger(__name__)

# Campos que definem o plano: só se alteram em rascunho.
PLAN_FIELDS = {
    'category_id',
    'rate_id',
    'rate',
    'method_period',
    'start_date',
    'original_value',
    'salvage_value',
    'opening_depreciation',
    'opening_depreciation_prior',
    'opening_date',
    'low_value',
    'quantity',
    'company_id',
}


class L10nAoAsset(models.Model):
    _name = 'l10n_ao_asset.asset'
    _description = 'Ficha de imobilizado'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Designação', required=True, tracking=True)
    code = fields.Char(string='Referência', copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection(
        [
            ('draft', 'Rascunho'),
            ('open', 'Em uso'),
            ('close', 'Totalmente amortizado'),
            ('disposed', 'Alienado / abatido'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    category_id = fields.Many2one(
        'l10n_ao_asset.category', string='Categoria', required=True, check_company=True, tracking=True
    )
    rate_id = fields.Many2one(
        'l10n_ao_asset.rate',
        string='Taxa legal',
        compute='_compute_rate_id',
        store=True,
        precompute=True,
        readonly=False,
    )
    rate = fields.Float(
        string='Taxa anual (%)',
        digits=(5, 2),
        compute='_compute_rate',
        store=True,
        precompute=True,
        readonly=False,
        help='Taxa 0: bem não amortizável (terrenos, CII art. 31.º). A parte acima da taxa legal não é aceite '
        'como custo fiscal (art. 40.º).',
    )
    method_period = fields.Selection(
        [('month', 'Duodécimos (mensal)'), ('year', 'Anual (ano completo)')],
        string='Regime',
        compute='_compute_method_period',
        store=True,
        precompute=True,
        readonly=False,
        required=True,
    )
    partner_id = fields.Many2one('res.partner', string='Fornecedor')
    acquisition_date = fields.Date(string='Data de aquisição', required=True, default=fields.Date.context_today)
    start_date = fields.Date(
        string='Entrada em funcionamento',
        required=True,
        default=fields.Date.context_today,
        help='A amortização começa na entrada em funcionamento (DP n.º 207/15, art. 3.º).',
    )
    original_value = fields.Monetary(string='Valor de aquisição', required=True, tracking=True)
    quantity = fields.Float(
        string='Quantidade',
        default=1.0,
        digits='Product Unit',
        help='Número de unidades na ficha. O limite dos bens de reduzido valor aplica-se ao custo unitário.',
    )
    salvage_value = fields.Monetary(string='Valor residual')
    opening_depreciation = fields.Monetary(
        string='Amortizações anteriores',
        help='Amortizações acumuladas já praticadas noutro sistema até à data indicada (arranque do Kututa).',
    )
    opening_depreciation_prior = fields.Monetary(
        string='Das quais de exercícios anteriores',
        compute='_compute_opening_depreciation_prior',
        store=True,
        precompute=True,
        readonly=False,
        help='Parte das amortizações anteriores praticada até ao fim do exercício anterior ao da data '
        '«Amortizado até». Só interessa quando o arranque cai a meio do exercício.',
    )
    opening_date = fields.Date(string='Amortizado até')
    low_value = fields.Boolean(
        string='Bem de reduzido valor',
        compute='_compute_low_value',
        store=True,
        precompute=True,
        readonly=False,
        help='Custo unitário até ao limite da empresa (Kz 30 000): amortizado na totalidade no exercício de entrada '
        'em funcionamento (CII, art. 36.º).',
    )
    invoice_line_id = fields.Many2one('account.move.line', string='Linha da factura', readonly=True, copy=False)
    invoice_id = fields.Many2one(related='invoice_line_id.move_id', string='Factura')
    line_ids = fields.One2many('l10n_ao_asset.depreciation.line', 'asset_id', string='Plano de amortização', copy=False)
    depreciated_amount = fields.Monetary(string='Amortizações acumuladas', compute='_compute_amounts')
    book_value = fields.Monetary(string='Valor líquido', compute='_compute_amounts')
    disposal_date = fields.Date(string='Data da alienação / abate', readonly=True, copy=False)
    disposal_move_id = fields.Many2one('account.move', string='Lançamento de alienação', readonly=True, copy=False)
    move_ids = fields.One2many('account.move', 'l10n_ao_asset_id', string='Lançamentos')

    # ------------------------------------------------------------------
    # Computes e validações
    # ------------------------------------------------------------------
    @api.depends('category_id')
    def _compute_rate_id(self):
        for asset in self:
            asset.rate_id = asset.category_id.rate_id

    @api.depends('rate_id', 'category_id')
    def _compute_rate(self):
        for asset in self:
            if asset.rate_id:
                asset.rate = asset.rate_id.rate
            elif asset.category_id and not asset.rate:
                asset.rate = asset.category_id.rate

    @api.depends('category_id')
    def _compute_method_period(self):
        for asset in self:
            asset.method_period = asset.category_id.method_period or asset.method_period or 'month'

    @api.depends('original_value', 'quantity', 'company_id')
    def _compute_low_value(self):
        for asset in self:
            asset.low_value = asset._unit_value() <= asset.company_id.l10n_ao_asset_low_value_limit

    @api.depends('opening_depreciation', 'opening_date', 'company_id')
    def _compute_opening_depreciation_prior(self):
        for asset in self:
            if not asset.opening_date:
                asset.opening_depreciation_prior = 0.0
            elif asset.opening_date == asset.company_id.compute_fiscalyear_dates(asset.opening_date)['date_to']:
                asset.opening_depreciation_prior = asset.opening_depreciation
            else:
                asset.opening_depreciation_prior = min(
                    asset.opening_depreciation_prior or 0.0, asset.opening_depreciation
                )

    @api.depends('original_value', 'opening_depreciation', 'line_ids.move_id.state', 'line_ids.amount')
    def _compute_amounts(self):
        for asset in self:
            asset.depreciated_amount = asset.opening_depreciation + sum(asset._posted_lines().mapped('amount'))
            asset.book_value = asset.original_value - asset.depreciated_amount

    def _unit_value(self):
        self.ensure_one()
        if not self.original_value:
            return 0.0
        return self.original_value / (self.quantity if self.quantity > 0 else 1.0)

    @api.constrains('original_value', 'salvage_value', 'opening_depreciation', 'rate', 'quantity', 'low_value')
    def _check_values(self):
        for asset in self:
            if asset.original_value <= 0:
                raise ValidationError(self.env._('O valor de aquisição tem de ser positivo.'))
            if asset.quantity < 0:
                raise ValidationError(self.env._('A quantidade não pode ser negativa.'))
            if asset.salvage_value < 0 or asset.salvage_value >= asset.original_value:
                raise ValidationError(self.env._('O valor residual tem de ser inferior ao valor de aquisição.'))
            if (
                asset.opening_depreciation < 0
                or asset.opening_depreciation > asset.original_value - asset.salvage_value
            ):
                raise ValidationError(self.env._('As amortizações anteriores excedem o valor amortizável.'))
            if asset.rate < 0 or asset.rate > 100:
                raise ValidationError(self.env._('A taxa tem de estar entre 0 e 100%.'))
            if asset.low_value and asset._unit_value() > asset.company_id.l10n_ao_asset_low_value_limit:
                raise ValidationError(
                    self.env._(
                        'Um bem de reduzido valor tem de custar, por unidade, até %s (CII, art. 36.º).',
                        asset.company_id.l10n_ao_asset_low_value_limit,
                    )
                )

    @api.constrains('opening_depreciation', 'opening_depreciation_prior', 'opening_date', 'start_date')
    def _check_opening(self):
        for asset in self:
            if asset.opening_depreciation and not asset.opening_date:
                raise ValidationError(self.env._('Indique até quando foram praticadas as amortizações anteriores.'))
            if asset.opening_date and asset.opening_date < asset.start_date:
                raise ValidationError(
                    self.env._('A data «Amortizado até» não pode ser anterior à entrada em funcionamento.')
                )
            if asset.opening_depreciation_prior < 0 or asset.opening_depreciation_prior > asset.opening_depreciation:
                raise ValidationError(
                    self.env._('A parte de exercícios anteriores não pode exceder as amortizações anteriores.')
                )

    def write(self, vals):
        if PLAN_FIELDS & set(vals) and any(asset.state != 'draft' for asset in self):
            raise UserError(self.env._('Os dados do plano de amortização só se alteram em rascunho.'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Plano de amortização
    # ------------------------------------------------------------------
    def _periods_per_year(self):
        return 12 if self.method_period == 'month' else 1

    def _period_end(self, day):
        if self.method_period == 'year':
            return self.company_id.compute_fiscalyear_dates(day)['date_to']
        return date_utils.end_of(day, 'month')

    def _next_period_start(self, day):
        return self._period_end(day) + relativedelta(days=1)

    def _compute_board(self):
        """[(data, quota)] por quotas constantes.

        O número de períodos é o da vida útil (100 / taxa, arredondada ao ano) e a última quota acerta
        o remanescente, para a amortização terminar no fim da vida útil (CII, art. 29.º, n.º 3).
        """
        self.ensure_one()
        currency = self.currency_id
        remaining = currency.round(self.original_value - self.salvage_value - self.opening_depreciation)
        if currency.compare_amounts(remaining, 0) <= 0:
            return []
        start = self.start_date
        if self.opening_date and self.opening_date >= start:
            start = self._next_period_start(self.opening_date)
        if self.low_value:
            return [(self._period_end(start), remaining)]
        if self.rate <= 0:
            # Bem não amortizável (terrenos).
            return []
        per_year = self._periods_per_year()
        total_periods = max(round(100.0 / self.rate), 1) * per_year
        amortizable = self.original_value - self.salvage_value
        quota = currency.round(amortizable / total_periods)
        if currency.is_zero(quota):
            raise UserError(self.env._('A quota de amortização de «%s» é nula.', self.name))
        # Períodos já consumidos pelas amortizações anteriores.
        elapsed = int(self.opening_depreciation // quota) if quota else 0
        periods_left = max(total_periods - elapsed, 1)
        board = []
        day = start
        for index in range(periods_left):
            amount = remaining if index == periods_left - 1 else min(quota, remaining)
            if currency.compare_amounts(amount, 0) <= 0:
                break
            board.append((self._period_end(day), amount))
            remaining = currency.round(remaining - amount)
            day = self._next_period_start(day)
        return board

    def _lock_date(self):
        """Última data bloqueada para lançamentos gerais (bloqueio do exercício ou irreversível)."""
        self.ensure_one()
        company = self.company_id
        return max(filter(None, (company.fiscalyear_lock_date, company.hard_lock_date)), default=None)

    def _generate_lines(self):
        for asset in self:
            asset.line_ids.filtered(lambda line: not line.move_id).unlink()
            lock_date = asset._lock_date()
            depreciated = asset.opening_depreciation
            vals = []
            for day, amount in asset._compute_board():
                if lock_date and day <= lock_date:
                    raise UserError(
                        self.env._(
                            'A quota de %(date)s de «%(asset)s» cai num período bloqueado (até %(lock)s). '
                            'Registe as amortizações desse período em «Amortizações anteriores».',
                            date=day.strftime('%d/%m/%Y'),
                            asset=asset.name,
                            lock=lock_date.strftime('%d/%m/%Y'),
                        )
                    )
                depreciated += amount
                vals.append({'asset_id': asset.id, 'date': day, 'amount': amount, 'depreciated': depreciated})
            self.env['l10n_ao_asset.depreciation.line'].sudo().create(vals)

    def action_compute_board(self):
        if any(asset.state != 'draft' for asset in self):
            raise UserError(self.env._('O plano só pode ser recalculado em rascunho.'))
        self._generate_lines()

    def action_confirm(self):
        for asset in self:
            if asset.state != 'draft':
                continue
            asset._generate_lines()
            amortizable = asset.original_value - asset.salvage_value - asset.opening_depreciation
            asset.state = 'close' if not asset.line_ids and asset.rate > 0 and amortizable <= 0 else 'open'

    def _posted_lines(self):
        return self.line_ids.filtered(lambda line: line.move_id.state == 'posted')

    def _pending_lines(self):
        """Quotas por lançar: sem lançamento ou com o lançamento cancelado."""
        return self.line_ids.filtered(lambda line: not line.move_id or line.move_id.state == 'cancel')

    def _check_no_draft_moves(self):
        for asset in self:
            drafts = asset.move_ids.filtered(lambda move: move.state == 'draft')
            if drafts:
                raise UserError(
                    self.env._(
                        '«%(asset)s» tem lançamentos em rascunho (%(moves)s): lance-os ou cancele-os primeiro.',
                        asset=asset.name,
                        moves=', '.join(drafts.mapped('name')),
                    )
                )

    def action_reset_draft(self):
        for asset in self:
            if asset.state == 'disposed':
                raise UserError(self.env._('Anule primeiro a alienação de «%s».', asset.name))
            asset._check_no_draft_moves()
            if asset._posted_lines():
                raise UserError(
                    self.env._('«%s» tem amortizações lançadas: anule os lançamentos primeiro.', asset.name)
                )
            asset.line_ids.sudo().unlink()
            asset.state = 'draft'

    def action_post_depreciation(self):
        """Lança as quotas vencidas até hoje."""
        moves = self._post_depreciation(fields.Date.context_today(self))
        message = (
            self.env._('%s quota(s) lançada(s).', len(moves))
            if moves
            else self.env._('Não há quotas vencidas por lançar.')
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': message, 'type': 'success' if moves else 'info'},
        }

    def _post_depreciation(self, up_to):
        """Lança as quotas vencidas até ``up_to`` das fichas em uso; devolve os lançamentos criados."""
        moves = self.env['account.move']
        for asset in self.filtered(lambda a: a.state == 'open'):
            lines = asset._pending_lines().filtered(lambda line: line.date <= up_to)
            lock_date = asset._lock_date()
            locked = lines.filtered(lambda line, lock=lock_date: lock and line.date <= lock)
            if locked:
                raise UserError(
                    self.env._(
                        'A quota de %(date)s de «%(asset)s» cai num período bloqueado e não pode ser lançada.',
                        date=locked[0].date.strftime('%d/%m/%Y'),
                        asset=asset.name,
                    )
                )
            moves |= lines.sorted('date')._create_moves()
            if asset.line_ids and not asset._pending_lines():
                if all(line.move_id.state == 'posted' for line in asset.line_ids):
                    asset.state = 'close'
        return moves

    @api.model
    def _cron_post_depreciation(self):
        """Uma ficha por vez: um erro numa ficha não impede as outras e fica registado na ficha."""
        today = fields.Date.context_today(self)
        for asset in self.search([('state', '=', 'open')]):
            try:
                with self.env.cr.savepoint():
                    asset._post_depreciation(today)
            except UserError as error:
                _logger.warning('Imobilizado %s: %s', asset.display_name, error)
                asset.message_post(body=self.env._('O lançamento automático das quotas falhou: %s', error))
            if not modules.module.current_test:
                self.env['ir.cron']._commit_progress(1)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(asset.state != 'draft' for asset in self):
            raise UserError(self.env._('Só se podem eliminar fichas em rascunho.'))

    def action_open_moves(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Lançamentos'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('l10n_ao_asset_id', 'in', self.ids)],
        }

    def action_dispose(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Alienação / abate'),
            'res_model': 'l10n_ao_asset.disposal',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_asset_id': self.id},
        }

    def action_cancel_disposal(self):
        """Anula a alienação: cancela o lançamento e repõe o plano a partir da última quota lançada."""
        for asset in self:
            if asset.state != 'disposed':
                continue
            move = asset.disposal_move_id
            if move and move.state != 'cancel':
                if move.state == 'posted':
                    move.button_draft()
                move.button_cancel()
            asset.write({'state': 'open', 'disposal_date': False, 'disposal_move_id': False})
            # Repõe as quotas que a alienação apagou, a seguir às já lançadas.
            posted = asset._posted_lines()
            board = asset._compute_board()
            depreciated = asset.opening_depreciation + sum(posted.mapped('amount'))
            vals = []
            for day, amount in board[len(posted) :]:
                depreciated += amount
                vals.append({'asset_id': asset.id, 'date': day, 'amount': amount, 'depreciated': depreciated})
            self.env['l10n_ao_asset.depreciation.line'].sudo().create(vals)

    # ------------------------------------------------------------------
    # Valores à data (mapa de reintegrações e amortizações)
    # ------------------------------------------------------------------
    def _depreciated_at(self, day, *, before=False):
        """Amortizações acumuladas até à data (inclusive, ou exclusive com ``before=True``).

        As amortizações anteriores de exercícios passados contam no fim do exercício anterior à data
        «Amortizado até»; o resto conta nessa data.
        """
        self.ensure_one()

        def counts(when):
            return when < day if before else when <= day

        amount = 0.0
        if self.opening_date:
            prior_end = self.company_id.compute_fiscalyear_dates(self.opening_date)['date_from'] - timedelta(days=1)
            if counts(prior_end):
                amount += self.opening_depreciation_prior
            if counts(self.opening_date):
                amount += self.opening_depreciation - self.opening_depreciation_prior
        for line in self._posted_lines():
            if counts(line.date):
                amount += line.amount
        return amount

    def _fiscal_excess_ratio(self):
        """Parte da amortização não aceite fiscalmente: taxa acima da legal (CII art. 40.º) e, nas viaturas
        ligeiras, a parte do custo acima do limite (art. 40.º, al. e))."""
        self.ensure_one()
        accepted = 1.0
        if self.rate_id and self.rate > self.rate_id.rate > 0:
            accepted *= self.rate_id.rate / self.rate
        limit = self.company_id.l10n_ao_asset_vehicle_limit
        if self.category_id.vehicle_limit and limit and self.original_value > limit:
            accepted *= limit / self.original_value
        return 1.0 - accepted


class L10nAoAssetDepreciationLine(models.Model):
    _name = 'l10n_ao_asset.depreciation.line'
    _description = 'Quota de amortização'
    _order = 'date, id'

    asset_id = fields.Many2one('l10n_ao_asset.asset', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='asset_id.company_id', store=True)
    currency_id = fields.Many2one(related='asset_id.currency_id')
    date = fields.Date(string='Data', required=True)
    amount = fields.Monetary(string='Quota', required=True)
    depreciated = fields.Monetary(string='Acumulado')
    remaining = fields.Monetary(string='Valor líquido', compute='_compute_remaining')
    move_id = fields.Many2one('account.move', string='Lançamento', readonly=True, ondelete='set null', copy=False)
    move_state = fields.Selection(related='move_id.state', string='Estado do lançamento')

    @api.depends('depreciated', 'asset_id.original_value')
    def _compute_remaining(self):
        for line in self:
            line.remaining = line.asset_id.original_value - line.depreciated

    def _create_moves(self):
        moves = self.env['account.move']
        for line in self:
            asset = line.asset_id
            category = asset.category_id
            label = self.env._(
                'Amortização de %(asset)s (%(date)s)', asset=asset.name, date=line.date.strftime('%m/%Y')
            )
            move = self.env['account.move'].create(
                {
                    'move_type': 'entry',
                    'journal_id': category.journal_id.id,
                    'date': line.date,
                    'ref': label,
                    'l10n_ao_asset_id': asset.id,
                    'line_ids': [
                        fields.Command.create(
                            {'account_id': category.account_expense_id.id, 'name': label, 'debit': line.amount}
                        ),
                        fields.Command.create(
                            {'account_id': category.account_depreciation_id.id, 'name': label, 'credit': line.amount}
                        ),
                    ],
                }
            )
            line.sudo().move_id = move
            moves |= move
        moves.action_post()
        return moves
