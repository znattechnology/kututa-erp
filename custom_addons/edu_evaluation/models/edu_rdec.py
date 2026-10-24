from odoo import api, fields, models
from odoo.exceptions import ValidationError

RDEC_LEVELS = [
    ('not_satisfactory', 'Não satisfatório'),
    ('satisfactory', 'Satisfatório'),
    ('good', 'Bom'),
    ('very_good', 'Muito bom'),
]
RDEC_STATES = [('todo', 'Por avaliar'), ('progress', 'Em curso'), ('done', 'Completo')]
# As crianças da turma: as matriculadas e, num ano passado, as que o concluíram.
ENROLLED = ('active', 'irregular', 'completed', 'retained')


class EduRdec(models.Model):
    """Relatório de Desempenho Escolar da Criança (iniciação): avaliação qualitativa e descritiva, sem notas e sem
    retenção (Dec. Exec. 424/25, arts. 19.º e 20.º). Um por criança e por trimestre, como no secPed: cada área de
    desenvolvimento (as disciplinas da matrícula) tem um nível e observações, e a criança tem uma apreciação global.
    Escreve-o o(a) educador(a), director(a) da turma; os outros professores e a secretaria consultam e imprimem, e a
    Direcção pode corrigir."""

    _name = 'edu.rdec'
    _description = 'RDEC (iniciação)'
    _inherit = ['mail.thread']
    _order = 'class_id, trimester_id, order_number, id'
    _rec_name = 'student_id'
    _check_company_auto = True

    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', required=True, check_company=True, index=True, ondelete='cascade'
    )
    student_id = fields.Many2one(related='enrollment_id.student_id', store=True, string='Criança')
    matricula_number = fields.Char(related='enrollment_id.student_id.matricula_number', string='N.º de matrícula')
    order_number = fields.Integer(related='enrollment_id.order_number', store=True, string='N.º', aggregator=False)
    class_id = fields.Many2one(related='enrollment_id.class_id', store=True, index=True)
    academic_year_id = fields.Many2one(related='enrollment_id.class_id.academic_year_id', store=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True)
    director_id = fields.Many2one(related='enrollment_id.class_id.director_id', string='Educador(a)')
    trimester_id = fields.Many2one('edu.trimester', string='Trimestre', required=True, index=True)
    appreciation = fields.Text(string='Apreciação global', tracking=True)
    line_ids = fields.One2many('edu.rdec.line', 'rdec_id', string='Áreas de desenvolvimento')
    areas_total = fields.Integer(string='Áreas', compute='_compute_progress', store=True, aggregator=False)
    areas_done = fields.Integer(string='Áreas avaliadas', compute='_compute_progress', store=True, aggregator=False)
    areas_label = fields.Char(string='Avaliadas', compute='_compute_progress')
    progress = fields.Float(string='Progresso', compute='_compute_progress', store=True, aggregator='avg')
    has_appreciation = fields.Boolean(string='Com apreciação', compute='_compute_progress', store=True)
    state = fields.Selection(RDEC_STATES, string='Estado', compute='_compute_progress', store=True, index=True)
    absences_justified = fields.Integer(string='Faltas justificadas', compute='_compute_absences')
    absences_unjustified = fields.Integer(string='Faltas injustificadas', compute='_compute_absences')
    can_edit = fields.Boolean(compute='_compute_can_edit')

    _enrollment_trimester_uniq = models.Constraint(
        'UNIQUE(enrollment_id, trimester_id)', 'A criança já tem RDEC neste trimestre.'
    )

    @api.depends('line_ids.level', 'appreciation')
    def _compute_progress(self):
        for rdec in self:
            total = len(rdec.line_ids)
            done = len(rdec.line_ids.filtered('level'))
            appreciation = bool((rdec.appreciation or '').strip())
            rdec.areas_total = total
            rdec.areas_done = done
            rdec.areas_label = f'{done}/{total}'
            rdec.progress = 100.0 * done / total if total else 0.0
            rdec.has_appreciation = appreciation
            if total and done == total and appreciation:
                rdec.state = 'done'
            elif done or appreciation:
                rdec.state = 'progress'
            else:
                rdec.state = 'todo'

    def _compute_absences(self):
        """Faltas da criança no trimestre, nas aulas realizadas (como no secPed e na pauta)."""
        counts = {}
        if self.ids:
            groups = (
                self.env['edu.lesson.attendance']
                .sudo()
                ._read_group(
                    [
                        ('enrollment_id', 'in', self.enrollment_id.ids),
                        ('trimester_id', 'in', self.trimester_id.ids),
                        ('lesson_state', '!=', 'cancelled'),
                        ('state', 'in', ('absent', 'excused')),
                    ],
                    ['enrollment_id', 'trimester_id', 'state'],
                    ['__count'],
                )
            )
            counts = {(e.id, t.id, state): count for e, t, state, count in groups}
        for rdec in self:
            key = (rdec.enrollment_id.id, rdec.trimester_id.id)
            rdec.absences_justified = counts.get((*key, 'excused'), 0)
            rdec.absences_unjustified = counts.get((*key, 'absent'), 0)

    @api.depends_context('uid')
    @api.depends('class_id.director_id.user_id')
    def _compute_can_edit(self):
        # Como no secPed: escreve o(a) educador(a); a secretaria consulta e imprime. A Direcção pode corrigir.
        manager = self.env.user.has_group('edu_core.group_edu_manager')
        for rdec in self:
            rdec.can_edit = manager or rdec.sudo().class_id.director_id.user_id == self.env.user

    @api.constrains('enrollment_id', 'trimester_id')
    def _check_iniciacao(self):
        for rdec in self:
            edu_class = rdec.enrollment_id.class_id
            if edu_class.level_id.code != 'INICIACAO':
                raise ValidationError(self.env._('O RDEC destina-se apenas às turmas da Iniciação (pré-escolar).'))
            if rdec.trimester_id.academic_year_id != edu_class.academic_year_id:
                raise ValidationError(self.env._('O trimestre não é do ano lectivo da turma.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fill_areas()
        return records

    def _areas(self):
        """As áreas de desenvolvimento: as disciplinas da matrícula (as do plano da turma, se a matrícula não as tiver),
        por ordem alfabética."""
        self.ensure_one()
        subjects = self.enrollment_id.subject_ids or self.enrollment_id.class_id.subject_line_ids.subject_id
        return subjects.sorted(lambda s: s.name or '')

    def _fill_areas(self):
        Line = self.env['edu.rdec.line'].sudo()
        for rdec in self:
            missing = rdec._areas() - rdec.line_ids.subject_id
            Line.create(
                [
                    {'rdec_id': rdec.id, 'subject_id': subject.id, 'sequence': sequence}
                    for sequence, subject in enumerate(missing, len(rdec.line_ids) + 1)
                ]
            )

    def action_fill_areas(self):
        self._fill_areas()
        return True

    # ------------------------------------------------------------------
    # Turma e trimestre: os relatórios das crianças, criados quando se abre a turma
    # ------------------------------------------------------------------
    @api.model
    def _prepare(self, classes, trimesters):
        """Cria os relatórios que faltam (com as áreas) das crianças das turmas da iniciação, nos trimestres dados."""
        Rdec = self.sudo()
        classes = classes.sudo().filtered(lambda c: c.level_id.code == 'INICIACAO')
        existing = set(
            Rdec.search([('class_id', 'in', classes.ids), ('trimester_id', 'in', trimesters.ids)]).mapped(
                lambda r: (r.enrollment_id.id, r.trimester_id.id)
            )
        )
        vals = []
        for edu_class in classes:
            enrollments = edu_class.enrollment_ids.filtered(lambda e: e.state in ENROLLED)
            for trimester in trimesters.filtered(lambda t, c=edu_class: t.academic_year_id == c.academic_year_id):
                vals += [
                    {'enrollment_id': enrollment.id, 'trimester_id': trimester.id}
                    for enrollment in enrollments
                    if (enrollment.id, trimester.id) not in existing
                ]
        return Rdec.create(vals) if vals else Rdec

    @api.model
    def _trimesters(self, year):
        """Os trimestres do ano já começados (todos, num ano passado) e o que abre por omissão: o corrente, ou o último
        começado."""
        trimesters = year.trimester_ids.sorted('number')
        today = fields.Date.context_today(self)
        started = trimesters.filtered(lambda t: t.date_start and t.date_start <= today) or trimesters[:1]
        default = started.filtered('is_current')[:1] or started[-1:]
        return started, default

    @api.model
    def _open_classes(self, classes, title=None):
        """A lista do RDEC das turmas (preparadas), no trimestre corrente; as turmas e os trimestres no painel."""
        years = classes.academic_year_id
        trimesters = self.env['edu.trimester']
        default = self.env['edu.trimester']
        for year in years:
            started, current = self._trimesters(year)
            trimesters |= started
            default = default or current
        self._prepare(classes, trimesters)
        action = self.env['ir.actions.actions']._for_xml_id('edu_evaluation.action_edu_rdec')
        action['domain'] = [('class_id', 'in', classes.ids)]
        action['context'] = {
            'searchpanel_default_trimester_id': default.id,
            'searchpanel_default_class_id': classes.id if len(classes) == 1 else False,
        }
        if title:
            action['name'] = action['display_name'] = title
        return action

    @api.model
    def action_open_rdec(self):
        """Menu «RDEC (iniciação)»: as turmas da iniciação do ano corrente (o professor, as que dirige ou lecciona)."""
        year = self.env.company.edu_current_year_id
        classes = (
            self.env['edu.class']
            .sudo()
            .search([('academic_year_id', '=', year.id), ('level_id.code', '=', 'INICIACAO')])
        )
        if not self.env.user.has_group('edu_core.group_edu_user'):
            employee = self.env.user.employee_id
            classes = classes.filtered(
                lambda c: employee and (c.director_id == employee or employee in c.assignment_ids.teacher_id)
            )
        return self._open_classes(classes)


class EduRdecLine(models.Model):
    _name = 'edu.rdec.line'
    _description = 'Área do RDEC'
    _order = 'rdec_id, sequence, id'

    rdec_id = fields.Many2one('edu.rdec', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    subject_id = fields.Many2one('edu.subject', string='Área de desenvolvimento', required=True)
    level = fields.Selection(RDEC_LEVELS, string='Nível')
    observations = fields.Text(string='Observações')
    company_id = fields.Many2one(related='rdec_id.company_id', store=True)

    _rdec_subject_uniq = models.Constraint('UNIQUE(rdec_id, subject_id)', 'A área já está no relatório.')
