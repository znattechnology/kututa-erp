from odoo import Command
from odoo.addons.l10n_ao_edi.tests.common import TODAY, L10nAoEdiCommon
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


class L10nAoEdiPosCommon(L10nAoEdiCommon, TestPoSCommon):
    """POS de uma empresa angolana com facturação electrónica e séries TV/NC activas."""

    _test_user_groups = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Series = cls.env['l10n_ao_edi.series']
        cls.series['TV'] = Series.create(
            {'document_type': 'TV', 'year': TODAY.year, 'code': f'TV{TODAY.year % 100}S1', 'state': 'active'}
        )
        cls.tv_contingency_series = Series.create(
            {
                'document_type': 'TV',
                'year': TODAY.year,
                'code': f'TV{TODAY.year % 100}C1',
                'contingency': True,
                'state': 'active',
            }
        )
        cls.config = cls.basic_config
        cls.pos_product = cls.env['product.product'].create(
            {
                'name': 'Sumo natural',
                'default_code': 'SUMO',
                'type': 'consu',
                'lst_price': 1000.0,
                'available_in_pos': True,
                'taxes_id': [Command.set(cls.vat14.ids)],
                'property_account_income_id': cls.company_data['default_account_revenue'].id,
            }
        )

    def sync_order(self, lines, **kwargs):
        """Venda vinda do POS (sync_from_ui). ``lines``: [(produto, qtd)] ou dicts com campos extra da linha."""
        order_args = kwargs.pop('order_args', {})
        data = self.create_ui_order_data(lines, pos_order_ui_args=order_args, **kwargs)
        self.env['pos.order'].sync_from_ui([data])
        # A resposta também inclui a venda devolvida: procura-se pelo uuid.
        return self.env['pos.order'].search([('uuid', '=', data['uuid'])])

    def sync_refund(self, order, reason='Devolução de artigos', **kwargs):
        line = order.lines[0]
        return self.sync_order(
            [{'product': line.product_id, 'quantity': -line.qty, 'refunded_orderline_id': line.id}],
            order_args={'l10n_ao_edi_reason': reason, 'is_refund': True},
            **kwargs,
        )

    def agt_accept_all(self):
        """Respostas da AGT: recebe tudo e valida todos os documentos do pedido."""
        Document = self.env['l10n_ao_edi.document'].sudo()

        def get_state(payload):
            document = Document.search([('request_id', '=', payload['requestID'])], limit=1)
            numbers = [record._l10n_ao_edi_number() for record in document._queued_records()]
            return 200, {
                'resultCode': '0',
                'documentStatusList': [{'documentNo': n, 'documentStatus': 'V'} for n in numbers],
            }

        return {'registarFactura': (200, {'requestID': 'REQ1', 'errorList': []}), 'obterEstado': get_state}
