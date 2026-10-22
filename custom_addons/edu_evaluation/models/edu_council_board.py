from odoo import api, models
from odoo.exceptions import UserError

ENROLLED = ('active', 'irregular', 'completed', 'retained')


class EduCouncilSession(models.Model):
    """Ecrã do conselho de turma (acção cliente ``edu_evaluation.council_board``), como o do secPed-Express: a grelha
    da turma (alunos × disciplinas) com as notas a cores, os casos limite que se votam ou o professor sobe, as votações
    abertas com o voto de cada um e o quórum, e o encerramento. O director de turma vê todas as disciplinas; o
    professor, as suas."""

    _inherit = 'edu.council.session'

    @api.model
    def board_for_class(self, class_id):
        """A sessão da turma (criada «por iniciar» se ainda não existir) e os dados do ecrã."""
        edu_class = self.env['edu.class'].browse(class_id).exists()
        if not edu_class:
            raise UserError(self.env._('A turma já não existe.'))
        session = self.search([('class_id', '=', edu_class.id)], limit=1) or self.sudo().create(
            {'class_id': edu_class.id}
        ).with_env(self.env)
        return session.board_data()

    @api.model
    def board_classes(self):
        """As turmas do ano em curso que o utilizador pode abrir: o director e os professores, as suas; a secretaria e
        a direcção, todas."""
        year = self.env['edu.academic.year'].search(
            [('is_current', '=', True), ('company_id', 'in', self.env.companies.ids)], limit=1
        )
        classes = self.env['edu.class'].search([('academic_year_id', '=', year.id)]) if year else []
        employee = self.env.user.employee_id
        staff = self.env.user.has_group('edu_core.group_edu_user')
        result = []
        for edu_class in classes.sorted(lambda c: (c.class_number, c.course_id.code or '', c.name or '')):
            directs = bool(employee) and edu_class.sudo().director_id == employee
            teaches = bool(employee) and employee in edu_class.sudo().assignment_ids.teacher_id
            if staff or directs or teaches:
                result.append({'id': edu_class.id, 'name': edu_class._editor_label(), 'directs': directs})
        return result

    def board_data(self):
        self.ensure_one()
        session = self.sudo()
        edu_class = session.class_id
        employee = self.env.user.employee_id
        is_director = self._is_director()
        mine = edu_class.assignment_ids.filtered(lambda a: a.teacher_id == employee).subject_id
        results = self.env['edu.subject.result'].sudo().search([('class_id', '=', edu_class.id)])
        lines = edu_class.subject_line_ids.filtered('weekly_hours').subject_id | results.subject_id
        staff = self.env.user.has_group('edu_core.group_edu_user')
        subjects = lines if (is_director or staff) else lines & mine
        subjects = subjects.sorted('name')
        enrollments = edu_class.enrollment_ids.filtered(lambda e: e.state in ENROLLED).sorted('order_number')
        by_key = {(r.enrollment_id.id, r.subject_id.id): r for r in results}
        open_votes = session.vote_ids.filtered(lambda v: v.state == 'open')
        vote_by_result = {v.result_id.id: v for v in open_votes}
        pass_grade = results[:1]._policy().pass_grade if results else 10

        def my_ballot(vote):
            ballot = vote.ballot_ids.filtered(lambda b: b.teacher_id == employee)
            return None if not ballot else ('favor' if ballot.in_favor else 'against')

        def vote_data(vote):
            return {
                'id': vote.id,
                'result_id': vote.result_id.id,
                'student': vote.student_id.name,
                'subject': vote.subject_id.name,
                'base': vote.base,
                'favor': vote.favor,
                'against': vote.against,
                'voted': len(vote.ballot_ids),
                'quorum': vote._quorum(),
                'my_ballot': my_ballot(vote),
            }

        students = []
        for enrollment in enrollments:
            cells = []
            for subject in subjects:
                result = by_key.get((enrollment.id, subject.id))
                if not result:
                    cells.append({'subject_id': subject.id, 'result_id': False})
                    continue
                vote = vote_by_result.get(result.id)
                cells.append(
                    {
                        'subject_id': subject.id,
                        'result_id': result.id,
                        'base': result.annual,
                        'final': result.final,
                        'points': result.council_points,
                        'source': result.council_source,
                        'complete': result.complete,
                        'passed': result.final >= pass_grade if result.complete else False,
                        'borderline': result.borderline,
                        'can_teach': subject in mine,
                        'vote_id': vote.id if vote else False,
                    }
                )
            students.append(
                {
                    'id': enrollment.id,
                    'number': enrollment.order_number,
                    'name': enrollment.student_id.name,
                    'cells': cells,
                }
            )
        members = session._members()
        return {
            'session': {
                'id': session.id,
                'state': session.state,
                'class': edu_class._editor_label(),
                'class_id': edu_class.id,
                'director': edu_class.director_id.name or False,
                'technical': edu_class.level_id.subsystem == 'technical',
                'members': len(members),
                'quorum': -(-len(members) // 2) if edu_class.level_id.subsystem == 'technical' else 0,
                'realized_date': session.realized_date and session.realized_date.strftime('%d/%m/%Y') or False,
            },
            'is_director': is_director,
            'is_member': bool(employee) and employee in members,
            'can_print': hasattr(self, 'action_print_acta') and is_director,
            'pass_grade': pass_grade,
            'subjects': [{'id': s.id, 'name': s.name, 'code': s.code or s.name[:4]} for s in subjects],
            'students': students,
            'votes': [vote_data(v) for v in open_votes.sorted('id')],
        }

    # Acções do ecrã: as mesmas regras dos botões dos formulários.

    def board_start(self):
        self.action_start()
        return self.board_data()

    def board_open_vote(self, result_id):
        self.ensure_one()
        self.action_open_vote(self.env['edu.subject.result'].sudo().browse(result_id))
        return self.board_data()

    def board_cast(self, vote_id, in_favor):
        self.ensure_one()
        vote = self.vote_ids.filtered(lambda v: v.id == vote_id)
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(self.env._('Só os professores da turma podem votar.'))
        vote.sudo().cast(employee, in_favor)
        return self.board_data()

    def board_close_vote(self, vote_id):
        self.ensure_one()
        vote = self.vote_ids.filtered(lambda v: v.id == vote_id)
        self._check_director(self.env._('Apenas o director de turma pode apurar as votações.'))
        message = vote.sudo().action_close()
        return {'message': message, 'data': self.board_data()}

    def board_grant(self, result_id):
        self.ensure_one()
        self._check_running()
        self.env['edu.subject.result'].browse(result_id).action_grant_two()
        return self.board_data()

    def board_remove_points(self, result_id):
        self.ensure_one()
        self._check_running()
        self.env['edu.subject.result'].browse(result_id).action_remove_points()
        return self.board_data()

    def board_realize(self):
        self.action_realize()
        return self.board_data()
