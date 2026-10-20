from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ao_asset_id = fields.Many2one(
        'l10n_ao_asset.asset', string='Ficha de imobilizado', readonly=True, copy=False, index='btree_not_null'
    )
    l10n_ao_asset_count = fields.Integer(compute='_compute_l10n_ao_asset_count')

    def _compute_l10n_ao_asset_count(self):
        for move in self:
            move.l10n_ao_asset_count = len(move.line_ids.l10n_ao_asset_ids)

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted.filtered(lambda move: move.move_type == 'in_invoice')._l10n_ao_asset_create_from_bills()
        return posted

    def _l10n_ao_asset_create_from_bills(self):
        """Cria uma ficha de imobilizado em rascunho por linha lançada na conta de uma categoria."""
        vals = []
        for move in self:
            categories = self.env['l10n_ao_asset.category'].search(
                [('company_id', '=', move.company_id.id), ('auto_create', '=', True)]
            )
            by_account = {}
            for category in categories:
                by_account.setdefault(category.account_asset_id, category)
            for line in move.invoice_line_ids:
                category = by_account.get(line.account_id)
                if not category or line.l10n_ao_asset_ids or line.company_currency_id.is_zero(line.balance):
                    continue
                vals.append(
                    {
                        'name': line.name or line.product_id.display_name or move.name,
                        'company_id': move.company_id.id,
                        'category_id': category.id,
                        'partner_id': move.partner_id.id,
                        'acquisition_date': move.invoice_date or move.date,
                        'start_date': move.invoice_date or move.date,
                        'original_value': line.balance,
                        'invoice_line_id': line.id,
                    }
                )
        if vals:
            self.env['l10n_ao_asset.asset'].create(vals)

    def action_open_l10n_ao_assets(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Imobilizado'),
            'res_model': 'l10n_ao_asset.asset',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.line_ids.l10n_ao_asset_ids.ids)],
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_ao_asset_ids = fields.One2many('l10n_ao_asset.asset', 'invoice_line_id', string='Fichas de imobilizado')
