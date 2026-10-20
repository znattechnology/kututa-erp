from odoo import api, models
from odoo.exceptions import UserError

# Campos que definem a linha do talão comunicado.
LOCKED_LINE_FIELDS = (
    'product_id',
    'qty',
    'price_unit',
    'discount',
    'tax_ids',
    'price_subtotal',
    'price_subtotal_incl',
    'order_id',
)


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    @api.model
    def _l10n_ao_edi_raise_locked(self, orders):
        raise UserError(
            self.env._(
                'O documento %s já foi emitido: as linhas não podem ser alteradas (devolva a venda).',
                ', '.join(orders.mapped('l10n_ao_edi_document_no')),
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env['pos.order'].browse({vals.get('order_id') for vals in vals_list if vals.get('order_id')})
        if documented := orders.filtered('l10n_ao_edi_document_no'):
            self._l10n_ao_edi_raise_locked(documented)
        return super().create(vals_list)

    def _l10n_ao_edi_changes(self, vals):
        for field_name in LOCKED_LINE_FIELDS:
            if field_name in vals:
                field = self._fields[field_name]
                if field.convert_to_record(field.convert_to_cache(vals[field_name], self), self) != self[field_name]:
                    return True
        return False

    def write(self, vals):
        if any(field in vals for field in LOCKED_LINE_FIELDS):
            changed = self.filtered(
                lambda line: line.order_id.l10n_ao_edi_document_no and line._l10n_ao_edi_changes(vals)
            )
            if changed:
                self._l10n_ao_edi_raise_locked(changed.order_id)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_l10n_ao_edi(self):
        if documented := self.order_id.filtered('l10n_ao_edi_document_no'):
            self._l10n_ao_edi_raise_locked(documented)
