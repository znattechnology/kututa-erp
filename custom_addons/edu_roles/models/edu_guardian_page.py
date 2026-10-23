from odoo import api, models
from odoo.exceptions import UserError

# O que se escreve no registo do encarregado (o resto do contacto edita-se na ficha do Odoo).
GUARDIAN_FIELDS = ['name', 'phone', 'email', 'id_number', 'vat', 'occupation', 'street', 'city']
LINK_OPTIONS = ['is_primary', 'is_emergency', 'can_pickup', 'can_access_portal', 'receive_notifications']


class EduGuardianPage(models.AbstractModel):
    """Páginas «Encarregados de educação» (acção cliente ``edu_roles.guardians``), como as do secPed-Express: a lista
    (quem são, como se contactam, de que alunos são encarregados), «Criar encarregado», que segue logo para o vincular,
    e «Vincular a aluno» num só ecrã: o aluno (pela turma ou pelo nome, com os encarregados que já tem), o encarregado
    e a relação com as autorizações."""

    _name = 'edu.guardian.page'
    _description = 'Encarregados de educação'

    @api.model
    def _relationships(self):
        Link = self.env['edu.student.guardian']
        return Link._fields['relationship']._description_selection(self.env)

    @api.model
    def _link_row(self, link):
        return {
            'id': link.id,
            'student_id': link.student_id.id,
            'student': link.student_id.name,
            'guardian_id': link.guardian_id.id,
            'guardian': link.guardian_id.name,
            'relationship': dict(self._relationships())[link.relationship],
            'primary': link.is_primary,
        }

    @api.model
    def _row(self, guardian):
        return {
            'id': guardian.id,
            'name': guardian.name,
            'occupation': guardian.occupation or '',
            'phone': guardian.phone or '',
            'email': guardian.email or '',
            'vat': guardian.vat or '',
            'links': [self._link_row(link) for link in guardian.student_link_ids],
        }

    @api.model
    def listing(self):
        guardians = self.env['edu.guardian'].search([('company_id', 'in', self.env.companies.ids)])
        return {'rows': [self._row(g) for g in guardians]}

    @api.model
    def search_guardians(self, query):
        query = (query or '').strip()
        domain = [('company_id', 'in', self.env.companies.ids)]
        if query:
            domain += [
                '|', '|', '|', '|',
                ('name', 'ilike', query),
                ('phone', 'ilike', query),
                ('email', 'ilike', query),
                ('vat', 'ilike', query),
                ('id_number', 'ilike', query),
            ]  # fmt: skip
        return [self._row(g) for g in self.env['edu.guardian'].search(domain, limit=30)]

    @api.model
    def guardian(self, guardian_id):
        guardian = self.env['edu.guardian'].browse(guardian_id).exists()
        if not guardian:
            raise UserError(self.env._('O encarregado já não existe.'))
        return self._row(guardian)

    @api.model
    def create_guardian(self, vals):
        values = {k: (vals.get(k) or '').strip() or False for k in GUARDIAN_FIELDS}
        if not values['name']:
            raise UserError(self.env._('Escreva o nome do encarregado.'))
        if not values['phone']:
            raise UserError(self.env._('Indique o telefone: é por ele que a escola contacta o encarregado.'))
        # O mesmo NIF ou BI é a mesma pessoa: vincula-se o registo que já existe.
        Guardian = self.env['edu.guardian']
        for field, label in (('vat', 'NIF'), ('id_number', 'BI')):
            if values[field]:
                twin = Guardian.search(
                    [('company_id', 'in', self.env.companies.ids), (field, '=', values[field])], limit=1
                )
                if twin:
                    raise UserError(
                        self.env._(
                            '%(name)s já está registado com este %(label)s: vincule esse encarregado.',
                            name=twin.name,
                            label=label,
                        )
                    )
        return self._row(Guardian.create(values))

    @api.model
    def options(self):
        return {'relationships': [{'value': v, 'label': label} for v, label in self._relationships()]}

    @api.model
    def student_guardians(self, student_id):
        student = self.env['edu.student'].browse(student_id).exists()
        if not student:
            raise UserError(self.env._('O aluno já não existe.'))
        return [self._link_row(link) for link in student.guardian_link_ids]

    @api.model
    def link(self, student_id, guardian_id, relationship, options):
        """Vincula o encarregado ao aluno. Um aluno tem um só encarregado principal (o das facturas das propinas): se o
        novo o é, o anterior deixa de ser."""
        student = self.env['edu.student'].browse(student_id).exists()
        guardian = self.env['edu.guardian'].browse(guardian_id).exists()
        if not student or not guardian:
            raise UserError(self.env._('O aluno ou o encarregado já não existe.'))
        if student.guardian_link_ids.filtered(lambda link: link.guardian_id == guardian):
            raise UserError(self.env._('%(g)s já é encarregado de %(s)s.', g=guardian.name, s=student.name))
        values = {k: bool(options.get(k)) for k in LINK_OPTIONS}
        primary = values.pop('is_primary')
        link = self.env['edu.student.guardian'].create(
            {'student_id': student.id, 'guardian_id': guardian.id, 'relationship': relationship, **values}
        )
        if primary and not link.is_primary:
            link.action_make_primary()
        return self._link_row(link)

    @api.model
    def unlink_link(self, link_id):
        link = self.env['edu.student.guardian'].browse(link_id).exists()
        if not link:
            raise UserError(self.env._('O vínculo já não existe.'))
        student = link.student_id
        others = student.guardian_link_ids - link
        link.unlink()
        if others and not others.filtered('is_primary'):
            others[:1].is_primary = True
        return [self._link_row(other) for other in student.guardian_link_ids]
