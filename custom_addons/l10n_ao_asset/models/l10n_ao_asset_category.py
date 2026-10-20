from odoo import api, fields, models


class L10nAoAssetRate(models.Model):
    _name = 'l10n_ao_asset.rate'
    _description = 'Taxa legal de reintegração e amortização (DP n.º 207/15)'
    _order = 'id'
    _rec_names_search = ['code', 'name', 'group']

    code = fields.Char(string='Código', required=True, index=True)
    group = fields.Char(string='Secção / grupo')
    name = fields.Char(string='Designação', required=True)
    rate = fields.Float(string='Taxa (%)', digits=(5, 2), required=True)
    life_years = fields.Float(string='Vida útil (anos)', digits=(5, 2))
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'O código da taxa tem de ser único.')

    @api.depends('code', 'name', 'rate')
    def _compute_display_name(self):
        for rate in self:
            rate.display_name = f'{rate.code} {rate.name} ({rate.rate:g}%)'


class L10nAoAssetCategory(models.Model):
    _name = 'l10n_ao_asset.category'
    _description = 'Categoria de imobilizado'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(string='Categoria', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    rate_id = fields.Many2one('l10n_ao_asset.rate', string='Taxa legal', help='Tabela anexa ao DP n.º 207/15.')
    rate = fields.Float(
        string='Taxa anual (%)',
        digits=(5, 2),
        compute='_compute_rate',
        store=True,
        readonly=False,
        required=True,
        help='Por omissão, a taxa máxima legal. Uma taxa superior não é aceite como custo fiscal (CII, art. 40.º).',
    )
    method_period = fields.Selection(
        [('month', 'Duodécimos (mensal)'), ('year', 'Anual (ano completo)')],
        string='Regime',
        default='month',
        required=True,
        help='Duodécimos: quota mensal a partir do mês de entrada em funcionamento (CII, art. 29.º, n.º 2). '
        'Anual: quota anual completa a partir do ano de entrada em funcionamento (art. 29.º, n.º 1).',
    )
    account_asset_id = fields.Many2one(
        'account.account',
        string='Conta do imobilizado',
        required=True,
        check_company=True,
        help='Classe 1 (11.x, 12.x). As facturas de fornecedor lançadas nesta conta criam fichas de imobilizado.',
    )
    account_depreciation_id = fields.Many2one(
        'account.account', string='Amortizações acumuladas', required=True, check_company=True, help='Conta 18.x.'
    )
    account_expense_id = fields.Many2one(
        'account.account', string='Amortizações do exercício', required=True, check_company=True, help='Conta 73.x.'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diário',
        required=True,
        check_company=True,
        domain="[('type', '=', 'general')]",
    )
    auto_create = fields.Boolean(
        string='Criar fichas a partir das facturas',
        default=True,
        help='Ao lançar uma factura de fornecedor na conta do imobilizado, é criada uma ficha em rascunho.',
    )
    vehicle_limit = fields.Boolean(
        string='Viatura ligeira de passageiros ou mista',
        help='A amortização da parte do custo acima do limite da empresa (Kz 20 000 000) não é aceite como custo '
        'fiscal (CII, art. 40.º, al. e)).',
    )

    @api.depends('rate_id')
    def _compute_rate(self):
        for category in self:
            if category.rate_id:
                category.rate = category.rate_id.rate
            elif not category.rate:
                category.rate = 0.0
