from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .edu_enrollment import SEAT_STATES

TRANSFER_TYPES = [
    ('class_change', 'Mudar de turma'),
    ('course_change', 'Mudar de curso'),
    ('external', 'Sair para outra escola'),
    ('incoming', 'Entrada de outra escola'),
]
INTERNAL_TYPES = ('class_change', 'course_change')


class EduTransfer(models.Model):
    """Transferência (DP 162/23, art. 30.º). Dentro da escola, a mesma matrícula muda de turma (as notas acompanham-na)
    e recebe o número de ordem seguinte na turma de destino. A saída para outra escola só se conclui com o parecer de
    vaga da escola de destino, fecha a matrícula como «Transferido» e dá os documentos de saída (guia e declaração com
    as notas). A entrada de um aluno de outra escola cria (ou reutiliza, pelo BI) o aluno e matricula-o como
    transferido, até ao fim do 1.º mês do II trimestre (art. 25.º, n.º 2) e havendo vaga. A secretaria pede, a direcção
    aprova."""

    _name = 'edu.transfer'
    _description = 'Transferência'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    student_id = fields.Many2one('edu.student', string='Aluno', index=True, tracking=True, check_company=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    enrollment_id = fields.Many2one(
        'edu.enrollment',
        string='Matrícula',
        check_company=True,
        domain="[('student_id', '=', student_id), ('state', 'in', ('active', 'irregular'))]",
    )
    transfer_type = fields.Selection(
        TRANSFER_TYPES, string='Tipo', required=True, default='class_change', tracking=True
    )
    from_class_id = fields.Many2one(
        'edu.class',
        string='Turma de origem',
        compute='_compute_from_class_id',
        store=True,
        readonly=True,
        copy=False,
    )
    to_class_id = fields.Many2one(
        'edu.class',
        string='Turma de destino',
        check_company=True,
        domain="[('academic_year_id', '=', academic_year_id)]",
    )
    academic_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano lectivo',
        compute='_compute_academic_year_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    external_school = fields.Char(string='Escola de destino', tracking=True)
    vacancy_confirmed = fields.Boolean(
        string='Vaga confirmada pela escola de destino',
        tracking=True,
        help='Sem a confirmação da vaga, a transferência para outra escola não se conclui '
        '(DP 162/23, art. 30.º, n.º 2).',
    )
    vacancy_reference = fields.Char(string='Parecer de vaga', help='Número ou data do parecer de vaga recebido.')
    # Entrada de outra escola: o aluno pode ainda não existir.
    origin_school = fields.Char(string='Escola de origem', tracking=True)
    incoming_name = fields.Char(string='Nome do aluno')
    incoming_id_number = fields.Char(string='N.º do BI / passaporte')
    incoming_birth_date = fields.Date(string='Data de nascimento')
    incoming_gender = fields.Selection([('male', 'Masculino'), ('female', 'Feminino')], string='Sexo')
    origin_documents = fields.Boolean(
        string='Guia e processo individual recebidos',
        tracking=True,
        help='A escola de origem envia o processo individual do aluno (art. 30.º, n.º 2; art. 29.º).',
    )
    reason = fields.Text(string='Motivo', required=True)
    state = fields.Selection(
        [
            ('pending', 'Pendente'),
            ('approved', 'Aprovada'),
            ('rejected', 'Rejeitada'),
            ('completed', 'Concluída'),
            ('cancelled', 'Cancelada'),
        ],
        string='Estado',
        default='pending',
        required=True,
        tracking=True,
    )
    next_step = fields.Char(string='Próximo passo', compute='_compute_next_step')
    effective_date = fields.Date(string='Data de efeito', default=fields.Date.context_today)
    reviewed_by_id = fields.Many2one('res.users', string='Decidida por', readonly=True, copy=False)
    decision_note = fields.Text(string='Fundamentação')

    @api.depends('enrollment_id')
    def _compute_from_class_id(self):
        for transfer in self:
            if transfer.state in ('pending', 'approved') or not transfer.from_class_id:
                transfer.from_class_id = transfer.enrollment_id.class_id

    @api.depends('enrollment_id', 'to_class_id')
    def _compute_academic_year_id(self):
        for transfer in self:
            transfer.academic_year_id = (
                transfer.enrollment_id.academic_year_id
                or transfer.to_class_id.academic_year_id
                or transfer.academic_year_id
                or self.env.company.edu_current_year_id
            )

    @api.depends('state', 'transfer_type', 'vacancy_confirmed', 'origin_documents')
    def _compute_next_step(self):
        for transfer in self:
            if transfer.state == 'pending':
                step = self.env._('Aguarda a decisão da direcção')
            elif transfer.state == 'approved':
                if transfer.transfer_type == 'external' and not transfer.vacancy_confirmed:
                    step = self.env._('Falta o parecer de vaga da escola de destino')
                elif transfer.transfer_type == 'incoming' and not transfer.origin_documents:
                    step = self.env._('Falta receber a guia e o processo do aluno')
                else:
                    step = self.env._('Falta concluir')
            else:
                step = False
            transfer.next_step = step

    @api.depends('student_id', 'incoming_name', 'transfer_type')
    def _compute_display_name(self):
        types = dict(TRANSFER_TYPES)
        for transfer in self:
            name = transfer.student_id.name or transfer.incoming_name or ''
            transfer.display_name = f'{types.get(transfer.transfer_type, "")} · {name}'

    @api.constrains('transfer_type', 'to_class_id', 'external_school', 'enrollment_id', 'student_id', 'incoming_name')
    def _check_target(self):
        for transfer in self:
            kind = transfer.transfer_type
            if kind == 'incoming':
                if not (transfer.student_id or transfer.incoming_name):
                    raise ValidationError(self.env._('Indique o aluno que vem transferido.'))
                if not transfer.origin_school:
                    raise ValidationError(self.env._('Indique a escola de origem.'))
                if not transfer.to_class_id:
                    raise ValidationError(self.env._('Indique a turma onde o aluno fica.'))
                if transfer.academic_year_id and transfer.to_class_id.academic_year_id != transfer.academic_year_id:
                    raise ValidationError(self.env._('A turma tem de ser do ano lectivo da transferência.'))
                continue
            if not transfer.student_id or not transfer.enrollment_id:
                raise ValidationError(self.env._('Indique o aluno e a matrícula.'))
            if transfer.enrollment_id.student_id != transfer.student_id:
                raise ValidationError(self.env._('A matrícula não é deste aluno.'))
            if kind == 'external':
                if not transfer.external_school:
                    raise ValidationError(self.env._('Indique a escola de destino.'))
                continue
            target = transfer.to_class_id
            if not target:
                raise ValidationError(self.env._('Indique a turma de destino.'))
            origin = transfer.from_class_id or transfer.enrollment_id.class_id
            if target == origin and transfer.state == 'pending':
                raise ValidationError(self.env._('A turma de destino é a actual.'))
            if target.academic_year_id != transfer.enrollment_id.academic_year_id:
                raise ValidationError(self.env._('A turma de destino tem de ser do mesmo ano lectivo.'))
            if target.class_number != origin.class_number:
                raise ValidationError(self.env._('A turma de destino tem de ser da mesma classe.'))
            if kind == 'class_change' and target.course_id != origin.course_id:
                raise ValidationError(self.env._('Para mudar de curso, escolha «Mudar de curso».'))
            if kind == 'course_change' and target.course_id == origin.course_id:
                raise ValidationError(self.env._('Numa mudança de curso, a turma de destino é de outro curso.'))

    def write(self, vals):
        # Mudar o destino de uma transferência aprovada volta a pedir a decisão da direcção.
        decided = {'to_class_id', 'external_school', 'vacancy_confirmed', 'vacancy_reference', 'transfer_type'}
        if decided & set(vals) and 'state' not in vals and not self.env.user.has_group('edu_core.group_edu_manager'):
            approved = self.filtered(lambda t: t.state == 'approved')
            if approved:
                super(EduTransfer, approved).write({'state': 'pending', 'reviewed_by_id': False})
        return super().write(vals)

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('A decisão sobre a transferência é da direcção.'))

    def action_approve(self):
        self._check_manager()
        for transfer in self:
            if transfer.state != 'pending':
                raise UserError(self.env._('Só se aprova uma transferência pendente.'))
            transfer.write({'state': 'approved', 'reviewed_by_id': self.env.uid})
        return True

    def action_reject(self):
        self._check_manager()
        for transfer in self:
            if transfer.state != 'pending':
                raise UserError(self.env._('Só se rejeita uma transferência pendente.'))
            if not transfer.decision_note:
                raise UserError(self.env._('Indique a fundamentação da rejeição.'))
            transfer.write({'state': 'rejected', 'reviewed_by_id': self.env.uid})
        return True

    def action_cancel(self):
        if self.filtered(lambda t: t.state == 'completed'):
            raise UserError(self.env._('Uma transferência concluída não se cancela.'))
        self.write({'state': 'cancelled'})
        return True

    @api.ondelete(at_uninstall=False)
    def _unlink_only_pending(self):
        if self.filtered(lambda t: t.state not in ('pending', 'cancelled')):
            raise UserError(self.env._('Só se elimina uma transferência pendente ou cancelada.'))

    def _incoming_deadline(self):
        """Matrícula de transferidos fora do prazo: até ao fim do 1.º mês do II trimestre (DP 162/23, art. 25.º)."""
        self.ensure_one()
        second = self.academic_year_id.trimester_ids.filtered(lambda t: t.number == 2)[:1]
        return second.date_start + relativedelta(months=1, days=-1) if second else False

    def action_complete(self):
        for transfer in self:
            if transfer.state != 'approved':
                raise UserError(self.env._('Aprove a transferência antes de a concluir.'))
            if transfer.transfer_type == 'incoming':
                transfer._complete_incoming()
            else:
                enrollment = transfer.enrollment_id
                if enrollment.state not in SEAT_STATES:
                    raise UserError(self.env._('A matrícula já não está em curso.'))
                if transfer.transfer_type == 'external':
                    transfer._complete_external()
                else:
                    transfer._complete_internal()
            transfer.state = 'completed'
        return True

    def _complete_external(self):
        if not self.vacancy_confirmed:
            raise UserError(
                self.env._('Falta a confirmação de vaga da escola de destino (DP 162/23, art. 30.º, n.º 2).')
            )
        self.enrollment_id._drop(
            self.env._('Transferido(a) para %(school)s. %(reason)s', school=self.external_school, reason=self.reason),
            state='transferred',
            day=self.effective_date,
        )

    def _complete_internal(self):
        Enrollment = self.env['edu.enrollment']
        enrollment = self.enrollment_id
        target = self.to_class_id
        origin = enrollment.class_id
        taken = Enrollment.search_count([('class_id', '=', target.id), ('state', 'in', SEAT_STATES)])
        if target.capacity and taken >= target.capacity:
            raise UserError(self.env._('A turma %s está completa.', target.display_name))
        vals = {'class_id': target.id, 'order_number': Enrollment._next_order_number(target)}
        if target.curriculum_id != origin.curriculum_id or target.class_number != origin.class_number:
            # Disciplinas do novo plano, mais as que já têm notas.
            vals['subject_ids'] = [
                fields.Command.set((target.subject_line_ids.subject_id | enrollment._edu_locked_subjects()).ids)
            ]
        enrollment.with_context(edu_enrollment_reseed=True).write(vals)
        if target.course_id != origin.course_id:
            # As disciplinas feitas numa turma da classe anterior eram do curso antigo.
            enrollment.lower_subject_ids.unlink()

    def _complete_incoming(self):
        if not self.origin_documents:
            raise UserError(self.env._('Registe a recepção da guia e do processo individual do aluno.'))
        deadline = self._incoming_deadline()
        day = max(filter(None, [self.effective_date, fields.Date.context_today(self)]))
        if deadline and day > deadline and not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(
                self.env._(
                    'Fora do prazo de matrícula de transferidos (até %s): só a direcção.',
                    deadline.strftime('%d/%m/%Y'),
                )
            )
        student = self.student_id
        if not student and self.incoming_id_number:
            student = self.env['edu.student'].search(
                [('id_number', '=', self.incoming_id_number), ('company_id', '=', self.company_id.id)], limit=1
            )
        if not student:
            student = self.env['edu.student'].create(
                {
                    'name': self.incoming_name,
                    'id_number': self.incoming_id_number or False,
                    'birth_date': self.incoming_birth_date or False,
                    'gender': self.incoming_gender or False,
                    'company_id': self.company_id.id,
                }
            )
        enrollment = self.env['edu.enrollment'].create(
            {
                'student_id': student.id,
                'class_id': self.to_class_id.id,
                'enrollment_type': 'transfer_in',
                'date': self.effective_date,
            }
        )
        enrollment.action_confirm()
        self.write({'student_id': student.id, 'enrollment_id': enrollment.id})
