{
    'name': 'Kututa Mukanda - Facturação Electrónica AGT',
    'version': '20.0.1.0.0',
    'summary': 'Facturação electrónica certificada AGT (DP n.º 71/25, DE n.º 683/25)',
    'description': """
Kututa Mukanda: facturação electrónica angolana.

* Séries de numeração geradas pela AGT (solicitarSerie)
* Numeração no formato AGT («FT <série>/<n.º>»)
* Assinaturas JWS RS256 (software, documento e pedido)
* Envio à AGT (registarFactura) e consulta do estado de validação (obterEstado)
* Regras do Regime Jurídico das Facturas: bloqueio de documentos comunicados,
  notas de crédito com motivo e documento de origem
* QR Code da AGT e identificação do software validado no documento impresso
* Recibos (RC) emitidos nos recebimentos, com as retenções na fonte sofridas
* Contingência (art. 18.º) e bloqueio da emissão após 60 dias sem comunicação (art. 17.º)
* Confirmação/rejeição na AGT das facturas de fornecedores (validarDocumento)
* Sincronização das séries registadas na AGT (listarSeries)
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Accounting/Localizations/EDI',
    'depends': [
        'l10n_ao',
        'account_debit_note',
        'certificate',
    ],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/l10n_ao_edi_series_views.xml',
        'views/l10n_ao_edi_document_views.xml',
        'views/res_company_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/product_template_views.xml',
        'report/report_invoice.xml',
        'report/report_payment_receipt.xml',
    ],
    'license': 'OPL-1',
}
