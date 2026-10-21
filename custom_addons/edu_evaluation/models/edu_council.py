from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools.grading import TECHNICAL

COUNCIL_POINTS = 2


class EduCouncilSession(models.Model):
    """Conselho de turma de fim de ano: bonificações dos casos limite e, realizado, fecho da pauta."""

    _name = 'edu.council.session'
    _description = 'Conselho de turma'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    class_id = fields.Many2one('edu.class', string='Turma', required=True, check_company=True)
    company_id = fields.Many2one(related='class_id.company_id', store=True)
    academic_year_id = fields.Many2one(related='class_id.academic_year_id', store=True)
    director_id = fields.Many2one(related='class_id.director_id', string='Director(a) de turma')
    state = fields.Selection(
        [('open', 'Em curso'), ('realized', 'Realizado')], string='Estado', default='open', required=True, tracking=True
    )
    realized_by_id = fields.Many2one('res.users', string='Realizado por', readonly=True)
    realized_date = fields.Datetime(string='Realizado em', readonly=True)
    vote_ids = fields.One2many('edu.council.vote', 'session_id', string='Votações')
    borderline_ids = fields.Many2many('edu.subject.result', string='Casos limite', compute='_compute_borderline_ids')

    _class_uniq = models.Constraint('UNIQUE(class_id)', 'A turma já tem conselho de turma.')

    @api.depends('class_id', 'vote_ids.state')
    def _compute_borderline_ids(self):
        for session in self:
            results = self.env['edu.subject.result'].sudo().search([('class_id', '=', session.class_id.id)])
            session.borderline_ids = results.filtered('borderline')

    def _check_director(self):
        if self.env.user.has_group('edu_core.group_edu_manager'):
            return
        for session in self:
            if session.class_id.director_id.user_id != self.env.user:
                raise UserError(self.env._('Só o director de turma conduz o conselho de turma.'))

    def action_realize(self):
        self._check_director()
        for session in self:
            if session.vote_ids.filtered(lambda v: v.state == 'open'):
                raise UserError(self.env._('Há votações por fechar.'))
            session.write({'state': 'realized', 'realized_by_id': self.env.uid, 'realized_date': fields.Datetime.now()})
            self.env['edu.year.result']._compute_for_classes(session.class_id)
        return True

    def action_reopen(self):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('Só a direcção reabre um conselho de turma realizado.'))
        self.write({'state': 'open', 'realized_by_id': False, 'realized_date': False})
        return True

    def _members(self):
        """Professores da turma (colocados no ano)."""
        self.ensure_one()
        return self.class_id.sudo().assignment_ids.teacher_id

    def action_open_vote(self, result):
        """Abre a votação de +2 valores para um caso limite."""
        self._check_director()
        self.ensure_one()
        if self.state != 'open':
            raise UserError(self.env._('O conselho de turma já foi realizado.'))
        if not result.borderline:
            raise UserError(self.env._('Só se vota um caso limite sem bonificação.'))
        if self.vote_ids.filtered(lambda v: v.state == 'open'):
            raise UserError(self.env._('Feche a votação em curso antes de abrir outra.'))
        return self.env['edu.council.vote'].create(
            {'session_id': self.id, 'result_id': result.id, 'base': result.annual}
        )


class EduCouncilVote(models.Model):
    """Votação nominal, sem abstenção, de +2 valores; aprovada por maioria dos votos (técnico: quórum de 50%)."""

    _name = 'edu.council.vote'
    _description = 'Votação do conselho de turma'
    _order = 'id desc'

    session_id = fields.Many2one('edu.council.session', string='Conselho', required=True, ondelete='cascade')
    result_id = fields.Many2one('edu.subject.result', string='Caso', required=True, ondelete='cascade')
    student_id = fields.Many2one(related='result_id.student_id')
    subject_id = fields.Many2one(related='result_id.subject_id')
    company_id = fields.Many2one(related='session_id.company_id', store=True)
    base = fields.Float(string='Nota de base', digits=(4, 2), readonly=True)
    state = fields.Selection(
        [('open', 'Em votação'), ('applied', 'Aprovada'), ('rejected', 'Rejeitada'), ('cancelled', 'Anulada')],
        default='open',
        required=True,
    )
    ballot_ids = fields.One2many('edu.council.ballot', 'vote_id', string='Votos')
    favor = fields.Integer(string='A favor', compute='_compute_count')
    against = fields.Integer(string='Contra', compute='_compute_count')

    @api.depends('ballot_ids.in_favor')
    def _compute_count(self):
        for vote in self:
            vote.favor = len(vote.ballot_ids.filtered('in_favor'))
            vote.against = len(vote.ballot_ids) - vote.favor

    def cast(self, employee, in_favor):
        """Voto de um professor da turma (repetir altera o voto)."""
        self.ensure_one()
        if self.state != 'open':
            raise UserError(self.env._('A votação está fechada.'))
        if employee not in self.session_id._members():
            raise UserError(self.env._('Só os professores da turma votam.'))
        ballot = self.ballot_ids.filtered(lambda b: b.teacher_id == employee)
        if ballot:
            ballot.in_favor = in_favor
        else:
            self.env['edu.council.ballot'].create({'vote_id': self.id, 'teacher_id': employee.id, 'in_favor': in_favor})

    def action_vote_favor(self):
        self.cast(self.env.user.employee_id, True)

    def action_vote_against(self):
        self.cast(self.env.user.employee_id, False)

    def action_close(self):
        self.session_id._check_director()
        for vote in self.filtered(lambda v: v.state == 'open'):
            members = len(vote.session_id._members())
            regime = vote.result_id._policy().regime
            if regime == TECHNICAL and members and len(vote.ballot_ids) * 2 < members:
                raise UserError(
                    self.env._(
                        'Quórum: votaram %(votes)s de %(members)s professores (mínimo 50%%).',
                        votes=len(vote.ballot_ids),
                        members=members,
                    )  # fmt: skip
                )
            approved = vote.favor * 2 > len(vote.ballot_ids)
            vote.state = 'applied' if approved else 'rejected'
            if approved:
                vote.result_id._set_points(COUNCIL_POINTS, 'council', vote)
        return True


class EduCouncilBallot(models.Model):
    _name = 'edu.council.ballot'
    _description = 'Voto no conselho de turma'

    vote_id = fields.Many2one('edu.council.vote', required=True, ondelete='cascade')
    teacher_id = fields.Many2one('hr.employee', string='Professor(a)', required=True)
    in_favor = fields.Boolean(string='A favor')
    company_id = fields.Many2one(related='vote_id.company_id', store=True)

    _vote_teacher_uniq = models.Constraint('UNIQUE(vote_id, teacher_id)', 'O professor já votou.')
