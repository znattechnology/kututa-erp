from odoo import api, fields, models
from odoo.exceptions import UserError

CLOSED = ('dropped', 'transferred')
LINE_STATES = [
    ('confirm', 'A confirmar'),
    ('done', 'Confirmada'),
    ('pending', 'Pendente'),
    ('excluded', 'Fora da confirmação'),
]


class EduEnrollmentConfirmation(models.TransientModel):
    """Confirmação de matrículas do ano seguinte, feita pela escola (DP 162/23, arts. 24.º, n.º 2 e 27.º, n.º 3; DP
    167/23, art. 50.º, n.º 4): fecha as matrículas do ano que acaba pelo resultado, cria as turmas do ano seguinte e
    confirma cada aluno na classe que lhe cabe. O resultado é uma lista — confirmados, pendentes (com o que falta) e
    fora da confirmação (com o porquê) — e cada aluno é tratado à parte: um caso com problema não trava os outros."""

    _name = 'edu.enrollment.confirmation'
    _description = 'Confirmação de matrículas'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    source_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano que acaba',
        required=True,
        default=lambda self: self._default_years()[0],
        domain="[('company_id', '=', company_id)]",
    )
    target_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano a confirmar',
        required=True,
        default=lambda self: self._default_years()[1],
        domain="[('company_id', '=', company_id)]",
    )
    create_classes = fields.Boolean(
        string='Criar as turmas que faltam',
        default=True,
        help='A classe seguinte de cada turma (mesmo nome, capacidade, turno e sala) e as da classe de entrada.',
    )
    state = fields.Selection([('draft', 'Preparar'), ('prepared', 'Rever'), ('done', 'Concluída')], default='draft')
    line_ids = fields.One2many('edu.enrollment.confirmation.line', 'wizard_id', string='Alunos')
    summary = fields.Char(compute='_compute_summary')
    classes_created = fields.Integer(readonly=True)

    @api.model
    def _default_years(self):
        """O ano em curso e o seguinte; se o seguinte ainda não existir, o anterior e o em curso."""
        Year = self.env['edu.academic.year']
        current = Year.search([('is_current', '=', True), ('company_id', '=', self.env.company.id)], limit=1)
        if not current:
            return Year, Year
        following = Year.search(
            [('company_id', '=', current.company_id.id), ('date_start', '>', current.date_start)],
            order='date_start',
            limit=1,
        )
        if following:
            return current, following
        previous = Year.search(
            [('company_id', '=', current.company_id.id), ('date_start', '<', current.date_start)],
            order='date_start desc',
            limit=1,
        )
        return previous, current

    @api.depends('source_year_id', 'target_year_id')
    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = self.env._(
                'Confirmação de matrículas %(from_year)s → %(to_year)s',
                from_year=wizard.source_year_id.name or '',
                to_year=wizard.target_year_id.name or '',
            )

    @api.depends('line_ids.state')
    def _compute_summary(self):
        labels = dict(LINE_STATES)
        for wizard in self:
            counts = {}
            for line in wizard.line_ids:
                counts[line.state] = counts.get(line.state, 0) + 1
            wizard.summary = ' · '.join(f'{labels[s]}: {n}' for s, n in counts.items()) or False

    def _reopen(self):
        return True  # o formulário recarrega-se no mesmo sítio (sem nova entrada no caminho)

    def action_prepare(self):
        self.ensure_one()
        if self.target_year_id.date_start <= self.source_year_id.date_start:
            raise UserError(self.env._('O ano a confirmar tem de ser posterior ao ano que acaba.'))
        Enrollment = self.env['edu.enrollment']
        previous = Enrollment.search([('academic_year_id', '=', self.source_year_id.id), ('state', '!=', 'draft')])
        previous._edu_close_year()
        if self.create_classes:
            created = self.env['edu.class']._create_next_year_classes(self.source_year_id, self.target_year_id)
            self.classes_created = len(created)
        self.line_ids.unlink()
        lines = []
        for enrollment in previous.sorted(lambda e: (e.class_id.class_number, e.class_id.name, e.order_number)):
            proposal = self._proposal(enrollment)
            proposal.pop('_no_class', None)
            lines.append(proposal)
        self.line_ids = [(0, 0, vals) for vals in lines]
        self.state = 'prepared'
        return self._reopen()

    def _proposal(self, previous):
        """O que cabe a um aluno: a classe seguinte, a mesma (retido) ou ficar de fora, e porquê. As regras vêem-se
        pela ordem: a primeira que se aplica decide."""
        vals = {'student_id': previous.student_id.id, 'previous_enrollment_id': previous.id}
        year = self.target_year_id
        result = previous.sudo().year_result_id
        # A decisão do ano manda (a direcção pode tê-la mudado depois do fecho).
        retained = result.status == 'retained' if result else previous.state == 'retained'
        number = previous.class_number + (0 if retained else 1)
        rules = [
            (
                lambda: previous.student_id.enrollment_ids.filtered(
                    lambda e: e.academic_year_id == year and e.state not in CLOSED
                ),
                'excluded',
                lambda: self.env._('Já tem matrícula em %s.', year.name),
            ),
            (
                lambda: previous.state in CLOSED,
                'excluded',
                lambda: dict(previous._fields['state'].selection)[previous.state],
            ),
            (
                lambda: previous.state in ('active', 'irregular'),
                'pending',
                lambda: (
                    self.env._('O ano ainda não fechou: %s.', dict(result._fields['status'].selection)[result.status])
                    if result
                    else self.env._('Sem resultado do ano.')
                ),
            ),
            (
                lambda: not retained and number == 10 and previous.course_id.level_id.subsystem != 'technical',
                'excluded',
                lambda: self.env._('Passa ao II Ciclo: faz nova matrícula (DP 162/23, art. 24.º, n.º 9).'),
            ),
            (
                lambda: result.status == 'graduated' or (previous.state == 'completed' and previous._edu_is_terminal()),
                'excluded',
                lambda: self.env._('Concluiu o curso.'),
            ),
            (
                lambda: retained and result.absence_excluded and previous.class_number >= 10,
                'excluded',
                lambda: self.env._(
                    'Reprovado por faltas injustificadas no II Ciclo: sem direito a matrícula no ano seguinte, só a '
                    'exame (DP 162/23, art. 24.º, n.º 4).'
                ),
            ),
            (
                lambda: retained and result.absence_excluded,
                'pending',
                lambda: self.env._(
                    'Reprovado por faltas: confirma-se depois de justificadas, até à 2.ª semana de aulas '
                    '(DP 162/23, art. 24.º, n.º 3).'
                ),
            ),
        ]
        for applies, state, reason in rules:
            if applies():
                return {**vals, 'state': state, 'reason': reason()}
        target = self._target_class(previous, number)
        if not target:
            return {
                **vals,
                '_no_class': True,
                'state': 'pending',
                'reason': self.env._(
                    'Não há turma da %(number)sª classe de %(course)s em %(year)s.',
                    number=number,
                    course=previous.course_id.name,
                    year=year.name,
                ),
            }
        return {**vals, 'state': 'confirm', 'target_class_id': target.id}

    def _target_class(self, previous, number):
        """A turma com o mesmo nome (10.ª A → 11.ª A); sem ela, a do mesmo curso e classe com mais vagas."""
        classes = self.env['edu.class'].search(
            [
                ('academic_year_id', '=', self.target_year_id.id),
                ('course_id', '=', previous.course_id.id),
                ('class_number', '=', number),
            ]
        )
        same = classes.filtered(lambda c: c.name == previous.class_id.name)
        return same[:1] or classes.sorted(lambda c: c.seats_available, reverse=True)[:1]

    def action_confirm(self):
        self.ensure_one()
        for line in self.line_ids.filtered(lambda line: line.state == 'confirm'):
            line._confirm()
        self.state = 'done'
        return self._reopen()


class EduEnrollmentConfirmationLine(models.TransientModel):
    _name = 'edu.enrollment.confirmation.line'
    _description = 'Confirmação de matrícula (aluno)'
    _order = 'state_order, id'

    wizard_id = fields.Many2one('edu.enrollment.confirmation', required=True, ondelete='cascade')
    student_id = fields.Many2one('edu.student', string='Aluno', required=True)
    previous_enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula anterior')
    previous_class_id = fields.Many2one(related='previous_enrollment_id.class_id', string='Turma anterior')
    previous_state = fields.Selection(related='previous_enrollment_id.state', string='Situação')
    target_class_id = fields.Many2one(
        'edu.class',
        string='Turma de destino',
        domain="[('academic_year_id', '=', parent.target_year_id)]",
    )
    state = fields.Selection(LINE_STATES, string='Estado', required=True, default='confirm')
    state_order = fields.Integer(compute='_compute_state_order', store=True)
    reason = fields.Char(string='Motivo')
    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula criada', readonly=True)

    @api.depends('state')
    def _compute_state_order(self):
        order = {'pending': 0, 'confirm': 1, 'done': 2, 'excluded': 3}
        for line in self:
            line.state_order = order[line.state]

    def _confirm(self):
        """Cria e activa a matrícula com as regras de sempre (vagas, retenções, disciplinas em atraso, dívida); se
        alguma falhar, a linha fica pendente com a mensagem, e os outros alunos seguem."""
        self.ensure_one()
        previous = self.previous_enrollment_id
        target = self.target_class_id
        if not target:
            self.write({'state': 'pending', 'reason': self.env._('Indique a turma de destino.')})
            return
        try:
            with self.env.cr.savepoint():
                enrollment = self.env['edu.enrollment'].create(
                    {
                        'student_id': self.student_id.id,
                        'class_id': target.id,
                        'previous_enrollment_id': previous.id,
                        'enrollment_type': 'repeat' if target.class_number == previous.class_number else 'renewal',
                    }
                )
                enrollment.action_confirm()
        except UserError as error:
            self.write({'state': 'pending', 'reason': str(error.args[0] if error.args else error)})
            return
        notes = enrollment._edu_propose_lower_subjects(previous)
        if notes:
            notes = [self.env._('Na classe anterior (Decreto Executivo 60/08): %s', '; '.join(notes))]
        reason = '\n'.join(filter(None, [enrollment.warning, *notes])) or False
        self.write({'state': 'done', 'enrollment_id': enrollment.id, 'reason': reason})

    def action_retry(self):
        """Depois de resolver o que faltava (exames, turma, faltas justificadas, decisão da direcção), volta a ver o
        aluno: fecha a matrícula anterior se o resultado já existir e confirma-o, se puder."""
        for line in self.filtered(lambda line: line.state == 'pending'):
            line.previous_enrollment_id._edu_close_year()
            proposal = line.wizard_id._proposal(line.previous_enrollment_id)
            if line.target_class_id and (proposal.pop('_no_class', False) or proposal['state'] == 'confirm'):
                proposal.update(state='confirm', target_class_id=line.target_class_id.id)  # a turma escolhida à mão
            line.write({k: v for k, v in proposal.items() if k not in ('student_id', 'previous_enrollment_id')})
            if line.state == 'confirm':
                line._confirm()
        return self.wizard_id._reopen()
