from odoo import api, fields, models
from odoo.exceptions import UserError

from .edu_document import DECLARATIONS, DOCUMENT_TYPES, IDENTITY_FIELDS
from .report_helpers import Helpers

# Os dados de identificação que a página edita (os de IDENTITY_FIELDS, com o rótulo do formulário).
IDENTITY_LABELS = {
    'father_name': 'Nome do pai',
    'mother_name': 'Nome da mãe',
    'birth_date': 'Data de nascimento',
    'birthplace': 'Naturalidade',
    'birth_state_id': 'Província',
    'id_number': 'Número do BI',
    'id_issuer': 'Arquivo de identificação',
    'id_issue_date': 'Data de emissão do BI',
    'process_number': 'Processo n.º',
}


class EduDeclarationPage(models.AbstractModel):
    """Página «Declarações» (acção cliente ``edu_documents.declarations``), como a do secPed-Express: escolhe-se o
    aluno (``edu.student.picker``: pela turma, com a lista dos alunos, ou pelo nome, no ano lectivo); depois o tipo
    de declaração, completam-se os dados de identificação (ficam na ficha do aluno) e vê-se ou emite-se a
    declaração, que fica no registo (``edu.document``) com o seu número."""

    _name = 'edu.declaration.page'
    _description = 'Declarações'

    @api.model
    def page_options(self):
        angola = self.env.ref('base.ao', raise_if_not_found=False)
        states = self.env['res.country.state'].search([('country_id', '=', angola.id)] if angola else [])
        return {
            'states': [{'id': s.id, 'name': s.name} for s in states.sorted('name')],
            'types': [{'key': k, 'name': n} for k, n in DOCUMENT_TYPES if k in DECLARATIONS],
            'identity_fields': [{'key': k, 'label': IDENTITY_LABELS[k]} for k, _label in IDENTITY_FIELDS],
        }

    # O aluno escolhido

    @api.model
    def student_data(self, enrollment_id, document_type):
        """A matrícula, os dados de identificação, se a declaração pode sair e as já emitidas."""
        enrollment = self.env['edu.enrollment'].browse(enrollment_id).exists()
        if not enrollment:
            raise UserError(self.env._('A matrícula já não existe.'))
        student = enrollment.student_id
        identity = {}
        for key, _label in IDENTITY_FIELDS:
            value = student[key]
            if key == 'birth_state_id':
                identity[key] = value.id or False
            elif key.endswith('date'):
                identity[key] = fields.Date.to_string(value) if value else ''
            else:
                identity[key] = value or ''
        documents = self.env['edu.document'].search(
            [('student_id', '=', student.id), ('document_type', 'in', DECLARATIONS), ('state', '!=', 'draft')]
        )
        return {
            'student': {'id': student.id, 'name': student.name},
            'enrollment': {
                'id': enrollment.id,
                'class': enrollment.class_id._editor_label(),
                'course': enrollment.class_id.course_id.name or '',
                'number': enrollment.order_number or '',
                'regime': Helpers.regime(enrollment),
                'year': enrollment.academic_year_id.name,
                'state': self.env['edu.student.picker']._row(enrollment)['state'],
            },
            'identity': identity,
            'blocked': self._blocked(enrollment, document_type),
            'documents': [
                {
                    'id': d.id,
                    'name': d.name,
                    'type': dict(DOCUMENT_TYPES)[d.document_type],
                    'year': d.academic_year_id.name or '',
                    'date': d.date.strftime('%d/%m/%Y'),
                    'state': d.state,
                    'prints': d.print_count,
                }
                for d in documents
            ],
        }

    @api.model
    def _blocked(self, enrollment, document_type):
        """Porque é que a declaração não pode sair (as regras da emissão), ou False."""
        document = self.env['edu.document'].new(
            {'document_type': document_type, 'student_id': enrollment.student_id.id, 'enrollment_id': enrollment.id}
        )
        try:
            document._check_requirements()
        except UserError as error:
            return str(error.args[0] if error.args else error)
        return False

    # Ver e emitir

    @api.model
    def _identity_vals(self, identity):
        vals = {}
        for key, _label in IDENTITY_FIELDS:
            if key in (identity or {}):
                value = identity[key]
                vals[key] = value or False
        return vals

    @api.model
    def save_identity(self, enrollment_id, identity):
        enrollment = self.env['edu.enrollment'].browse(enrollment_id)
        enrollment.student_id.write(self._identity_vals(identity))
        return True

    @api.model
    def _document(self, enrollment_id, document_type, identity, purpose):
        """O rascunho da declaração (o que já existe para esta matrícula e tipo, ou um novo), com os dados guardados."""
        if document_type not in DECLARATIONS:
            raise UserError(self.env._('Escolha o tipo de declaração.'))
        enrollment = self.env['edu.enrollment'].browse(enrollment_id).exists()
        if not enrollment:
            raise UserError(self.env._('A matrícula já não existe.'))
        self.save_identity(enrollment.id, identity)
        Document = self.env['edu.document']
        document = Document.search(
            [('enrollment_id', '=', enrollment.id), ('document_type', '=', document_type), ('state', '=', 'draft')],
            limit=1,
        )
        vals = {'purpose': purpose or False}
        if document:
            document.write(vals)
        else:
            document = Document.create(
                {
                    'document_type': document_type,
                    'student_id': enrollment.student_id.id,
                    'enrollment_id': enrollment.id,
                    'company_id': enrollment.company_id.id,
                    **vals,
                }
            )
        document._check_requirements()
        return document

    @api.model
    def preview(self, enrollment_id, document_type, identity, purpose):
        """Ver a declaração tal como sai, sem a emitir (fica em rascunho no registo)."""
        return self._document(enrollment_id, document_type, identity, purpose).action_preview()

    @api.model
    def issue_and_print(self, enrollment_id, document_type, identity, purpose):
        """Emite (dá o número) e imprime em PDF."""
        return self._document(enrollment_id, document_type, identity, purpose).action_print()

    @api.model
    def reprint(self, document_id):
        """Reimprime uma declaração emitida (sai «2.ª VIA»)."""
        document = self.env['edu.document'].browse(document_id).exists()
        if not document or document.state != 'issued':
            raise UserError(self.env._('Só se reimprime uma declaração emitida.'))
        return document.action_print()
