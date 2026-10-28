from contextlib import contextmanager
from unittest.mock import patch

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

TODAY = fields.Date.today()


class L10nAoEdiCommon(AccountTestInvoicingCommon):
    """Empresa angolana com facturação electrónica activa, chaves RSA de teste e séries activas."""

    @classmethod
    @AccountTestInvoicingCommon.setup_country('ao')
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        Key = cls.env['certificate.key']
        cls.software_key = Key._generate_rsa_private_key(cls.company, name='produtor', key_size=2048)
        cls.taxpayer_key = Key._generate_rsa_private_key(cls.company, name='contribuinte', key_size=2048)
        cls.company.write(
            {
                'vat': '5000000001',
                'l10n_ao_edi_enabled': True,
                'l10n_ao_edi_environment': 'test',
                'l10n_ao_edi_software_validation_number': 'C_134',
                'l10n_ao_edi_software_key_id': cls.software_key.id,
                'l10n_ao_edi_taxpayer_key_id': cls.taxpayer_key.id,
                'l10n_ao_edi_username': 'teste',
                'l10n_ao_edi_password': 'teste',
            }
        )
        Series = cls.env['l10n_ao_edi.series']
        cls.series = {
            doc_type: Series.create(
                {
                    'document_type': doc_type,
                    'year': TODAY.year,
                    'code': f'{doc_type}{TODAY.year % 100}S1',
                    'state': 'active',
                }
            )
            for doc_type in ('FT', 'FR', 'FG', 'NC', 'ND', 'RG')
        }
        cls.contingency_series = Series.create(
            {
                'document_type': 'FT',
                'year': TODAY.year,
                'code': f'FT{TODAY.year % 100}C1',
                'contingency': True,
                'state': 'active',
            }
        )
        cls.partner_ao = cls.env['res.partner'].create(
            {'name': 'Cliente Angola, Lda', 'country_id': cls.env.ref('base.ao').id, 'vat': '5000000002'}
        )
        cls.consumer = cls.env['res.partner'].create({'name': 'Consumidor final'})
        cls.vat14 = cls._ao_tax('ao_iva_sale_14')
        cls.exempt_m21 = cls._ao_tax('ao_iva_sale_ise_m21')
        cls.service = cls.env['product.product'].create(
            {'name': 'Consultoria', 'type': 'service', 'default_code': 'CONS'}
        )
        cls.goods = cls.env['product.product'].create({'name': 'Caderno', 'type': 'consu', 'default_code': 'CAD'})

    @classmethod
    def _ao_tax(cls, xmlid):
        return cls.env.ref(f'account.{cls.company.id}_{xmlid}')

    def _create_invoice(self, partner=None, lines=None, move_type='out_invoice', post=True, **values):
        lines = lines or [(self.service, 1, 1000.0, self.vat14)]
        move = self.env['account.move'].create(
            {
                'move_type': move_type,
                'partner_id': (partner or self.partner_ao).id,
                'invoice_date': TODAY,
                'invoice_line_ids': [
                    Command.create(
                        {
                            'product_id': product.id,
                            'quantity': qty,
                            'price_unit': price,
                            'tax_ids': [Command.set(taxes.ids)],
                        }
                    )
                    for product, qty, price, taxes in lines
                ],
                **values,
            }
        )
        if post:
            move.action_post()
        return move

    @contextmanager
    def mock_agt(self, responses):
        """Simula a AGT. ``responses``: dict serviço -> (código HTTP, corpo) ou função(payload) -> (código, corpo).
        Os pedidos feitos ficam em ``self.agt_calls``."""
        self.agt_calls = []

        def fake_call(company, service, payload):
            self.agt_calls.append((service, payload))
            response = responses[service]
            return response(payload) if callable(response) else response

        with patch.object(type(self.env['res.company']), '_l10n_ao_edi_call', fake_call, create=False):
            yield

    def send_and_poll(self):
        Document = self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)
        Document._cron_send()
        documents = Document.sudo().search([('state', '=', 'sent')])
        documents.write({'next_poll': fields.Datetime.now()})
        Document._cron_poll()

    def send_and_poll_send_only(self):
        self.env['l10n_ao_edi.document'].with_context(l10n_ao_edi_no_commit=True)._cron_send()

    def register_payment(self, invoices, amount=None, **values):
        wizard = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=invoices.ids)
            .create({'amount': amount, **values} if amount is not None else values)
        )
        return wizard._create_payments()

    def mark_sent(self, *records):
        for record in records:
            record.sudo().l10n_ao_edi_state = 'sent'
