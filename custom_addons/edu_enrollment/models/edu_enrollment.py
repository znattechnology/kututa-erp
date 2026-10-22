from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Estados que ocupam vaga na turma (o irregular está matriculado, com propinas em atraso).
SEAT_STATES = ('active', 'irregular')
CLOSED_STATES = ('dropped', 'transferred')

# Anulação de matrícula (DP 162/23, art. 28.º): os motivos justificados do n.º 4 dão direito a exames especiais no
# II Ciclo (n.º 3); a anulação oficiosa vem do processo incompleto (art. 24.º, n.º 10) ou de declarações falsas (art.
# 28.º, n.º 2).
DROP_REASONS = [
    ('illness', 'Doença comprovada'),
    ('relocation', 'Mudança de residência dos pais ou encarregados'),
    ('official_activity', 'Actividades oficiais culturais ou desportivas (mais de 45 dias lectivos)'),
    ('justified_other', 'Outro motivo fundamentado'),
    ('withdrawal', 'Desistência'),
    ('incomplete', 'Processo de matrícula incompleto (60 dias)'),
    ('false_statement', 'Declarações falsas no boletim de matrícula'),
    ('other', 'Outro'),
]
JUSTIFIED_REASONS = ('illness', 'relocation', 'official_activity', 'justified_other')
OFFICIAL_REASONS = ('incomplete', 'false_statement')
DROP_REQUESTERS = [
    ('guardian', 'Encarregado de educação'),
    ('student', 'O próprio aluno (maior de idade)'),
    ('school', 'A escola (anulação oficiosa)'),
]


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
            ('renewal', 'Confirmação de matrícula'),
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
    late_reason = fields.Char(
        string='Motivo da matrícula fora de prazo',
        help='Transferência, doença grave… (DP 162/23, art. 25.º, n.º 2). Exigido fora do período de matrícula.',
    )
    drop_date = fields.Date(string='Data de saída', readonly=True, copy=False, tracking=True)
    drop_reason_code = fields.Selection(DROP_REASONS, string='Motivo', readonly=True, copy=False, tracking=True)
    drop_requested_by = fields.Selection(DROP_REQUESTERS, string='Pedida por', readonly=True, copy=False)
    drop_justified = fields.Boolean(string='Anulação justificada', readonly=True, copy=False, tracking=True)
    drop_reason = fields.Text(string='Observações da saída', readonly=True, copy=False, tracking=True)
    drop_exam_right = fields.Boolean(
        string='Direito a exames especiais',
        compute='_compute_drop_exam_right',
        help='Anulação justificada, dentro do prazo, no II Ciclo (DP 162/23, art. 28.º, n.º 3).',
    )
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
        """Bloqueios da matrícula: levanta UserError. Na primeira matrícula, a idade mínima e o prazo do calendário; a
        avaliação acrescenta retenções e disciplinas em atraso."""
        self.ensure_one()
        if self.env.context.get('edu_matricula_import') or self.enrollment_type not in ('new', 'transfer_in'):
            return
        age, level = self._edu_age(), self.class_id.level_id
        if age is not None and level.min_age and age < level.min_age:
            raise UserError(
                self.env._(
                    '%(student)s tem %(age)s anos no ano da matrícula; a idade mínima para %(level)s é %(min)s '
                    '(DP 162/23, art. 21.º; DP 167/23, art. 23.º).',
                    student=self.student_id.name,
                    age=age,
                    level=level.name,
                    min=level.min_age,
                )
            )
        self._edu_check_enrollment_window()

    def _edu_age(self):
        """Idade completa no ano da matrícula (a lei conta os anos feitos até 31 de Dezembro desse ano)."""
        birth = self.student_id.birth_date
        return self.academic_year_id.date_start.year - birth.year if birth and self.academic_year_id else None

    def _edu_check_enrollment_window(self):
        """Fora do período de matrícula do calendário: só com motivo (transferência, doença…) e até ao fim do 1.º mês
        do II trimestre (DP 162/23, art. 25.º, n.º 2); depois disso, só a direcção."""
        today = fields.Date.context_today(self)
        start, end = self.env['edu.calendar.event']._phase_window(
            'enrollment', level=self.class_id.level_id, company=self.company_id, around=today
        )
        if not end or today <= end:
            return
        second = self.academic_year_id.trimester_ids.filtered(lambda t: t.number == 2)[:1]
        limit = second.date_start + relativedelta(months=1, days=-1) if second else False
        if limit and today > limit and not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(
                self.env._(
                    'Matrícula fora do prazo excepcional (até %s, DP 162/23, art. 25.º, n.º 2): só a direcção.',
                    limit.strftime('%d/%m/%Y'),
                )
            )
        if not self.late_reason:
            raise UserError(
                self.env._(
                    'Matrícula fora do período de matrícula (%(start)s a %(end)s): indique o motivo do atraso '
                    '(transferência, doença grave…) — DP 162/23, art. 25.º, n.º 2.',
                    start=start.strftime('%d/%m/%Y'),
                    end=end.strftime('%d/%m/%Y'),
                )
            )

    def _edu_enrollment_warnings(self):
        """Avisos que não bloqueiam: fora da idade regular (as propinas acrescentam a dívida)."""
        self.ensure_one()
        warnings = []
        age, level = self._edu_age(), self.class_id.level_id
        if age is not None and level.regular_age_max and age > level.regular_age_max:
            warnings.append(
                self.env._(
                    'Fora da idade regular (%(age)s anos; até %(max)s): apoio pedagógico específico ou educação de '
                    'adultos (DP 162/23, art. 23.º).',
                    age=age,
                    max=level.regular_age_max,
                )
            )
        return warnings

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

    @api.depends('state', 'drop_justified', 'class_number')
    def _compute_drop_exam_right(self):
        for enrollment in self:
            enrollment.drop_exam_right = (
                enrollment.state == 'dropped' and enrollment.drop_justified and enrollment.class_number >= 10
            )

    def _drop_deadline(self):
        """Último dia para anular a pedido: o fim do II trimestre no ensino geral (DP 162/23, art. 28.º, n.º 1); o 5.º
        dia útil do III trimestre no técnico (Despacho 60/08, art. 11.º). Sem trimestres, não há prazo."""
        self.ensure_one()
        trimesters = self.academic_year_id.trimester_ids.sorted('number')
        if self.course_id.level_id.subsystem == 'technical':
            third = trimesters.filtered(lambda t: t.number == 3)[:1]
            if not third:
                return False
            day, working = third.date_start, 0
            while True:
                if day.weekday() < 5:
                    working += 1
                    if working == 5:
                        return day
                day += timedelta(days=1)
        second = trimesters.filtered(lambda t: t.number == 2)[:1]
        return second.date_end if second else False

    def _edu_drop_warnings(self):
        """Avisos a mostrar antes de anular (as propinas acrescentam as facturas por pagar)."""
        self.ensure_one()
        return []

    def _drop(self, reason, state='dropped', day=None, *, reason_code=False, requested_by=False, justified=False):
        for enrollment in self:
            if enrollment.state in CLOSED_STATES:
                raise UserError(self.env._('A matrícula de %s já está fechada.', enrollment.student_id.name))
            enrollment.write(
                {
                    'state': state,
                    'drop_date': day or fields.Date.context_today(self),
                    'drop_reason': reason or False,
                    'drop_reason_code': reason_code,
                    'drop_requested_by': requested_by,
                    'drop_justified': justified,
                }
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
        """Volta a activar uma matrícula anulada ou transferida no ano em curso, com as regras da matrícula (vagas,
        retenções, disciplinas em atraso, dívida). A anulação anterior fica no histórico da matrícula."""
        for enrollment in self.filtered(lambda e: e.state in CLOSED_STATES):
            if not enrollment.academic_year_id.is_current:
                raise UserError(self.env._('Só se reactiva uma matrícula do ano lectivo em curso.'))
            enrollment._check_capacity()
            enrollment._edu_check_enrollment_allowed()
            labels = dict(DROP_REASONS)
            enrollment.message_post(
                body=self.env._(
                    'Matrícula reactivada. Saída anterior: %(date)s, %(reason)s.',
                    date=enrollment.drop_date and enrollment.drop_date.strftime('%d/%m/%Y') or '—',
                    reason=labels.get(enrollment.drop_reason_code) or enrollment.drop_reason or '—',
                )
            )
            enrollment.write(
                {
                    'state': 'active',
                    'drop_date': False,
                    'drop_reason': False,
                    'drop_reason_code': False,
                    'drop_requested_by': False,
                    'drop_justified': False,
                }
            )
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
