from odoo import api, fields, models
from odoo.exceptions import UserError


class L10nAoAssetDisposal(models.TransientModel):
    _name = 'l10n_ao_asset.disposal'
    _description = 'Alienação ou abate de imobilizado'

    asset_id = fields.Many2one('l10n_ao_asset.asset', string='Bem', required=True)
    company_id = fields.Many2one(related='asset_id.company_id')
    currency_id = fields.Many2one(related='asset_id.currency_id')
    disposal_type = fields.Selection(
        [('sale', 'Alienação (venda)'), ('scrap', 'Abate')], string='Tipo', required=True, default='scrap'
    )
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    loss_account_id = fields.Many2one(
        'account.account',
        string='Conta do valor líquido',
        compute='_compute_loss_account',
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        check_company=True,
        help='Perdas em imobilizações (78.3): 78.3.1/78.3.2 na venda, 78.3.3 no abate. O preço de venda é facturado '
        'à parte, com o proveito em 68.3 (Ganhos em imobilizações).',
    )
    to_post_count = fields.Integer(string='Quotas a lançar', compute='_compute_preview')
    to_drop_count = fields.Integer(string='Quotas a anular', compute='_compute_preview')
    depreciated_amount = fields.Monetary(
        string='Amortizações acumuladas', compute='_compute_preview', currency_field='currency_id'
    )
    book_value = fields.Monetary(string='Valor líquido', compute='_compute_preview', currency_field='currency_id')

    @api.depends('disposal_type', 'asset_id')
    def _compute_loss_account(self):
        for wizard in self:
            asset = wizard.asset_id
            if not asset:
                wizard.loss_account_id = False
                continue
            if wizard.disposal_type == 'scrap':
                code = '78.3.3'
            else:
                code = '78.3.2' if (asset.category_id.account_asset_id.code or '').startswith('12') else '78.3.1'
            company = asset.company_id
            wizard.loss_account_id = (
                self.env['account.account']
                .with_company(company)
                .search([('code', '=', code), ('company_ids', 'in', company.id)], limit=1)
            )

    def _first_day(self):
        """Primeiro dia do período (mês ou exercício) da alienação: a partir daqui não há quota."""
        self.ensure_one()
        asset = self.asset_id
        if asset.method_period == 'year':
            return asset.company_id.compute_fiscalyear_dates(self.date)['date_from']
        return self.date.replace(day=1)

    @api.depends('asset_id', 'date')
    def _compute_preview(self):
        for wizard in self:
            asset = wizard.asset_id
            if not asset or not wizard.date:
                wizard.to_post_count = wizard.to_drop_count = 0
                wizard.depreciated_amount = wizard.book_value = 0.0
                continue
            first_day = wizard._first_day()
            pending = asset._pending_lines()
            to_post = pending.filtered(lambda line, day=first_day: line.date < day)
            wizard.to_post_count = len(to_post)
            wizard.to_drop_count = len(pending) - len(to_post)
            wizard.depreciated_amount = asset.depreciated_amount + sum(to_post.mapped('amount'))
            wizard.book_value = asset.original_value - wizard.depreciated_amount

    def action_confirm(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state not in ('open', 'close'):
            raise UserError(self.env._('Só se pode alienar ou abater um bem em uso.'))
        if self.date < asset.start_date:
            raise UserError(self.env._('A data é anterior à entrada em funcionamento.'))
        if self.date > fields.Date.context_today(self):
            raise UserError(self.env._('A alienação não pode ter data futura.'))
        asset._check_no_draft_moves()
        # CII, art. 29.º, n.º 4: há quota até ao mês (ou ano) anterior ao da alienação ou abate.
        first_day = self._first_day()
        posted_after = asset._posted_lines().filtered(lambda line: line.date >= first_day)
        if posted_after:
            raise UserError(
                self.env._(
                    'Já há quotas lançadas a partir de %(date)s (%(moves)s). Anule esses lançamentos antes de '
                    'alienar com esta data.',
                    date=first_day.strftime('%d/%m/%Y'),
                    moves=', '.join(posted_after.move_id.mapped('name')),
                )
            )
        pending = asset._pending_lines()
        pending.filtered(lambda line: line.date < first_day).sorted('date')._create_moves()
        pending.filtered(lambda line: line.date >= first_day).sudo().unlink()
        asset.invalidate_recordset(['depreciated_amount', 'book_value'])
        category = asset.category_id
        depreciated = asset.depreciated_amount
        net = asset.original_value - depreciated
        kind = dict(self._fields['disposal_type'].selection)[self.disposal_type]
        label = self.env._('%(type)s de %(asset)s', type=kind, asset=asset.name)
        lines = [(category.account_asset_id, -asset.original_value)]
        if not asset.currency_id.is_zero(depreciated):
            lines.append((category.account_depreciation_id, depreciated))
        if not asset.currency_id.is_zero(net):
            lines.append((self.loss_account_id, net))
        move = self.env['account.move'].create(
            {
                'move_type': 'entry',
                'journal_id': category.journal_id.id,
                'date': self.date,
                'ref': label,
                'l10n_ao_asset_id': asset.id,
                'line_ids': [
                    fields.Command.create(
                        {
                            'account_id': account.id,
                            'name': label,
                            'debit': max(amount, 0.0),
                            'credit': max(-amount, 0.0),
                        }
                    )
                    for account, amount in lines
                ],
            }
        )
        move.action_post()
        asset.write({'state': 'disposed', 'disposal_date': self.date, 'disposal_move_id': move.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': move.id, 'view_mode': 'form'}
