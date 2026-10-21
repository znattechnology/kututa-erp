from odoo import api, fields, models
from odoo.exceptions import UserError


class EduGuardian(models.Model):
    """Encarregado de educação. É o adquirente das facturas das propinas (DP 71/25, art. 10.º): o NIF fica no
    contacto (campo «NIF» do Odoo)."""

    _name = 'edu.guardian'
    _description = 'Encarregado de educação'
    _inherit = ['mail.thread']
    _inherits = {'res.partner': 'partner_id'}
    _order = 'name'
    _check_company_auto = True
    _rec_names_search = ['name', 'phone', 'vat', 'id_number']

    partner_id = fields.Many2one('res.partner', string='Contacto', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    id_number = fields.Char(string='N.º do BI / passaporte')
    occupation = fields.Char(string='Profissão')
    student_link_ids = fields.One2many('edu.student.guardian', 'guardian_id', string='Educandos')
    student_count = fields.Integer(string='N.º de educandos', compute='_compute_student_count')
    active = fields.Boolean(default=True)

    _partner_company_uniq = models.Constraint(
        'UNIQUE(company_id, partner_id)', 'Este contacto já é encarregado nesta escola.'
    )

    @api.depends('student_link_ids')
    def _compute_student_count(self):
        for guardian in self:
            guardian.student_count = len(guardian.student_link_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id'):
                vals.setdefault('is_company', False)
                vals.setdefault('type', 'contact')
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_with_students(self):
        if self.student_link_ids:
            raise UserError(self.env._('O encarregado tem educandos associados: arquive-o.'))

    def action_view_students(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Educandos de %s', self.name),
            'res_model': 'edu.student',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.student_link_ids.student_id.ids)],
        }
