from odoo import fields, models
from odoo.exceptions import UserError

RELATIONSHIPS = [
    ('father', 'Pai'),
    ('mother', 'Mãe'),
    ('stepfather', 'Padrasto'),
    ('stepmother', 'Madrasta'),
    ('grandparent', 'Avô / avó'),
    ('sibling', 'Irmão / irmã'),
    ('uncle_aunt', 'Tio / tia'),
    ('legal_guardian', 'Tutor legal'),
    ('other', 'Outro'),
]
EDITABLE = ('draft', 'submitted', 'review')
REVIEWABLE = ('submitted', 'review')
# Campos que se escrevem depois da decisão; os outros ficam fixos numa candidatura decidida.
DECISION_FIELDS = {
    'state',
    'decision_note',
    'class_id',
    'student_id',
    'enrollment_id',
    'reviewed_by_id',
    'reviewed_date',
    'submitted_date',
    'message_main_attachment_id',
}


class EduApplication(models.Model):
    _name = 'edu.application'
    _description = 'Candidatura'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(string='Candidato(a)', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    state = fields.Selection(
        [
            ('draft', 'Rascunho'),
            ('submitted', 'Submetida'),
            ('review', 'Em análise'),
            ('approved', 'Aprovada'),
            ('rejected', 'Rejeitada'),
            ('cancelled', 'Cancelada'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )
    # Candidato
    birth_date = fields.Date(string='Data de nascimento')
    gender = fields.Selection([('male', 'Masculino'), ('female', 'Feminino')], string='Sexo')
    id_number = fields.Char(string='N.º do BI / passaporte')
    vat = fields.Char(string='NIF')
    birthplace = fields.Char(string='Naturalidade')
    father_name = fields.Char(string='Nome do pai')
    mother_name = fields.Char(string='Nome da mãe')
    street = fields.Char(string='Morada')
    phone = fields.Char(string='Telefone')
    email = fields.Char()
    # Encarregado
    guardian_name = fields.Char(string='Encarregado(a)')
    guardian_phone = fields.Char(string='Telefone do encarregado')
    guardian_email = fields.Char(string='Email do encarregado')
    guardian_vat = fields.Char(string='NIF do encarregado')
    guardian_relationship = fields.Selection(RELATIONSHIPS, string='Parentesco', default='legal_guardian')
    # Pretensão
    previous_school = fields.Char(string='Escola de proveniência')
    academic_year_id = fields.Many2one(
        'edu.academic.year',
        string='Ano lectivo',
        check_company=True,
        default=lambda self: self.env.company.edu_current_year_id,
    )
    desired_level_id = fields.Many2one('edu.level', string='Nível pretendido')
    desired_course_id = fields.Many2one('edu.course', string='Curso pretendido', check_company=True)
    desired_class_number = fields.Integer(string='Classe pretendida')
    transfer_in = fields.Boolean(string='Vem transferido(a) de outra escola')
    # Decisão
    class_id = fields.Many2one(
        'edu.class',
        string='Turma',
        check_company=True,
        domain="[('academic_year_id', '=', academic_year_id)]",
        help='Turma onde o aluno é matriculado na aprovação.',
    )
    submitted_date = fields.Datetime(string='Submetida em', readonly=True, copy=False)
    reviewed_by_id = fields.Many2one('res.users', string='Decidida por', readonly=True, copy=False)
    reviewed_date = fields.Datetime(string='Decidida em', readonly=True, copy=False)
    decision_note = fields.Text(string='Fundamentação')
    student_id = fields.Many2one('edu.student', string='Aluno', readonly=True, copy=False)
    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', readonly=True, copy=False)

    def write(self, vals):
        protected = set(vals) - DECISION_FIELDS
        if protected and self.filtered(lambda a: a.state not in EDITABLE):
            raise UserError(self.env._('Uma candidatura decidida não se altera.'))
        return super().write(vals)

    def action_submit(self):
        for application in self:
            if application.state != 'draft':
                raise UserError(self.env._('Só um rascunho se submete.'))
            application.write({'state': 'submitted', 'submitted_date': fields.Datetime.now()})
        return True

    def action_review(self):
        self.filtered(lambda a: a.state == 'submitted').write({'state': 'review'})
        return True

    def action_reject(self):
        for application in self:
            if application.state not in REVIEWABLE:
                raise UserError(self.env._('Só se rejeita uma candidatura submetida ou em análise.'))
            if not application.decision_note:
                raise UserError(self.env._('Indique a fundamentação da rejeição.'))
            application.write(
                {'state': 'rejected', 'reviewed_by_id': self.env.uid, 'reviewed_date': fields.Datetime.now()}
            )
        return True

    def action_cancel(self):
        if self.filtered(lambda a: a.state == 'approved'):
            raise UserError(self.env._('Uma candidatura aprovada não se cancela: anule a matrícula.'))
        self.write({'state': 'cancelled'})
        return True

    def action_draft(self):
        self.filtered(lambda a: a.state in ('rejected', 'cancelled')).write({'state': 'draft'})
        return True

    def action_approve(self):
        """Cria (ou reutiliza, pelo BI) o aluno e o encarregado e matricula-o na turma escolhida."""
        for application in self:
            if application.state not in REVIEWABLE:
                raise UserError(self.env._('Só se aprova uma candidatura submetida ou em análise.'))
            if not application.class_id:
                raise UserError(self.env._('Escolha a turma onde o aluno fica matriculado.'))
            if application.class_id.academic_year_id != application.academic_year_id:
                raise UserError(self.env._('A turma não é do ano lectivo da candidatura.'))
            student = application._find_or_create_student()
            application._link_guardian(student)
            enrollment = self.env['edu.enrollment'].create(
                {
                    'student_id': student.id,
                    'class_id': application.class_id.id,
                    'enrollment_type': 'transfer_in' if application.transfer_in else 'new',
                    'application_id': application.id,
                }
            )
            enrollment.action_confirm()
            application.write(
                {
                    'state': 'approved',
                    'student_id': student.id,
                    'enrollment_id': enrollment.id,
                    'reviewed_by_id': self.env.uid,
                    'reviewed_date': fields.Datetime.now(),
                }
            )
        return True

    def _find_or_create_student(self):
        self.ensure_one()
        Student = self.env['edu.student'].with_company(self.company_id)
        if self.id_number:
            student = Student.with_context(active_test=False).search(
                [('company_id', '=', self.company_id.id), ('id_number', '=', self.id_number)], limit=1
            )
            if student:
                return student
        return Student.create(
            {
                'name': self.name,
                'company_id': self.company_id.id,
                'birth_date': self.birth_date,
                'gender': self.gender,
                'id_number': self.id_number,
                'vat': self.vat,
                'birthplace': self.birthplace,
                'father_name': self.father_name,
                'mother_name': self.mother_name,
                'street': self.street,
                'phone': self.phone,
                'email': self.email,
            }
        )

    def _link_guardian(self, student):
        self.ensure_one()
        if not (self.guardian_name and self.guardian_phone):
            return
        Guardian = self.env['edu.guardian'].with_company(self.company_id)
        guardian = Guardian.search(
            [('company_id', '=', self.company_id.id), ('phone', '=', self.guardian_phone)], limit=1
        ) or Guardian.create(
            {
                'name': self.guardian_name,
                'company_id': self.company_id.id,
                'phone': self.guardian_phone,
                'email': self.guardian_email,
                'vat': self.guardian_vat,
            }
        )
        if guardian not in student.guardian_link_ids.guardian_id:
            self.env['edu.student.guardian'].create(
                {'student_id': student.id, 'guardian_id': guardian.id, 'relationship': self.guardian_relationship}
            )
