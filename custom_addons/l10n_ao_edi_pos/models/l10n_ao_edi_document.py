from odoo import api, fields, models


class L10nAoEdiDocument(models.Model):
    _inherit = 'l10n_ao_edi.document'

    pos_order_ids = fields.Many2many(
        'pos.order',
        'l10n_ao_edi_document_pos_order_rel',
        'document_id',
        'pos_order_id',
        string='Talões',
        readonly=True,
    )

    @api.model
    def _queue_fields(self):
        # Os talões seguem depois das facturas (uma NC do POS pode referir uma FR) e antes dos recibos.
        queue = super()._queue_fields()
        payments = queue.pop('account.payment')
        return {**queue, 'pos.order': 'pos_order_ids', 'account.payment': payments}
