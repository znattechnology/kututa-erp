from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

MAX_DAYS = 30
MIN_REASON = 5


class EduGradeEditPermission(models.Model):
    """Autorização da secretaria para um professor lançar notas num trimestre que não é o corrente (ainda aberto)."""

    _name = 'edu.grade.edit.permission'
    _description = 'Autorização de lançamento de notas'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    teacher_id = fields.Many2one(
        'hr.employee',
        string='Professor(a)',
        required=True,
        check_company=True,
        domain="[('edu_is_teacher', '=', True)]",
    )
    class_id = fields.Many2one('edu.class', string='Turma', required=True, check_company=True)
    company_id = fields.Many2one(related='class_id.company_id', store=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, check_company=True)
    trimester_id = fields.Many2one(
        'edu.trimester', string='Trimestre', required=True, domain="[('academic_year_id', '=', academic_year_id)]"
    )
    academic_year_id = fields.Many2one(related='class_id.academic_year_id')
    reason = fields.Text(string='Motivo', required=True)
    date_expiry = fields.Datetime(
        string='Válida até', required=True, default=lambda self: fields.Datetime.now() + timedelta(days=7)
    )
    revoked = fields.Boolean(string='Revogada', readonly=True, tracking=True)
    revoked_by_id = fields.Many2one('res.users', string='Revogada por', readonly=True)
    revoked_date = fields.Datetime(string='Revogada em', readonly=True)
    active_now = fields.Boolean(string='Em vigor', compute='_compute_active_now')

    @api.depends('revoked', 'date_expiry')
    def _compute_active_now(self):
        now = fields.Datetime.now()
        for permission in self:
            permission.active_now = not permission.revoked and permission.date_expiry > now

    @api.constrains('reason', 'date_expiry', 'trimester_id', 'teacher_id', 'class_id', 'subject_id')
    def _check_permission(self):
        now = fields.Datetime.now()
        for permission in self:
            if len((permission.reason or '').strip()) < MIN_REASON:
                raise ValidationError(self.env._('Indique o motivo da autorização.'))
            if permission.date_expiry <= now or permission.date_expiry > now + timedelta(days=MAX_DAYS + 1):
                raise ValidationError(self.env._('A autorização dura no máximo 30 dias.'))
            trimester = permission.trimester_id
            if trimester.state == 'closed':
                raise ValidationError(self.env._('O trimestre está fechado: a correcção faz-se por reapreciação.'))
            if trimester.is_current and trimester.academic_year_id.is_current:
                raise ValidationError(self.env._('No trimestre em curso o professor não precisa de autorização.'))
            assigned = (
                self.env['edu.teaching.assignment']
                .sudo()
                .search_count(
                    [
                        ('class_id', '=', permission.class_id.id),
                        ('subject_id', '=', permission.subject_id.id),
                        ('teacher_id', '=', permission.teacher_id.id),
                    ]
                )
            )
            if not assigned:
                raise ValidationError(
                    self.env._('%s não lecciona esta disciplina nesta turma.', permission.teacher_id.name)
                )

    @api.model_create_multi
    def create(self, vals_list):
        """Repetir o pedido para o mesmo caso renova a autorização em vigor em vez de a duplicar."""
        result = self.browse()
        to_create = []
        for vals in vals_list:
            existing = self.search(
                [
                    ('teacher_id', '=', vals.get('teacher_id')),
                    ('class_id', '=', vals.get('class_id')),
                    ('subject_id', '=', vals.get('subject_id')),
                    ('trimester_id', '=', vals.get('trimester_id')),
                    ('revoked', '=', False),
                    ('date_expiry', '>', fields.Datetime.now()),
                ],
                limit=1,
            )
            if existing:
                existing.write({'reason': vals.get('reason'), 'date_expiry': vals.get('date_expiry')})
                result |= existing
            else:
                to_create.append(vals)
        return result | super().create(to_create)

    def action_revoke(self):
        """Revoga: o professor deixa de poder alterar as notas desse trimestre; as que já lançou ficam."""
        self.filtered(lambda p: not p.revoked).write(
            {'revoked': True, 'revoked_by_id': self.env.uid, 'revoked_date': fields.Datetime.now()}
        )
        return True

    @api.model
    def _allows(self, employee, edu_class, subject, trimester):
        return bool(
            self.sudo().search_count(
                [
                    ('teacher_id', '=', employee.id),
                    ('class_id', '=', edu_class.id),
                    ('subject_id', '=', subject.id),
                    ('trimester_id', '=', trimester.id),
                    ('revoked', '=', False),
                    ('date_expiry', '>', fields.Datetime.now()),
                ]
            )
        )
