from odoo import api, fields, models
from odoo.addons.edu_core.tools.trust import is_trusted, trusted
from odoo.addons.edu_evaluation.tools import grading
from odoo.exceptions import AccessError, UserError, ValidationError


class EduStudent(models.Model):
    _inherit = 'edu.student'

    process_number = fields.Char(string='Processo individual n.º', copy=False, tracking=True)
    subject_result_ids = fields.One2many('edu.subject.result', 'student_id', string='Histórico escolar')
    graduation_ids = fields.One2many('edu.graduation', 'student_id', string='Conclusões')
    year_result_ids = fields.One2many('edu.year.result', 'student_id', string='Anos lectivos')
    history_summary = fields.Char(string='Percurso', compute='_compute_history_summary')

    _process_company_uniq = models.Constraint(
        'UNIQUE(company_id, process_number)', 'Já existe um aluno com este número de processo.'
    )

    @api.depends('year_result_ids.status')
    def _compute_history_summary(self):
        """«3 anos lectivos: transitou em 2 e concluiu o curso.», como no secPed."""
        for student in self:
            results = student.year_result_ids
            if not results:
                student.history_summary = self.env._(
                    '%s ainda não tem anos no histórico. Cada ano entra quando o conselho de turma fecha.', student.name
                )
                continue
            count = {
                status: len(results.filtered(lambda r, s=status: r.status == s))
                for status in set(results.mapped('status'))
            }
            parts = []
            promoted = count.get('promoted', 0) + count.get('conditional', 0)
            if promoted:
                parts.append(self.env._('transitou em %s', promoted))
            if count.get('retained'):
                parts.append(self.env._('não transitou em %s', count['retained']))
            if count.get('exam'):
                parts.append(self.env._('vai a exame em %s', count['exam']))
            if count.get('pending'):
                parts.append(self.env._('%s por decidir', count['pending']))
            if count.get('graduated'):
                parts.append(self.env._('concluiu o curso'))
            years = len(results)
            head = self.env._('1 ano lectivo') if years == 1 else self.env._('%s anos lectivos', years)
            text = ', '.join(parts[:-1]) + (self.env._(' e ') if len(parts) > 1 else '') + (parts[-1] if parts else '')
            student.history_summary = f'{head}: {text}.' if text else f'{head}.'

    def action_view_history(self):
        """O histórico do aluno: um ano lectivo por linha, com a média, a assiduidade e o resultado."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Histórico de %s', self.name),
            'res_model': 'edu.student',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('edu_records.edu_student_history_form').id, 'form')],
        }

    def action_view_subject_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Classificações de %s', self.name),
            'res_model': 'edu.subject.result',
            'view_mode': 'list',
            'views': [(self.env.ref('edu_records.edu_subject_result_history_list').id, 'list')],
            'domain': [('student_id', '=', self.id)],
            'context': {'group_by': ['academic_year_id'], 'create': False},
        }


class EduTrainingMixin(models.AbstractModel):
    """O que o estágio e a PAP partilham: são dos finalistas de um curso que os prevê, um por aluno e ano lectivo (sem
    contar os reprovados e os anulados, para se poder repetir), e o aluno vem da matrícula do ano."""

    _name = 'edu.training.mixin'
    _description = 'Etapa da formação técnica'

    # Campo do curso que diz se a etapa é obrigatória, e os estados que deixam o aluno repetir.
    _course_flag = None
    _graduation_field = None
    _label = ''  # «estágio», «PAP»: nas mensagens
    _repeat_states = ('failed', 'cancelled')
    _closed_states = ('passed', 'failed', 'cancelled')
    # O que o tutor (ou o orientador e o júri) grava; o resto é da secretaria e da direcção.
    _teacher_fields = ()
    # Depois de fechado, o aluno, a matrícula e a nota não mudam: a direcção reabre primeiro.
    _locked_fields = ('student_id', 'enrollment_id', 'grade')

    @api.model
    def _current_enrollment(self, student):
        return student.enrollment_ids.filtered(lambda e: e.state in ('active', 'irregular')).sorted(
            lambda e: e.academic_year_id.date_start, reverse=True
        )[:1]

    def _fill_enrollment(self):
        if self.student_id and self.enrollment_id.student_id != self.student_id:
            self.enrollment_id = self._current_enrollment(self.student_id)

    def _is_staff(self):
        return self.env.su or self.env.user.has_group('edu_core.group_edu_user')

    def _check_staff(self):
        if not self._is_staff():
            raise UserError(self.env._('Só a secretaria e a direcção mudam o estado.'))

    def _act(self, vals):
        """As acções (iniciar, fechar, anular, reabrir) gravam o estado por aqui, depois das suas verificações."""
        with trusted(self.env):  # marca do servidor: o cliente não a põe por contexto
            return self.write(vals)

    def write(self, vals):
        if not self.env.su:
            if not self._is_staff():
                allowed = set(self._teacher_fields)
                extra = {k for k in vals if k not in allowed and not k.startswith(('message_', 'activity_'))}
                if extra:
                    raise UserError(
                        self.env._('Como tutor ou orientador só regista o acompanhamento; o resto é da secretaria.')
                    )
            elif not is_trusted(self.env):
                if 'state' in vals:
                    raise UserError(self.env._('O estado muda pelos botões da ficha (iniciar, fechar, reabrir).'))
                if set(vals) & set(self._locked_fields) and self.filtered(lambda r: r.state in self._closed_states):
                    raise UserError(
                        self.env._('Já está fechado: o aluno e a nota não mudam. A direcção reabre-o primeiro.')
                    )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_closed(self):
        if self.env.su:
            return
        self._check_manager(self.env._('Só a direcção remove um estágio ou uma PAP.'))
        self._check_not_in_graduation()

    def _detach_from_draft_graduations(self):
        """Reaberto ou anulado, deixa de servir a uma conclusão por emitir."""
        self.env['edu.graduation'].sudo().search(
            [('state', '=', 'draft'), (self._graduation_field, 'in', self.ids)]
        ).write({self._graduation_field: False})

    def _check_one_per_year(self):
        for record in self:
            if not record.enrollment_id:
                raise ValidationError(self.env._('%s não tem matrícula activa neste ano.', record.student_id.name))
            if record.enrollment_id.student_id != record.student_id:
                raise ValidationError(self.env._('A matrícula é de outro aluno.'))
            course = record.course_id
            if course and self._course_flag and not course[self._course_flag]:
                raise ValidationError(
                    self.env._('O curso %(course)s não prevê %(what)s.', course=course.name, what=self._label)
                )
            if record.state in self._repeat_states:
                continue
            twin = self.search_count(
                [
                    ('id', '!=', record.id),
                    ('student_id', '=', record.student_id.id),
                    ('academic_year_id', '=', record.academic_year_id.id),
                    ('state', 'not in', self._repeat_states),
                ]
            )
            if twin:
                raise ValidationError(
                    self.env._(
                        '%(student)s já tem %(what)s em %(year)s (um reprovado ou anulado não conta).',
                        student=record.student_id.name,
                        what=self._label,
                        year=record.academic_year_id.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('student_id') and not vals.get('enrollment_id'):
                enrollment = self._current_enrollment(self.env['edu.student'].browse(vals['student_id']))
                vals['enrollment_id'] = enrollment.id or False
            if not self.env.su and not self.env.user.has_group('edu_core.group_edu_user'):
                raise UserError(self.env._('Só a secretaria regista estágios e PAP.'))
        return super().create(vals_list)

    def _check_manager(self, message):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(message)

    def _check_not_in_graduation(self):
        if (
            self.env['edu.graduation']
            .sudo()
            .search_count([('state', '=', 'issued'), (self._graduation_field, 'in', self.ids)], limit=1)
        ):
            raise UserError(self.env._('Já entrou numa conclusão de curso emitida: não se altera.'))


class EduInternship(models.Model):
    """Estágio curricular (resumo do regime de avaliação, III.5: condição de conclusão do curso técnico)."""

    _name = 'edu.internship'
    _description = 'Estágio curricular'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'edu.training.mixin']
    _order = 'date_start desc, id desc'
    _check_company_auto = True
    _course_flag = 'requires_internship'
    _graduation_field = 'internship_id'
    _label = 'estágio'
    _teacher_fields = ('hours', 'appraisal')

    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', check_company=True, domain="[('student_id', '=', student_id)]"
    )
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    course_id = fields.Many2one(related='enrollment_id.course_id', store=True)
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id', store=True, index=True)
    entity = fields.Char(string='Entidade de acolhimento', required=True)
    supervisor = fields.Char(string='Supervisor na entidade')
    supervisor_contact = fields.Char(string='Contacto do supervisor')
    tutor_id = fields.Many2one('hr.employee', string='Tutor(a) da escola', check_company=True)
    date_start = fields.Date(string='Início')
    date_end = fields.Date(string='Fim')
    hours = fields.Integer(string='Horas realizadas')
    grade = fields.Float(string='Classificação', digits=(4, 2), tracking=True)
    state = fields.Selection(
        [
            ('planned', 'Por começar'),
            ('ongoing', 'A decorrer'),
            ('passed', 'Aprovado'),
            ('failed', 'Não aprovado'),
            ('cancelled', 'Anulado'),
        ],
        string='Estado',
        default='planned',
        required=True,
        tracking=True,
    )
    appraisal = fields.Text(string='Apreciação', help='O parecer do tutor ou do supervisor sobre o estágio.')
    note = fields.Text(string='Observações')
    report_ids = fields.One2many('edu.internship.report', 'internship_id', string='Relatórios entregues')

    @api.onchange('student_id')
    def _onchange_student_id(self):
        self._fill_enrollment()

    @api.constrains('student_id', 'enrollment_id', 'state')
    def _check_student_year(self):
        self._check_one_per_year()

    @api.depends('student_id', 'entity')
    def _compute_display_name(self):
        for internship in self:
            internship.display_name = (
                self.env._(
                    'Estágio de %(student)s (%(entity)s)', student=internship.student_id.name, entity=internship.entity
                )
                if internship.entity
                else self.env._('Estágio de %s', internship.student_id.name or '…')
            )

    @api.constrains('grade', 'date_start', 'date_end', 'hours')
    def _check_internship(self):
        for internship in self:
            if not 0 <= internship.grade <= 20:
                raise ValidationError(self.env._('A classificação vai de 0 a 20.'))
            if internship.hours < 0:
                raise ValidationError(self.env._('As horas não podem ser negativas.'))
            if internship.date_start and internship.date_end and internship.date_end < internship.date_start:
                raise ValidationError(self.env._('O estágio termina antes de começar.'))

    def action_start(self):
        self._check_staff()
        if self.filtered(lambda i: i.state != 'planned'):
            raise UserError(self.env._('Só um estágio por começar se marca como a decorrer.'))
        self._act({'state': 'ongoing'})
        return True

    def action_evaluate(self, grade=None):
        """Fecha o estágio com a classificação: aprovado com 10 ou mais."""
        self._check_staff()
        for internship in self:
            if internship.state not in ('planned', 'ongoing'):
                raise UserError(self.env._('O estágio de %s já está fechado.', internship.student_id.name))
            grade = internship.grade if grade is None else grade
            internship._act({'grade': grade, 'state': 'passed' if grade >= 10 else 'failed'})
        return True

    def action_cancel(self):
        """Anula um estágio que ainda não fechou (um fechado, a direcção reabre-o primeiro)."""
        self._check_staff()
        if self.filtered(lambda i: i.state not in ('planned', 'ongoing')):
            raise UserError(self.env._('Só se anula um estágio por começar ou a decorrer.'))
        self._detach_from_draft_graduations()
        self._act({'state': 'cancelled'})
        return True

    def action_reopen(self):
        """A direcção reabre um estágio fechado (a nota estava errada, ou foi anulado por engano)."""
        self._check_manager(self.env._('Só a direcção reabre um estágio fechado.'))
        self._check_not_in_graduation()
        self._detach_from_draft_graduations()
        self._act({'state': 'ongoing'})
        return True


class EduInternshipReport(models.Model):
    """Relatório que o aluno entrega durante o estágio (intercalar, final…), com o ficheiro."""

    _name = 'edu.internship.report'
    _description = 'Relatório de estágio'
    _order = 'date desc, id desc'

    internship_id = fields.Many2one('edu.internship', string='Estágio', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='internship_id.company_id', store=True)
    name = fields.Char(string='Relatório', required=True)
    date = fields.Date(string='Entregue em', required=True, default=fields.Date.context_today)
    file = fields.Binary(string='Ficheiro', attachment=True)
    file_name = fields.Char(string='Nome do ficheiro')

    @api.constrains('internship_id')
    def _check_open(self):
        for report in self:
            if report.internship_id.state in report.internship_id._closed_states:
                raise ValidationError(self.env._('O estágio já está fechado: não se registam relatórios.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_closed(self):
        if not self.env.su and self.internship_id.filtered(lambda i: i.state in i._closed_states):
            raise UserError(self.env._('O estágio já está fechado: os relatórios ficam.'))


class EduFinalProject(models.Model):
    """Prova de Aptidão Profissional (PAP): defesa do projecto final do curso técnico."""

    _name = 'edu.final.project'
    _description = 'Prova de Aptidão Profissional (PAP)'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'edu.training.mixin']
    _order = 'defense_date desc, id desc'
    _check_company_auto = True
    _course_flag = 'requires_final_project'
    _graduation_field = 'final_project_id'
    _label = 'PAP'
    _repeat_states = ('failed',)
    _closed_states = ('passed', 'failed')
    _teacher_fields = ('note',)

    name = fields.Char(string='Tema', required=True, tracking=True)
    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', check_company=True, domain="[('student_id', '=', student_id)]"
    )
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    course_id = fields.Many2one(related='enrollment_id.course_id', store=True)
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id', store=True, index=True)
    advisor_id = fields.Many2one('hr.employee', string='Orientador(a)', check_company=True)
    jury_ids = fields.Many2many('hr.employee', string='Júri', check_company=True)
    description = fields.Text(string='Resumo')
    submitted_date = fields.Date(string='Entregue em')
    defense_date = fields.Date(string='Data da defesa')
    grade = fields.Float(string='Classificação', digits=(4, 2), tracking=True)
    note = fields.Text(string='Observações')
    state = fields.Selection(
        [
            ('proposed', 'Proposto'),
            ('ongoing', 'Em elaboração'),
            ('submitted', 'Entregue'),
            ('defended', 'Defendido'),
            ('passed', 'Aprovado'),
            ('failed', 'Reprovado'),
        ],
        string='Estado',
        default='proposed',
        required=True,
        tracking=True,
    )

    @api.onchange('student_id')
    def _onchange_student_id(self):
        self._fill_enrollment()

    @api.constrains('student_id', 'enrollment_id', 'state')
    def _check_student_year(self):
        self._check_one_per_year()

    @api.constrains('grade')
    def _check_grade(self):
        for project in self:
            if not 0 <= project.grade <= 20:
                raise ValidationError(self.env._('A classificação vai de 0 a 20.'))

    def action_start(self):
        self._check_staff()
        if self.filtered(lambda p: p.state != 'proposed'):
            raise UserError(self.env._('Só um trabalho proposto passa a «em elaboração».'))
        self._act({'state': 'ongoing'})
        return True

    def action_submit(self, day=None):
        self._check_staff()
        if self.filtered(lambda p: p.state not in ('proposed', 'ongoing')):
            raise UserError(self.env._('O trabalho já foi entregue.'))
        self._act({'state': 'submitted', 'submitted_date': day or fields.Date.context_today(self)})
        return True

    def action_evaluate(self, grade=None):
        """O resultado da defesa: aprovado com 10 ou mais. Só se defende um trabalho entregue."""
        self._check_staff()
        for project in self:
            if project.state in ('passed', 'failed'):
                raise UserError(self.env._('A PAP de %s já tem resultado.', project.student_id.name))
            if project.state not in ('submitted', 'defended'):
                raise UserError(self.env._('Registe primeiro a entrega do trabalho de %s.', project.student_id.name))
            if not project.defense_date:
                raise UserError(self.env._('Indique a data da defesa.'))
            grade = project.grade if grade is None else grade
            project._act({'grade': grade, 'state': 'passed' if grade >= 10 else 'failed'})
        return True

    def action_reopen(self):
        """A direcção reabre uma PAP com resultado (a nota estava errada)."""
        self._check_manager(self.env._('Só a direcção reabre uma PAP com resultado.'))
        self._check_not_in_graduation()
        self._detach_from_draft_graduations()
        self._act({'state': 'submitted'})
        return True


class EduGraduation(models.Model):
    """Conclusão de curso ou de nível: base do diploma e do certificado de habilitações."""

    _name = 'edu.graduation'
    _description = 'Conclusão de curso'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    year_result_id = fields.Many2one(
        'edu.year.result', string='Resultado do ano terminal', required=True, check_company=True
    )
    enrollment_id = fields.Many2one(related='year_result_id.enrollment_id', store=True)
    company_id = fields.Many2one(related='year_result_id.company_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='year_result_id.academic_year_id', store=True)
    course_id = fields.Many2one(related='enrollment_id.course_id', store=True)
    level_id = fields.Many2one(related='enrollment_id.class_id.level_id', store=True)
    date = fields.Date(string='Data de conclusão', required=True, default=fields.Date.context_today)
    plan_average = fields.Float(string='Classificação do plano curricular (PC)', digits=(4, 2), readonly=True)
    internship_id = fields.Many2one(
        'edu.internship', string='Estágio', domain="[('student_id', '=', student_id), ('state', '=', 'passed')]"
    )
    final_project_id = fields.Many2one(
        'edu.final.project', string='PAP', domain="[('student_id', '=', student_id), ('state', '=', 'passed')]"
    )
    final_grade = fields.Float(string='Classificação final', digits=(4, 2), readonly=True, tracking=True)
    diploma_number = fields.Char(string='Diploma n.º', readonly=True, copy=False, tracking=True)
    book_number = fields.Char(string='Livro de termos n.º')
    page_number = fields.Char(string='Folha n.º')
    state = fields.Selection(
        [('draft', 'Rascunho'), ('issued', 'Emitido'), ('cancelled', 'Anulado')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    final_result_ids = fields.Many2many(
        'edu.subject.result', string='Classificações finais das disciplinas', compute='_compute_final_result_ids'
    )
    # Validação do diploma, como no secPed: quem verificou e quem assinou ficam registados (não se desfaz).
    verified_by_id = fields.Many2one('res.users', string='Verificado por', readonly=True, copy=False, tracking=True)
    verified_date = fields.Datetime(string='Verificado em', readonly=True, copy=False)
    signed_by_id = fields.Many2one('res.users', string='Assinado por', readonly=True, copy=False, tracking=True)
    signed_date = fields.Datetime(string='Assinado em', readonly=True, copy=False)
    diploma_state = fields.Selection(
        [('to_verify', 'Por verificar'), ('to_sign', 'Verificado, falta assinar'), ('signed', 'Assinado')],
        string='Diploma',
        compute='_compute_diploma_state',
        store=True,
    )

    _year_result_uniq = models.Constraint('UNIQUE(year_result_id)', 'A conclusão deste ano já está registada.')

    @api.constrains('year_result_id', 'student_id')
    def _check_graduated(self):
        for graduation in self:
            result = graduation.year_result_id
            if result.student_id != graduation.student_id:
                raise ValidationError(self.env._('O resultado do ano é de outro aluno.'))
            if result.status not in ('graduated', 'promoted') or (
                result.status == 'promoted' and not result._policy()._rules(result.class_id).terminal
            ):
                raise ValidationError(
                    self.env._('%s não concluiu o curso neste ano lectivo.', graduation.student_id.name)
                )

    @api.depends('verified_by_id', 'signed_by_id')
    def _compute_diploma_state(self):
        for graduation in self:
            graduation.diploma_state = (
                'signed' if graduation.signed_by_id else 'to_sign' if graduation.verified_by_id else 'to_verify'
            )

    _PROTECTED = frozenset(
        {
            'plan_average', 'final_grade', 'diploma_number', 'state', 'verified_by_id', 'verified_date',
            'signed_by_id', 'signed_date',
        }
    )  # fmt: skip

    @api.model_create_multi
    def create(self, vals_list):
        if not is_trusted(self.env) and any(self._PROTECTED & set(vals) for vals in vals_list):
            raise AccessError(self.env._('A classificação e o diploma calculam-se e emitem-se pelas acções.'))
        return super().create(vals_list)

    def write(self, vals):
        """Classificação, número do diploma, estado, verificação e assinatura só pelas acções (calcular, emitir,
        verificar, assinar, anular); depois de emitida, o estágio, a PAP e o resultado do ano já não mudam."""
        if not is_trusted(self.env):
            if self._PROTECTED & set(vals):
                raise AccessError(self.env._('A classificação e o diploma calculam-se e emitem-se pelas acções.'))
            frozen = {'internship_id', 'final_project_id', 'year_result_id', 'student_id', 'date'} & set(vals)
            if frozen and self.filtered(lambda g: g.state != 'draft'):
                raise UserError(self.env._('A conclusão já foi emitida: não pode ser alterada.'))
        return super().write(vals)

    def action_mark_verified(self):
        for graduation in self:
            if graduation.state != 'issued':
                raise UserError(self.env._('Emita a conclusão antes de verificar o diploma.'))
            if not graduation.verified_by_id:
                with trusted(self.env):
                    graduation.write({'verified_by_id': self.env.uid, 'verified_date': fields.Datetime.now()})
        return True

    def action_mark_signed(self):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('Só a direcção marca o diploma como assinado.'))
        for graduation in self:
            if not graduation.verified_by_id:
                raise UserError(self.env._('O diploma tem de ser verificado antes de ser assinado.'))
            if not graduation.signed_by_id:
                with trusted(self.env):
                    graduation.write({'signed_by_id': self.env.uid, 'signed_date': fields.Datetime.now()})
        return True

    def _compute_final_result_ids(self):
        for graduation in self:
            graduation.final_result_ids = graduation._final_results()

    def _final_results(self):
        """Classificação final de cada disciplina do curso: a do último ano em que foi leccionada."""
        self.ensure_one()
        results = (
            self.env['edu.subject.result']
            .sudo()
            .search(
                [
                    ('student_id', '=', self.student_id.id),
                    ('complete', '=', True),
                    ('class_id.course_id', '=', self.course_id.id),
                ]
            )
        )
        latest = {}
        for result in results.sorted(lambda r: r.academic_year_id.date_start):
            latest[result.subject_id] = result
        return results.browse([result.id for result in latest.values()])

    def action_compute(self):
        """PC = média das classificações finais das disciplinas (CFD), o estágio incluído, que é uma disciplina do
        curso; classificação final pela fórmula da escola. Na fórmula (4 × PC + EC + PAP) / 6 o estágio conta só como
        EC, para não entrar duas vezes."""
        for graduation in self:
            if graduation.state != 'draft':
                raise UserError(self.env._('A conclusão já foi emitida.'))
            results = graduation._final_results()
            policy = graduation.year_result_id._policy()
            internship = graduation.internship_id.grade if graduation.internship_id else None
            if policy.course_formula == 'internship':
                internship_results = results.filtered(lambda r: r._component() == 'internship')
                results -= internship_results
                if internship is None and internship_results:
                    last = internship_results[-1]
                    internship = last.cfd or last.final
            finals = [r.cfd if r.cfd else r.final for r in results]
            pc = grading.round_units(grading.mean(finals)) if finals else None
            final = grading.course_final(
                pc,
                pap=graduation.final_project_id.grade if graduation.final_project_id else None,
                internship=internship,
                formula=policy.course_formula,
            )
            with trusted(self.env):
                graduation.write({'plan_average': pc or 0.0, 'final_grade': final or 0.0})
        return True

    def action_issue(self):
        """Emite: número de diploma sequencial na escola (ano/sequência)."""
        for graduation in self:
            if graduation.state != 'draft':
                continue
            graduation.action_compute()
            course = graduation.course_id
            if graduation.internship_id.state not in (False, 'passed') or graduation.final_project_id.state not in (
                False,
                'passed',
            ):
                raise UserError(self.env._('O estágio e a PAP da conclusão têm de estar aprovados.'))
            if course.requires_final_project and not graduation.final_project_id:
                raise UserError(self.env._('O curso exige a PAP aprovada.'))
            if course.requires_internship and not graduation.internship_id:
                raise UserError(self.env._('O curso exige o estágio curricular aprovado.'))
            sequence = graduation._diploma_sequence()
            with trusted(self.env):
                graduation.write(
                    {
                        'diploma_number': sequence.with_context(ir_sequence_date=graduation.date).next_by_id(),
                        'state': 'issued',
                    }
                )
        return True

    def action_cancel(self):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('Só a direcção anula uma conclusão emitida.'))
        with trusted(self.env):
            self.write({'state': 'cancelled'})
        return True

    def _diploma_sequence(self):
        self.ensure_one()
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search([('code', '=', 'edu.graduation'), ('company_id', '=', self.company_id.id)], limit=1)
        return sequence or Sequence.create(
            {
                'name': self.env._('Diplomas (%s)', self.company_id.name),
                'code': 'edu.graduation',
                'company_id': self.company_id.id,
                'implementation': 'no_gap',
                'prefix': '%(year)s/',
                'padding': 4,
                'use_date_range': True,
            }
        )


class EduYearResult(models.Model):
    _inherit = 'edu.year.result'

    graduation_id = fields.Many2one('edu.graduation', string='Conclusão', compute='_compute_graduation_id')

    def _compute_graduation_id(self):
        Graduation = self.env['edu.graduation'].sudo()
        for result in self:
            result.graduation_id = Graduation.search([('year_result_id', '=', result.id)], limit=1)

    def _passed_training(self):
        """O estágio e a PAP aprovados deste curso e escola (os mais recentes, se houver mais de um)."""
        domain = [
            ('student_id', '=', self.student_id.id),
            ('state', '=', 'passed'),
            ('course_id', '=', self.enrollment_id.course_id.id),
            ('company_id', '=', self.company_id.id),
        ]
        order = 'academic_year_id desc, id desc'
        return (
            self.env['edu.internship'].search(domain, order=order, limit=1),
            self.env['edu.final.project'].search(domain, order=order, limit=1),
        )

    def _register_graduation(self):
        """Regista (ou reaproveita) a conclusão do curso deste resultado, com o estágio e a PAP aprovados."""
        self.ensure_one()
        graduation = self.graduation_id or self.env['edu.graduation'].create(
            {'student_id': self.student_id.id, 'year_result_id': self.id}
        )
        if graduation.state == 'draft':
            internship, project = self._passed_training()
            graduation.write(
                {
                    'internship_id': graduation.internship_id.id or internship.id,
                    'final_project_id': graduation.final_project_id.id or project.id,
                }
            )
            graduation.action_compute()
        return graduation

    def action_register_graduation(self):
        self.ensure_one()
        graduation = self._register_graduation()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.graduation',
            'res_id': graduation.id,
            'view_mode': 'form',
        }


class EduCourse(models.Model):
    _inherit = 'edu.course'

    training_area = fields.Char(
        string='Área de formação', help='Escreve-se no diploma e no certificado (por exemplo «Saúde» ou «Informática»).'
    )
