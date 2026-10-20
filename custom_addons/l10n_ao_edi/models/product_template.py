from odoo import fields, models

# Tipo de operação por linha (Anexo I do DE n.º 683/25, operationType).
AGT_OPERATION_TYPES = [
    ('TB', 'TB - Transmissão de bens'),
    ('SG', 'SG - Prestação de serviço (geral)'),
    ('SE', 'SE - Serviços de educação'),
    ('SS', 'SS - Serviços de saúde'),
    ('STP', 'STP - Transporte de passageiros'),
    ('SR', 'SR - Serviços sujeitos a royalties'),
    ('SIF', 'SIF - Intermediação financeira ou seguradora'),
    ('SHS', 'SHS - Hotelaria e similares'),
    ('ST', 'ST - Telecomunicações'),
    ('AS', 'AS - Arrendamento e subarrendamento'),
    ('QT', 'QT - Quotas'),
    ('RD', 'RD - Repasse de despesas'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ao_operation_type = fields.Selection(
        AGT_OPERATION_TYPES,
        string='Tipo de operação (AGT)',
        help='Por omissão: TB para bens, SG para serviços.',
    )
