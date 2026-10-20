from collections import defaultdict

from odoo import fields, models
from odoo.exceptions import UserError

NON_DEDUCTIBLE_TYPES = ('non_deductible_product', 'non_deductible_tax')


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

    def button_draft(self):
        self._l10n_ao_asset_drop_draft_assets()
        return super().button_draft()

    def button_cancel(self):
        self._l10n_ao_asset_drop_draft_assets()
        return super().button_cancel()

    def _l10n_ao_asset_drop_draft_assets(self):
        """Ao reabrir ou cancelar a factura, as fichas em rascunho criadas por ela são apagadas (voltam a ser
        criadas ao lançar de novo, com os valores actuais). As fichas já confirmadas ficam."""
        assets = self.line_ids.l10n_ao_asset_ids
        confirmed = assets.filtered(lambda asset: asset.state != 'draft')
        if confirmed and self.filtered(lambda move: move.state == 'posted'):
            raise UserError(
                self.env._(
                    'A factura tem fichas de imobilizado confirmadas (%s). Volte-as a rascunho primeiro.',
                    ', '.join(confirmed.mapped('name')),
                )
            )
        (assets - confirmed).sudo().unlink()

    def _l10n_ao_asset_categories_by_account(self, company):
        """{conta: categorias com criação automática} da empresa (ou das empresas-mãe, nas sucursais)."""
        categories = self.env['l10n_ao_asset.category'].search(
            [('company_id', 'in', company.parent_ids.ids), ('auto_create', '=', True)], order='sequence, id'
        )
        by_account = defaultdict(list)
        for category in categories:
            by_account[category.account_asset_id].append(category)
        return by_account

    def _l10n_ao_asset_create_from_bills(self):
        """Cria uma ficha de imobilizado em rascunho por linha lançada na conta de uma categoria.

        O IVA não dedutível lançado na mesma conta junta-se ao valor da ficha. As linhas negativas
        (descontos) abatem às positivas da mesma conta, proporcionalmente.
        """
        Asset = self.env['l10n_ao_asset.asset'].sudo()
        vals = []
        for move in self:
            by_account = self._l10n_ao_asset_categories_by_account(move.company_id)
            if not by_account:
                continue
            product_lines = move.invoice_line_ids.filtered(
                lambda line, accounts=by_account: line.account_id in accounts
            )
            extra_by_account = defaultdict(float)
            for line in move.line_ids.filtered(lambda line: line.display_type in NON_DEDUCTIBLE_TYPES):
                extra_by_account[line.account_id] += line.balance
            for account in product_lines.account_id:
                lines = product_lines.filtered(lambda line, a=account: line.account_id == a)
                positive = lines.filtered(lambda line: line.balance > 0)
                total_positive = sum(positive.mapped('balance'))
                if not positive or move.company_currency_id.is_zero(total_positive):
                    continue
                adjustment = sum(lines.mapped('balance')) - total_positive + extra_by_account.get(account, 0.0)
                categories = by_account[account]
                for line in positive:
                    if line.l10n_ao_asset_ids:
                        continue
                    product_category = line.product_id.product_tmpl_id.l10n_ao_asset_category_id
                    category = product_category if product_category in categories else categories[0]
                    value = line.balance * (1 + adjustment / total_positive)
                    vals.append(
                        {
                            'name': line.name or line.product_id.display_name or move.name,
                            'company_id': move.company_id.id,
                            'category_id': category.id,
                            'partner_id': move.commercial_partner_id.id,
                            'acquisition_date': move.invoice_date or move.date,
                            'start_date': move.invoice_date or move.date,
                            'original_value': move.company_currency_id.round(value),
                            'quantity': line.quantity if line.quantity > 0 else 1.0,
                            'invoice_line_id': line.id,
                            '_ambiguous': len(categories) > 1 and category != product_category,
                        }
                    )
        ambiguous = [v.pop('_ambiguous') for v in vals]
        assets = Asset.create(vals) if vals else Asset
        for asset, flag in zip(assets, ambiguous, strict=True):
            if flag:
                asset.message_post(
                    body=self.env._(
                        'A conta %s é partilhada por várias categorias de imobilizado: confirme a categoria '
                        'antes de confirmar a ficha.',
                        asset.category_id.account_asset_id.code,
                    )
                )

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
