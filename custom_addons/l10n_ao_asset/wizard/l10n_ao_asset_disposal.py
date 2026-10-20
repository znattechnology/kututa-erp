from odoo import api, fields, models
from odoo.exceptions import UserError


class L10nAoAssetDisposal(models.TransientModel):
    _name = 'l10n_ao_asset.disposal'
    _description = 'Alienação ou abate de imobilizado'

    asset_id = fields.Many2one('l10n_ao_asset.asset', required=True)
    company_id = fields.Many2one(related='asset_id.company_id')
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
        help='Perdas em imobilizações (78.3): 78.3.1/78.3.2 na venda, 78.3.3 no abate. O preço de venda é facturado '
        'à parte, com o proveito em 68.3 (Ganhos em imobilizações).',
    )

    @api.depends('disposal_type', 'asset_id')
    def _compute_loss_account(self):
        for wizard in self:
            if wizard.disposal_type == 'scrap':
                code = '78.3.3'
            else:
                code = '78.3.2' if wizard.asset_id.category_id.account_asset_id.code.startswith('12') else '78.3.1'
            company = wizard.asset_id.company_id
            wizard.loss_account_id = (
                self.env['account.account']
                .with_company(company)
                .search([('code', '=', code), ('company_ids', 'in', company.id)], limit=1)
            )

    def action_confirm(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state not in ('open', 'close'):
            raise UserError(self.env._('Só se pode alienar ou abater um bem em uso.'))
        if self.date < asset.start_date:
            raise UserError(self.env._('A data é anterior à entrada em funcionamento.'))
        # CII, art. 29.º, n.º 4: há quota até ao mês (ou ano) anterior ao da alienação ou abate.
        if asset.method_period == 'year':
            first_day = asset.company_id.compute_fiscalyear_dates(self.date)['date_from']
        else:
            first_day = self.date.replace(day=1)
        pending = asset.line_ids.filtered(lambda line: not line.move_id)
        pending.filtered(lambda line: line.date < first_day).sorted('date')._create_moves()
        pending.filtered(lambda line: line.date >= first_day).unlink()
        asset.invalidate_recordset(['depreciated_amount', 'book_value'])
        category = asset.category_id
        depreciated = asset.depreciated_amount
        net = asset.original_value - depreciated
        label = self.env._(
            '%(type)s de %(asset)s',
            type=dict(self._fields['disposal_type'].selection)[self.disposal_type],
            asset=asset.name,
        )
        lines = [
            fields.Command.create(
                {'account_id': category.account_asset_id.id, 'name': label, 'credit': asset.original_value}
            )
        ]
        if not asset.currency_id.is_zero(depreciated):
            lines.append(
                fields.Command.create(
                    {'account_id': category.account_depreciation_id.id, 'name': label, 'debit': depreciated}
                )
            )
        if not asset.currency_id.is_zero(net):
            lines.append(fields.Command.create({'account_id': self.loss_account_id.id, 'name': label, 'debit': net}))
        move = self.env['account.move'].create(
            {
                'move_type': 'entry',
                'journal_id': category.journal_id.id,
                'date': self.date,
                'ref': label,
                'l10n_ao_asset_id': asset.id,
                'line_ids': lines,
            }
        )
        move.action_post()
        asset.write({'state': 'disposed', 'disposal_date': self.date, 'disposal_move_id': move.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': move.id, 'view_mode': 'form'}
