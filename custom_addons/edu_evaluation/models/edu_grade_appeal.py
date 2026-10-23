from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Em curso: recebido, admitido (em apreciação pelo conselho ou pela comissão) e no Conselho Pedagógico.
OPEN = ('pending', 'review', 'appealed')
FINAL = ('granted', 'denied', 'rejected')
REQUEST_DAYS = 3  # Despacho 60/08, art. 15.º, n.º 2: três dias úteis após a afixação das pautas
MEETING_DAYS = 5  # n.º 3: o conselho extraordinário reúne até cinco dias úteis após a aceitação
ANSWER_DAYS = 30  # n.º 5: o interessado sabe da deliberação até 30 dias após a entrada do pedido


class EduGradeAppeal(models.Model):
    """Reapreciação (revisão) dos resultados da avaliação — a única via de alterar uma classificação depois de a pauta
    estar afixada (o trimestre encerrado).

    * Técnico (Despacho 60/08, art. 15.º): o encarregado, ou o aluno maior, pede a revisão das deliberações do conselho
      de turma em requerimento fundamentado à direcção, até três dias úteis após a afixação das pautas (fora de prazo
      ou sem fundamento, indefere-se liminarmente). Aceite, a direcção convoca o conselho de turma extraordinário até
      cinco dias úteis depois, que delibera com relatório na acta; sem provimento, decide o Conselho Pedagógico. O
      interessado sabe da deliberação até 30 dias após a entrada do pedido.
    * Geral (DE 424/25, art. 36.º): a avaliação de fim de ano pode ser reapreciada a pedido fundamentado do aluno ou
      do encarregado à direcção; aceite, a direcção cria uma comissão para a reavaliação da prova. Os prazos são os do
      calendário do Ministério.

    O deferimento corrige a nota (a prova) que deu a classificação; a pauta e a decisão do ano recalculam-se."""

    _name = 'edu.grade.appeal'
    _description = 'Reapreciação de resultados'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', index=True, check_company=True)
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, string='Aluno')
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True, string='Turma')
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', index=True, check_company=True)
    trimester_id = fields.Many2one(
        'edu.trimester', string='Trimestre', help='Vazio: a classificação final do ano (a pauta final).'
    )
    regime = fields.Selection([('technical', 'Técnico'), ('general', 'Geral')], compute='_compute_regime', store=True)
    grade_id = fields.Many2one(
        'edu.grade', string='Nota corrigida', check_company=True, help='A nota (a prova) que o deferimento corrige.'
    )
    requester_type = fields.Selection(
        [('guardian', 'Encarregado de educação'), ('student', 'O próprio aluno')],
        string='Requerente',
        default='guardian',
        required=True,
    )
    requester_name = fields.Char(string='Nome do requerente')
    request_date = fields.Date(string='Entrada do pedido', required=True, default=fields.Date.context_today)
    posting_date = fields.Date(string='Afixação da pauta', help='A data em que a pauta contestada foi afixada.')
    deadline_date = fields.Date(string='Prazo do pedido', compute='_compute_deadlines', store=True)
    late = fields.Boolean(string='Fora de prazo', compute='_compute_deadlines', store=True)
    answer_deadline = fields.Date(string='Responder até', compute='_compute_deadlines', store=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Documentos do requerimento')
    reason = fields.Text(string='Fundamentação do pedido', required=True)
    state = fields.Selection(
        [
            ('pending', 'Recebido'),
            ('review', 'Em apreciação'),
            ('appealed', 'No Conselho Pedagógico'),
            ('granted', 'Deferido'),
            ('denied', 'Indeferido'),
            ('rejected', 'Indeferido liminarmente'),
        ],
        string='Estado',
        default='pending',
        required=True,
        tracking=True,
    )
    admitted_date = fields.Date(string='Admitido em', readonly=True, copy=False)
    meeting_date = fields.Date(string='Reunião', help='Conselho de turma extraordinário (técnico) ou comissão (geral).')
    minutes_ref = fields.Char(string='Acta n.º')
    decision = fields.Text(string='Deliberação', help='O relatório da deliberação (que integra a acta).')
    pedagogical_decision = fields.Text(string='Decisão do Conselho Pedagógico')
    original_score = fields.Float(string='Nota inicial', digits=(4, 2), readonly=True)
    new_score = fields.Float(string='Nova nota', digits=(4, 2))
    has_new_score = fields.Boolean(readonly=True, copy=False)
    decided_date = fields.Datetime(string='Decidida em', readonly=True, copy=False)
    decided_by_id = fields.Many2one('res.users', string='Decidida por', readonly=True)
    notified_date = fields.Date(string='Interessado informado em', copy=False, tracking=True)

    @api.depends('class_id.level_id.subsystem')
    def _compute_regime(self):
        for appeal in self:
            appeal.regime = 'technical' if appeal.class_id.level_id.subsystem == 'technical' else 'general'

    @api.depends('posting_date', 'request_date', 'regime')
    def _compute_deadlines(self):
        for appeal in self:
            # Os três dias úteis são do técnico; no geral o prazo é o do calendário do Ministério (sem verificação).
            appeal.deadline_date = (
                appeal._add_working_days(appeal.posting_date, REQUEST_DAYS)
                if appeal.posting_date and appeal.regime == 'technical'
                else False
            )
            appeal.late = bool(
                appeal.deadline_date and appeal.request_date and appeal.request_date > appeal.deadline_date
            )
            appeal.answer_deadline = appeal.request_date and appeal.request_date + timedelta(days=ANSWER_DAYS)

    def _add_working_days(self, day, count):
        """Dias úteis: segunda a sexta, sem os feriados e pausas do calendário escolar."""
        edu_class = self.class_id
        holidays = set()
        if edu_class:
            holidays = (
                self.env['edu.calendar.event']
                .sudo()
                ._days_without_lessons(
                    edu_class.company_id, edu_class.level_id, day, day + timedelta(days=count * 3 + 14)
                )
            )
        while count:
            day += timedelta(days=1)
            if day.weekday() < 5 and day not in holidays:
                count -= 1
        return day

    # Criação

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Um pedido sobre uma nota concreta herda dela a matrícula, a disciplina e o trimestre.
            if vals.get('grade_id') and not vals.get('enrollment_id'):
                grade = self.env['edu.grade'].browse(vals['grade_id'])
                vals.setdefault('enrollment_id', grade.enrollment_id.id)
                vals.setdefault('subject_id', grade.subject_id.id)
                vals.setdefault('trimester_id', grade.trimester_id.id)
        appeals = super().create(vals_list)
        for appeal, vals in zip(appeals, vals_list, strict=True):
            if not appeal.enrollment_id or not appeal.subject_id:
                raise ValidationError(self.env._('Indique o aluno e a disciplina do pedido.'))
            if self.search_count(
                [
                    ('enrollment_id', '=', appeal.enrollment_id.id),
                    ('subject_id', '=', appeal.subject_id.id),
                    ('trimester_id', '=', appeal.trimester_id.id),
                    ('state', 'in', OPEN),
                    ('id', '!=', appeal.id),
                ]
            ):
                raise ValidationError(self.env._('Este resultado já tem uma reapreciação em curso.'))
            if not appeal.posting_date:
                appeal.posting_date = appeal._default_posting_date()
            if not appeal.requester_name:
                student = appeal.student_id.sudo()
                appeal.requester_name = (
                    student.primary_guardian_id.name if appeal.requester_type == 'guardian' else student.name
                ) or False
            if appeal.grade_id:
                appeal.original_score = appeal.grade_id.score
            if 'new_score' in vals:
                appeal.has_new_score = True
        return appeals

    def _default_posting_date(self):
        """A pauta afixa-se quando o trimestre encerra; a final, quando encerra o último."""
        trimester = self.trimester_id or self.class_id.academic_year_id.trimester_ids.sorted('number')[-1:]
        return trimester.closed_date.date() if trimester.closed_date else False

    def write(self, vals):
        # A nova nota escreveu-se (0 é uma nota): sem ela não se defere.
        if 'new_score' in vals:
            vals = dict(vals, has_new_score=True)
        if vals.get('grade_id'):
            grade = self.env['edu.grade'].browse(vals['grade_id'])
            vals = dict(vals, original_score=grade.score)
        return super().write(vals)

    # Decisões (da direcção e dos órgãos que ela regista)

    def _check_manager(self):
        if not (self.env.su or self.env.user.has_group('edu_core.group_edu_manager')):
            raise UserError(self.env._('Só a direcção admite e decide as reapreciações.'))

    def action_admit(self, meeting_date=None):
        """A direcção aceita o pedido e marca o conselho extraordinário (técnico, até 5 dias úteis) ou a comissão."""
        self._check_manager()
        today = fields.Date.context_today(self)
        for appeal in self:
            if appeal.state != 'pending':
                raise UserError(self.env._('Só se admite um pedido recebido.'))
            if appeal.late:
                raise UserError(
                    self.env._(
                        'O pedido entrou fora de prazo (até %s): indefere-se liminarmente.',
                        appeal.deadline_date.strftime('%d/%m/%Y'),
                    )
                )
            meeting = fields.Date.to_date(meeting_date) if meeting_date else appeal.meeting_date
            if appeal.regime == 'technical':
                limit = appeal._add_working_days(today, MEETING_DAYS)
                meeting = meeting or limit
                if meeting < today or meeting > limit:
                    raise UserError(
                        self.env._(
                            'O conselho de turma extraordinário reúne até cinco dias úteis após a aceitação (até %s).',
                            limit.strftime('%d/%m/%Y'),
                        )
                    )
            appeal.write({'state': 'review', 'admitted_date': today, 'meeting_date': meeting})
        return True

    def action_review(self):
        # Compatibilidade: «pôr em apreciação» é admitir.
        return self.action_admit()

    def action_reject(self, reason=None):
        """Indeferimento liminar: fora de prazo ou sem fundamento."""
        self._check_manager()
        for appeal in self:
            if appeal.state != 'pending':
                raise UserError(self.env._('Só se indefere liminarmente um pedido recebido.'))
            text = (reason or appeal.decision or '').strip()
            if not text:
                raise UserError(self.env._('Escreva o motivo do indeferimento (fora de prazo, sem fundamento…).'))
            appeal.write(
                {
                    'state': 'rejected',
                    'decision': text,
                    'decided_by_id': self.env.uid,
                    'decided_date': fields.Datetime.now(),
                }
            )
        return True

    def action_grant(self):
        """Deferido (pelo conselho, pela comissão ou pelo Conselho Pedagógico): corrige a nota e recalcula."""
        self._check_manager()
        for appeal in self:
            if appeal.state not in ('review', 'appealed'):
                raise UserError(
                    self.env._('A reapreciação defere-se depois de admitida (e apreciada pelo órgão competente).')
                )
            grade = appeal.grade_id
            if not grade:
                raise UserError(self.env._('Escolha a nota que a deliberação corrige.'))
            if not appeal.has_new_score:
                raise UserError(self.env._('Escreva a nova nota antes de deferir.'))
            if appeal.new_score == appeal.original_score:
                raise UserError(self.env._('A nova nota é igual à anterior: para manter a nota, indefira.'))
            if not 0 <= appeal.new_score <= grade.assessment_id.max_score:
                raise ValidationError(self.env._('A nova nota vai de 0 a %s.', grade.assessment_id.max_score))
            grade.with_context(edu_grade_appeal=True).write({'score': appeal.new_score, 'absent': False})
            appeal.write({'state': 'granted', 'decided_by_id': self.env.uid, 'decided_date': fields.Datetime.now()})
            # A decisão do ano (se já tomada e não manual) acompanha a nota reapreciada.
            year_result = grade.enrollment_id.sudo().year_result_id
            if year_result and not year_result.manual:
                year_result.action_recompute()
        return True

    def action_deny(self):
        """Sem provimento. No técnico, o Conselho Pedagógico toma a decisão final (o pedido passa para ele); no geral,
        e no Conselho Pedagógico, fica indeferido."""
        self._check_manager()
        for appeal in self:
            if appeal.state not in ('review', 'appealed'):
                raise UserError(self.env._('A reapreciação indefere-se depois de admitida.'))
            if appeal.state == 'review':
                if not (appeal.decision or '').strip():
                    raise UserError(self.env._('Escreva a deliberação (o fundamento do indeferimento).'))
                if appeal.regime == 'technical':
                    appeal.state = 'appealed'
                    continue
            elif not (appeal.pedagogical_decision or '').strip():
                raise UserError(self.env._('Escreva a decisão do Conselho Pedagógico.'))
            appeal.write({'state': 'denied', 'decided_by_id': self.env.uid, 'decided_date': fields.Datetime.now()})
        return True

    def action_notify(self, date=None):
        """Regista o dia em que o interessado soube da deliberação."""
        for appeal in self:
            if appeal.state not in FINAL:
                raise UserError(self.env._('Informa-se o interessado depois da decisão.'))
            appeal.notified_date = fields.Date.to_date(date) if date else fields.Date.context_today(self)
        return True
