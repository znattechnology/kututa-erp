from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

MATRICULA_SEQUENCE = 'edu.student.matricula'


class EduStudent(models.Model):
    _name = 'edu.student'
    _description = 'Aluno'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'res.partner': 'partner_id'}
    _order = 'name'
    _check_company_auto = True
    _rec_names_search = ['name', 'matricula_number', 'id_number']

    partner_id = fields.Many2one('res.partner', string='Contacto', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    # Número de matrícula: imutável e vitalício, «<ano da 1.ª matrícula>-<sequência>», a sequência nunca reinicia.
    matricula_number = fields.Char(string='N.º de matrícula', readonly=True, copy=False, tracking=True, index=True)
    matricula_year = fields.Integer(string='Ano da 1.ª matrícula', readonly=True, copy=False)
    matricula_seq = fields.Integer(string='Ordem de matrícula', readonly=True, copy=False)
    enrollment_date = fields.Date(string='Data da 1.ª matrícula', copy=False)
    birth_date = fields.Date(string='Data de nascimento', tracking=True)
    age = fields.Integer(string='Idade', compute='_compute_age')
    gender = fields.Selection([('male', 'Masculino'), ('female', 'Feminino')], string='Sexo')
    id_number = fields.Char(string='N.º do BI / passaporte', tracking=True)
    id_issuer = fields.Char(string='Emitido por', help='Arquivo de Identificação que emitiu o BI.')
    id_issue_date = fields.Date(string='Data de emissão')
    birthplace = fields.Char(string='Naturalidade', help='Local ou município de nascimento.')
    birth_state_id = fields.Many2one(
        'res.country.state', string='Província de naturalidade', domain="[('country_id.code', '=', 'AO')]"
    )
    nationality_id = fields.Many2one(
        'res.country', string='Nacionalidade', default=lambda self: self.env.ref('base.ao')
    )
    father_name = fields.Char(string='Nome do pai')
    mother_name = fields.Char(string='Nome da mãe')
    special_needs = fields.Text(string='Necessidades educativas especiais')
    guardian_link_ids = fields.One2many('edu.student.guardian', 'student_id', string='Encarregados')
    primary_guardian_id = fields.Many2one(
        'edu.guardian', string='Encarregado principal', compute='_compute_primary_guardian_id', store=True
    )
    active = fields.Boolean(default=True)

    _matricula_company_uniq = models.Constraint(
        'UNIQUE(company_id, matricula_number)', 'Este número de matrícula já existe nesta escola.'
    )
    _id_number_company_uniq = models.Constraint(
        'UNIQUE(company_id, id_number)', 'Já existe um aluno com este número de BI nesta escola.'
    )

    @api.depends('birth_date')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for student in self:
            student.age = relativedelta(today, student.birth_date).years if student.birth_date else 0

    @api.depends('guardian_link_ids.is_primary', 'guardian_link_ids.guardian_id')
    def _compute_primary_guardian_id(self):
        for student in self:
            student.primary_guardian_id = student.guardian_link_ids.filtered('is_primary')[:1].guardian_id

    @api.depends('name', 'matricula_number')
    def _compute_display_name(self):
        for student in self:
            student.display_name = (
                f'{student.matricula_number} · {student.name}' if student.matricula_number else student.name
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('is_company', False)
            vals.setdefault('type', 'contact')
        students = super().create(vals_list)
        for student in students:
            if student.partner_id.company_id and student.partner_id.company_id != student.company_id:
                continue
            # Em sudo: mudar a empresa do contacto faz verificações noutros módulos (o stock procura lotes) que a
            # secretaria não pode ler.
            student.partner_id.sudo().company_id = student.company_id
        return students

    @api.constrains('birth_date')
    def _check_birth_date(self):
        today = fields.Date.context_today(self)
        for student in self:
            if student.birth_date and student.birth_date > today:
                raise ValidationError(self.env._('A data de nascimento de %s é futura.', student.name))

    def write(self, vals):
        if self.env.context.get('edu_matricula_import'):
            return super().write(vals)
        locked = {'matricula_number', 'matricula_year', 'matricula_seq'} & set(vals)
        if locked and self.filtered('matricula_number'):
            raise UserError(self.env._('O número de matrícula é vitalício e não se altera.'))
        return super().write(vals)

    def _matricula_sequence(self):
        self.ensure_one()
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search(
            [('code', '=', MATRICULA_SEQUENCE), ('company_id', '=', self.company_id.id)], limit=1
        )
        if not sequence:
            last = max(
                self.with_context(active_test=False)
                .search([('company_id', '=', self.company_id.id)])
                .mapped('matricula_seq')
                or [0]
            )
            sequence = Sequence.create(
                {
                    'name': self.env._('Números de matrícula (%s)', self.company_id.name),
                    'code': MATRICULA_SEQUENCE,
                    'company_id': self.company_id.id,
                    'implementation': 'no_gap',
                    'number_next': last + 1,
                    'padding': 0,
                }
            )
        return sequence

    def _assign_matricula_number(self, year=None, date=None):
        """Atribui o número de matrícula na 1.ª matrícula: ano lectivo de início e a ordem global na escola."""
        for student in self.filtered(lambda s: not s.matricula_number):
            year = year or fields.Date.context_today(student).year
            seq = int(student._matricula_sequence().next_by_id())
            student.with_context(edu_matricula_import=True).write(
                {
                    'matricula_seq': seq,
                    'matricula_year': year,
                    'matricula_number': f'{year}-{seq:04d}',
                    'enrollment_date': student.enrollment_date or date or fields.Date.context_today(student),
                }
            )
        return True

    def action_assign_matricula_number(self):
        year = self.env.company.edu_current_year_id.date_start.year if self.env.company.edu_current_year_id else None
        return self._assign_matricula_number(year=year)

    @api.model
    def _sync_matricula_sequence(self, company):
        """Depois de importar números (migração), a sequência continua a seguir ao maior já usado."""
        last = max(
            self.with_context(active_test=False).search([('company_id', '=', company.id)]).mapped('matricula_seq')
            or [0]
        )
        sequence = self.new({'company_id': company.id})._matricula_sequence()
        if sequence.number_next_actual <= last:
            sequence.number_next = last + 1
        return sequence

    @api.ondelete(at_uninstall=False)
    def _unlink_except_matriculated(self):
        if self.filtered('matricula_number'):
            raise UserError(self.env._('Um aluno com número de matrícula não se elimina: arquive-o.'))

    def unlink(self):
        partners = self.partner_id
        result = super().unlink()
        partners.filtered(lambda p: not p.user_ids).unlink()
        return result


class EduStudentGuardian(models.Model):
    _name = 'edu.student.guardian'
    _description = 'Encarregado do aluno'
    _order = 'is_primary desc, id'
    _check_company_auto = True

    student_id = fields.Many2one('edu.student', string='Aluno', required=True, ondelete='cascade', index=True)
    guardian_id = fields.Many2one(
        'edu.guardian', string='Encarregado', required=True, ondelete='restrict', index=True, check_company=True
    )
    company_id = fields.Many2one(related='student_id.company_id', store=True, index=True)
    relationship = fields.Selection(
        [
            ('father', 'Pai'),
            ('mother', 'Mãe'),
            ('stepfather', 'Padrasto'),
            ('stepmother', 'Madrasta'),
            ('grandparent', 'Avô / avó'),
            ('sibling', 'Irmão / irmã'),
            ('uncle_aunt', 'Tio / tia'),
            ('legal_guardian', 'Tutor legal'),
            ('other', 'Outro'),
        ],
        string='Parentesco',
        required=True,
        default='legal_guardian',
    )
    is_primary = fields.Boolean(string='Principal', help='Encarregado de educação; recebe as facturas das propinas.')
    is_emergency = fields.Boolean(string='Emergência')
    can_pickup = fields.Boolean(string='Pode recolher o aluno', default=True)
    can_access_portal = fields.Boolean(string='Acesso ao portal', default=True)
    receive_notifications = fields.Boolean(string='Recebe avisos', default=True)
    phone = fields.Char(related='guardian_id.phone')

    _student_guardian_uniq = models.Constraint(
        'UNIQUE(student_id, guardian_id)', 'Este encarregado já está associado ao aluno.'
    )
    _one_primary = models.UniqueIndex('(student_id) WHERE is_primary IS TRUE')

    @api.model_create_multi
    def create(self, vals_list):
        links = super().create(vals_list)
        # O primeiro encarregado de um aluno é o principal.
        for link in links.filtered(lambda link: not link.is_primary):
            if not (link.student_id.guardian_link_ids - link).filtered('is_primary'):
                link.is_primary = True
        return links

    def action_make_primary(self):
        self.ensure_one()
        (self.student_id.guardian_link_ids - self).filtered('is_primary').write({'is_primary': False})
        self.is_primary = True
        return True
