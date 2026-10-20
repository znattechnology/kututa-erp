from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import date_utils


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
        'l10n_ao_asset.rate', string='Taxa legal', compute='_compute_from_category', store=True, readonly=False
    )
    rate = fields.Float(
        string='Taxa anual (%)', digits=(5, 2), compute='_compute_from_category', store=True, readonly=False
    )
    method_period = fields.Selection(
        [('month', 'Duodécimos (mensal)'), ('year', 'Anual (ano completo)')],
        string='Regime',
        compute='_compute_from_category',
        store=True,
        readonly=False,
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
    salvage_value = fields.Monetary(string='Valor residual')
    opening_depreciation = fields.Monetary(
        string='Amortizações anteriores',
        help='Amortizações acumuladas já praticadas noutro sistema até à data indicada (arranque do Kututa).',
    )
    opening_date = fields.Date(string='Amortizado até')
    low_value = fields.Boolean(
        string='Bem de reduzido valor',
        compute='_compute_low_value',
        store=True,
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

    @api.depends('category_id')
    def _compute_from_category(self):
        for asset in self:
            category = asset.category_id
            asset.rate_id = category.rate_id
            asset.rate = category.rate
            asset.method_period = category.method_period or 'month'

    @api.depends('original_value', 'company_id')
    def _compute_low_value(self):
        for asset in self:
            limit = asset.company_id.l10n_ao_asset_low_value_limit
            asset.low_value = bool(asset.original_value) and asset.original_value <= limit

    @api.depends('original_value', 'opening_depreciation', 'line_ids.move_id.state', 'line_ids.amount')
    def _compute_amounts(self):
        for asset in self:
            posted = sum(asset.line_ids.filtered(lambda line: line.move_id.state == 'posted').mapped('amount'))
            asset.depreciated_amount = asset.opening_depreciation + posted
            asset.book_value = asset.original_value - asset.depreciated_amount

    @api.constrains('original_value', 'salvage_value', 'opening_depreciation', 'rate')
    def _check_values(self):
        for asset in self:
            if asset.original_value <= 0:
                raise ValidationError(self.env._('O valor de aquisição tem de ser positivo.'))
            if asset.salvage_value < 0 or asset.salvage_value >= asset.original_value:
                raise ValidationError(self.env._('O valor residual tem de ser inferior ao valor de aquisição.'))
            if asset.opening_depreciation > asset.original_value - asset.salvage_value:
                raise ValidationError(self.env._('As amortizações anteriores excedem o valor amortizável.'))
            if asset.rate < 0 or asset.rate > 100:
                raise ValidationError(self.env._('A taxa tem de estar entre 0 e 100%.'))

    @api.constrains('opening_depreciation', 'opening_date')
    def _check_opening(self):
        for asset in self:
            if asset.opening_depreciation and not asset.opening_date:
                raise ValidationError(self.env._('Indique até quando foram praticadas as amortizações anteriores.'))

    # ------------------------------------------------------------------
    # Plano de amortização
    # ------------------------------------------------------------------
    def _period_end(self, day):
        if self.method_period == 'year':
            return self.company_id.compute_fiscalyear_dates(day)['date_to']
        return date_utils.end_of(day, 'month')

    def _next_period_start(self, day):
        return self._period_end(day) + relativedelta(days=1)

    def _compute_board(self):
        """[(data, quota)] por quotas constantes; a última quota acerta o remanescente."""
        self.ensure_one()
        currency = self.currency_id
        remaining = self.original_value - self.salvage_value - self.opening_depreciation
        if currency.compare_amounts(remaining, 0) <= 0:
            return []
        start = self.start_date
        if self.opening_date and self.opening_date >= start:
            start = self._next_period_start(self.opening_date)
        if self.low_value:
            return [(self._period_end(start), remaining)]
        if self.rate <= 0:
            raise UserError(self.env._('Indique a taxa de amortização de «%s».', self.name))
        annual = (self.original_value - self.salvage_value) * self.rate / 100
        quota = currency.round(annual if self.method_period == 'year' else annual / 12)
        if currency.is_zero(quota):
            raise UserError(self.env._('A quota de amortização de «%s» é nula.', self.name))
        board = []
        day = start
        while currency.compare_amounts(remaining, 0) > 0:
            amount = min(quota, remaining)
            board.append((self._period_end(day), amount))
            remaining = currency.round(remaining - amount)
            day = self._next_period_start(day)
        return board

    def _generate_lines(self):
        for asset in self:
            asset.line_ids.filtered(lambda line: not line.move_id).unlink()
            depreciated = asset.opening_depreciation
            vals = []
            for day, amount in asset._compute_board():
                depreciated += amount
                vals.append({'asset_id': asset.id, 'date': day, 'amount': amount, 'depreciated': depreciated})
            self.env['l10n_ao_asset.depreciation.line'].create(vals)

    def action_compute_board(self):
        if any(asset.state != 'draft' for asset in self):
            raise UserError(self.env._('O plano só pode ser recalculado em rascunho.'))
        self._generate_lines()

    def action_confirm(self):
        for asset in self:
            if asset.state != 'draft':
                continue
            asset._generate_lines()
            asset.state = 'open'

    def action_reset_draft(self):
        for asset in self:
            if asset.line_ids.move_id.filtered(lambda move: move.state == 'posted') or asset.disposal_move_id:
                raise UserError(
                    self.env._('«%s» tem amortizações lançadas: anule os lançamentos primeiro.', asset.name)
                )
            asset.line_ids.unlink()
            asset.state = 'draft'

    def action_post_depreciation(self):
        """Lança as quotas vencidas até hoje."""
        self._post_depreciation(fields.Date.context_today(self))

    def _post_depreciation(self, up_to):
        lines = self.filtered(lambda asset: asset.state == 'open').line_ids.filtered(
            lambda line: not line.move_id and line.date <= up_to
        )
        lines.sorted('date')._create_moves()
        for asset in self.filtered(lambda a: a.state == 'open'):
            if asset.line_ids and all(line.move_id.state == 'posted' for line in asset.line_ids):
                asset.state = 'close'

    @api.model
    def _cron_post_depreciation(self):
        self.search([('state', '=', 'open')])._post_depreciation(fields.Date.context_today(self))

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

    # ------------------------------------------------------------------
    # Valores à data (mapa de reintegrações e amortizações)
    # ------------------------------------------------------------------
    def _depreciated_at(self, day, *, before=False):
        """Amortizações acumuladas lançadas até à data (inclusive, ou exclusive com before=True)."""
        self.ensure_one()
        amount = 0.0
        if self.opening_date and (self.opening_date < day if before else self.opening_date <= day):
            amount += self.opening_depreciation
        for line in self.line_ids:
            if line.move_id.state == 'posted' and (line.date < day if before else line.date <= day):
                amount += line.amount
        return amount

    def _fiscal_excess_ratio(self):
        """Parte da amortização não aceite fiscalmente (viaturas ligeiras acima do limite)."""
        self.ensure_one()
        limit = self.company_id.l10n_ao_asset_vehicle_limit
        if not self.category_id.vehicle_limit or not limit or self.original_value <= limit:
            return 0.0
        return (self.original_value - limit) / self.original_value


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
            line.move_id = move
            moves |= move
        moves.action_post()
        return moves
