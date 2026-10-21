{
    'name': 'Kitanda - Talões AGT no Ponto de Venda',
    'version': '20.0.1.2.0',
    'summary': 'Talões de venda (TV), facturas/recibo (FR) e notas de crédito certificados AGT no POS',
    'description': """
Kitanda: o Ponto de Venda com facturação electrónica AGT.

* Cada venda emite um Talão de Venda (TV) numerado numa série AGT e comunicado à AGT
* Venda facturada ao cliente: Factura/Recibo (FR); a crédito: Factura (FT)
* Devoluções: Nota de Crédito (NC) com referência ao talão e motivo obrigatório
* Talão impresso com o n.º AGT, QR Code, programa validado e menção «Original» / «2.ª via»
* Correcção de documentos rejeitados pela AGT; linhas bloqueadas depois da emissão
* Sem ligação ao servidor: talão provisório, sem valor fiscal; o talão certificado é emitido ao sincronizar
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Accounting/Localizations/Point of Sale',
    'depends': [
        'l10n_ao_edi',
        'point_of_sale',
    ],
    'data': [
        'views/pos_order_views.xml',
        'receipt/pos_order_receipt.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            # Arredondamento AGT do imposto por linha (o mesmo do backend).
            'l10n_ao/static/src/helpers/*.js',
            'l10n_ao_edi_pos/static/src/**/*',
        ],
        # Quiosque (self-order), se instalado: os mesmos totais e o mesmo talão.
        'pos_self_order.assets': [
            'l10n_ao/static/src/helpers/*.js',
            'l10n_ao_edi_pos/static/src/app/utils/generate_printer_data.js',
        ],
    },
    'auto_install': True,
    'license': 'OPL-1',
}
