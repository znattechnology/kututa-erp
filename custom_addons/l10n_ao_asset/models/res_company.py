from odoo import fields, models

# (nome, conta do imobilizado, amortizações acumuladas, amortizações do exercício, taxa legal, viatura ligeira)
DEFAULT_CATEGORIES = [
    ('Edifícios comerciais e administrativos', '11.2.1.2', '18.1.2', '73.1.2', 'G.1.3', False),
    ('Edifícios industriais', '11.2.1.1', '18.1.2', '73.1.2', 'G.1.1', False),
    ('Construções ligeiras', '11.2.2', '18.1.2', '73.1.2', 'G.1.6', False),
    ('Instalações de água, electricidade e refrigeração', '11.2.3', '18.1.2', '73.1.2', 'G.2.1', False),
    ('Máquinas e equipamentos', '11.3.1', '18.1.3', '73.1.3', 'G.3.17', False),
    ('Viaturas ligeiras', '11.4', '18.1.4', '73.1.4', 'G.4.1.2', True),
    ('Viaturas pesadas', '11.4', '18.1.4', '73.1.4', 'G.4.1.1', False),
    ('Equipamento informático', '11.5', '18.1.5', '73.1.5', 'G.3.1', False),
    ('Mobiliário de escritório', '11.5', '18.1.5', '73.1.5', 'G.5.5.2', False),
    ('Programas informáticos', '12.9', '18.2.9', '73.2.9', 'CII.39.4', False),
    ('Propriedade industrial e I&D', '12.3', '18.2.3', '73.2.3', 'N.1', False),
]
ASSET_JOURNAL_CODE = 'IMO'


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ao_asset_low_value_limit = fields.Monetary(
        string='Limite dos bens de reduzido valor',
        currency_field='currency_id',
        default=30000.0,
        help='CII, art. 36.º: bens até este custo unitário podem ser amortizados no exercício de entrada em '
        'funcionamento.',
    )
    l10n_ao_asset_vehicle_limit = fields.Monetary(
        string='Limite fiscal das viaturas ligeiras',
        currency_field='currency_id',
        default=20000000.0,
        help='CII, art. 40.º, al. e) (Lei n.º 26/20): a amortização acima deste custo não é aceite como custo fiscal.',
    )

    def _l10n_ao_asset_create_default_categories(self):
        for company in self:
            category_model = self.env['l10n_ao_asset.category'].with_company(company)
            if category_model.search_count([('company_id', '=', company.id)], limit=1):
                continue
            accounts = {
                account.code: account
                for account in self.env['account.account']
                .with_company(company)
                .search([('company_ids', 'in', company.id), ('code', '=like', '1%')])
            }
            accounts.update(
                {
                    account.code: account
                    for account in self.env['account.account']
                    .with_company(company)
                    .search([('company_ids', 'in', company.id), ('code', '=like', '73%')])
                }
            )
            journal = self.env['account.journal'].search(
                [('company_id', '=', company.id), ('code', '=', ASSET_JOURNAL_CODE), ('type', '=', 'general')],
                limit=1,
            ) or self.env['account.journal'].create(
                {
                    'name': 'Operações de imobilizado',
                    'code': ASSET_JOURNAL_CODE,
                    'type': 'general',
                    'company_id': company.id,
                }
            )
            vals = []
            for sequence, (name, asset, depreciation, expense, rate_code, vehicle) in enumerate(DEFAULT_CATEGORIES):
                if not all(code in accounts for code in (asset, depreciation, expense)):
                    continue
                rate = self.env['l10n_ao_asset.rate'].search([('code', '=', rate_code)], limit=1)
                vals.append(
                    {
                        'name': name,
                        'sequence': sequence,
                        'company_id': company.id,
                        'rate_id': rate.id,
                        'rate': rate.rate,
                        'account_asset_id': accounts[asset].id,
                        'account_depreciation_id': accounts[depreciation].id,
                        'account_expense_id': accounts[expense].id,
                        'journal_id': journal.id,
                        'vehicle_limit': vehicle,
                    }
                )
            category_model.create(vals)
