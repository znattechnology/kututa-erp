from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Estados que ocupam vaga na turma (o irregular está matriculado, com propinas em atraso).
SEAT_STATES = ('active', 'irregular')
CLOSED_STATES = ('dropped', 'transferred')


class EduEnrollment(models.Model):
    _name = 'edu.enrollment'
    _description = 'Matrícula'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'academic_year_id desc, class_id, order_number, id'
    _check_company_auto = True

    student_id = fields.Many2one(
        'edu.student', string='Aluno', required=True, index=True, tracking=True, check_company=True
    )
    class_id = fields.Many2one(
        'edu.class', string='Turma', required=True, index=True, tracking=True, check_company=True
    )
    company_id = fields.Many2one(related='class_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='class_id.academic_year_id', store=True, index=True)
    course_id = fields.Many2one(related='class_id.course_id', store=True)
    class_number = fields.Integer(related='class_id.class_number', store=True)
    matricula_number = fields.Char(related='student_id.matricula_number')
    state = fields.Selection(
        [
            ('draft', 'Pendente'),
            ('active', 'Activa'),
            ('irregular', 'Irregular'),
            ('transferred', 'Transferido'),
            ('dropped', 'Anulada'),
            ('completed', 'Concluída'),
            ('retained', 'Retido'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )
    enrollment_type = fields.Selection(
        [
            ('new', 'Nova matrícula'),
            ('renewal', 'Rematrícula'),
            ('repeat', 'Repetente'),
            ('transfer_in', 'Transferido de outra escola'),
        ],
        string='Tipo',
        default='new',
        required=True,
    )
    order_number = fields.Integer(
        string='N.º de ordem', readonly=True, copy=False, tracking=True, help='Número na pauta da turma, fixo no ano.'
    )
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    drop_date = fields.Date(string='Data de saída', readonly=True, copy=False)
    drop_reason = fields.Text(string='Motivo da saída', readonly=True, copy=False)
    subject_ids = fields.Many2many('edu.subject', string='Disciplinas', check_company=True)
    previous_enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula anterior', copy=False)
    application_id = fields.Many2one('edu.application', string='Candidatura', readonly=True, copy=False)
    warning = fields.Text(string='Avisos', readonly=True, copy=False)
    note = fields.Text(string='Notas')

    _order_number_uniq = models.UniqueIndex(
        '(class_id, order_number) WHERE order_number > 0', 'O número de ordem já existe nesta turma.'
    )
    _one_seat_per_year = models.UniqueIndex(
        "(student_id, academic_year_id) WHERE state IN ('active', 'irregular')",
        'O aluno já está matriculado neste ano lectivo.',
    )

    @api.depends('student_id', 'class_id')
    def _compute_display_name(self):
        for enrollment in self:
            enrollment.display_name = f'{enrollment.student_id.name or ""} · {enrollment.class_id.display_name or ""}'

    @api.model_create_multi
    def create(self, vals_list):
        enrollments = super().create(vals_list)
        for enrollment in enrollments.filtered(lambda e: not e.subject_ids):
            enrollment.subject_ids = enrollment.class_id.subject_line_ids.subject_id
        return enrollments

    @api.constrains('student_id', 'academic_year_id', 'state')
    def _check_one_per_year(self):
        for enrollment in self.filtered(lambda e: e.state not in CLOSED_STATES):
            other = self.search(
                [
                    ('id', '!=', enrollment.id),
                    ('student_id', '=', enrollment.student_id.id),
                    ('academic_year_id', '=', enrollment.academic_year_id.id),
                    ('state', 'not in', CLOSED_STATES),
                ],
                limit=1,
            )
            if other:
                raise ValidationError(
                    self.env._(
                        '%(student)s já tem matrícula em %(year)s (%(class)s).',
                        student=enrollment.student_id.name,
                        year=enrollment.academic_year_id.name,
                        **{'class': other.class_id.display_name},
                    )
                )

    @api.constrains('subject_ids', 'class_id')
    def _check_subjects(self):
        """Só disciplinas do plano do curso, da classe da turma ou de classes anteriores (atrasos)."""
        for enrollment in self:
            allowed = enrollment._allowed_subjects()
            extra = enrollment.subject_ids - allowed - enrollment._edu_locked_subjects()
            if allowed and extra:
                raise ValidationError(
                    self.env._('Fora do plano curricular da turma: %s.', ', '.join(extra.mapped('name')))
                )

    def _allowed_subjects(self):
        self.ensure_one()
        curriculum = self.class_id.curriculum_id
        lines = curriculum.line_ids.filtered(lambda line: line.year_id.class_number <= self.class_number)
        return lines.subject_id

    # ------------------------------------------------------------------
    # Pontos de extensão (avaliação, propinas)
    # ------------------------------------------------------------------
    def _edu_check_enrollment_allowed(self):
        """Bloqueios da matrícula: levanta UserError. A avaliação acrescenta retenções e disciplinas em atraso."""
        self.ensure_one()

    def _edu_enrollment_warnings(self):
        """Avisos que não bloqueiam (por exemplo, propinas em atraso, no módulo das propinas)."""
        self.ensure_one()
        return []

    def _edu_locked_subjects(self):
        """Disciplinas que já não se retiram da matrícula (com notas lançadas, no módulo da avaliação)."""
        self.ensure_one()
        return self.env['edu.subject']

    # ------------------------------------------------------------------
    def _check_capacity(self):
        for enrollment in self:
            edu_class = enrollment.class_id
            taken = self.search_count(
                [('class_id', '=', edu_class.id), ('state', 'in', SEAT_STATES), ('id', '!=', enrollment.id)]
            )
            if edu_class.capacity and taken >= edu_class.capacity:
                raise UserError(
                    self.env._(
                        'A turma %(class)s está completa (%(capacity)s vagas).',
                        capacity=edu_class.capacity,
                        **{'class': edu_class.display_name},
                    )
                )

    def _next_order_number(self, edu_class):
        """O seguinte na turma: quem entra a meio do ano fica no fim da pauta, sem renumerar os outros."""
        last = self.search(
            [('class_id', '=', edu_class.id), ('order_number', '!=', False)], order='order_number desc', limit=1
        )
        return (last.order_number or 0) + 1

    def action_confirm(self):
        for enrollment in self.filtered(lambda e: e.state == 'draft'):
            enrollment._edu_check_enrollment_allowed()
            enrollment._check_capacity()
            year = enrollment.academic_year_id
            enrollment.student_id._assign_matricula_number(year=year.date_start.year, date=enrollment.date)
            vals = {'state': 'active', 'warning': '\n'.join(enrollment._edu_enrollment_warnings()) or False}
            if not enrollment.order_number:
                vals['order_number'] = self._next_order_number(enrollment.class_id)
            enrollment.write(vals)
        return True

    def _drop(self, reason, state='dropped', day=None):
        for enrollment in self:
            if enrollment.state in CLOSED_STATES:
                raise UserError(self.env._('A matrícula de %s já está fechada.', enrollment.student_id.name))
            enrollment.write(
                {'state': state, 'drop_date': day or fields.Date.context_today(self), 'drop_reason': reason}
            )
        return True

    def action_drop(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Anular a matrícula'),
            'res_model': 'edu.enrollment.drop',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_enrollment_ids': self.ids},
        }

    def action_reactivate(self):
        for enrollment in self.filtered(lambda e: e.state in ('dropped', 'transferred', 'completed', 'retained')):
            enrollment._check_capacity()
            enrollment.write({'state': 'active', 'drop_date': False, 'drop_reason': False})
            enrollment._check_one_per_year()
        return True

    def action_mark_irregular(self):
        self.filtered(lambda e: e.state == 'active').write({'state': 'irregular'})
        return True

    def action_mark_regular(self):
        self.filtered(lambda e: e.state == 'irregular').write({'state': 'active'})
        return True

    def write(self, vals):
        if 'subject_ids' in vals and not self.env.context.get('edu_enrollment_reseed'):
            for enrollment in self:
                if enrollment.state in CLOSED_STATES + ('completed', 'retained'):
                    raise UserError(self.env._('As disciplinas só se alteram numa matrícula em curso.'))
            before = {enrollment: enrollment.subject_ids for enrollment in self}
            result = super().write(vals)
            for enrollment, subjects in before.items():
                removed = (subjects - enrollment.subject_ids) & enrollment._edu_locked_subjects()
                if removed:
                    raise UserError(
                        self.env._('Com notas lançadas, não se retira: %s.', ', '.join(removed.mapped('name')))
                    )
            return result
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if self.filtered(lambda e: e.state != 'draft'):
            raise UserError(self.env._('Só uma matrícula pendente se elimina; as outras anulam-se.'))
