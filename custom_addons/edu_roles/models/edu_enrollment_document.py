from odoo import fields, models


class EduEnrollmentDocumentType(models.Model):
    """As entregas de cada documento da matrícula no ano em curso, para os cartões da secretaria: em quantas
    matrículas é pedido e em quantas já foi entregue."""

    _inherit = 'edu.enrollment.document.type'

    edu_requested = fields.Integer(string='Pedido em', compute='_compute_edu_delivery')
    edu_delivered = fields.Integer(string='Entregue em', compute='_compute_edu_delivery')
    edu_delivery = fields.Integer(string='Entregas (%)', compute='_compute_edu_delivery')

    def _compute_edu_delivery(self):
        Document = self.env['edu.enrollment.document'].sudo()
        domain = [('type_id', 'in', self.ids), ('enrollment_id.academic_year_id.is_current', '=', True)]
        requested = dict(Document._read_group(domain, ['type_id'], ['__count']))
        delivered = dict(Document._read_group([*domain, ('delivered', '=', True)], ['type_id'], ['__count']))
        for doc_type in self:
            doc_type.edu_requested = requested.get(doc_type, 0)
            doc_type.edu_delivered = delivered.get(doc_type, 0)
            doc_type.edu_delivery = (
                round(100 * doc_type.edu_delivered / doc_type.edu_requested) if doc_type.edu_requested else 0
            )
