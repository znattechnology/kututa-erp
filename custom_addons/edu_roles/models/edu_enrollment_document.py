from odoo import api, fields, models


class EduEnrollmentDocumentType(models.Model):
    """As entregas de cada documento da matrícula no ano em curso, para os cartões da secretaria: em quantas
    matrículas é pedido e em quantas já foi entregue."""

    _inherit = 'edu.enrollment.document.type'

    edu_for_school = fields.Boolean(
        string='Dos níveis da escola',
        compute='_compute_edu_for_school',
        search='_search_edu_for_school',
        help='O documento vale para todos os níveis ou para um nível que a escola ensina (os níveis dos seus cursos).',
    )
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

    @api.model
    def _edu_school_levels(self):
        """Os níveis que a escola ensina: os dos seus cursos."""
        return self.env['edu.course'].sudo().search([('company_id', 'in', self.env.companies.ids)]).level_id

    def _compute_edu_for_school(self):
        levels = self._edu_school_levels()
        for doc_type in self:
            doc_type.edu_for_school = not doc_type.level_ids or bool(doc_type.level_ids & levels)

    def _search_edu_for_school(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        domain = ['|', ('level_ids', '=', False), ('level_ids', 'in', self._edu_school_levels().ids)]
        return domain if (operator == '=') == value else ['!', *domain]
