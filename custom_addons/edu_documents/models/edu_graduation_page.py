from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Em que ponto está o diploma (e a conclusão), como no secPed, com o tom da coluna.
DIPLOMA_STATES = {
    'draft': ('Por emitir', 'muted'),
    'to_verify': ('Por verificar', 'warn'),
    'to_sign': ('Por assinar', 'warn'),
    'signed': ('Assinado', 'pos'),
    'cancelled': ('Anulado', 'muted'),
}


class EduGraduationPage(models.AbstractModel):
    """Página «Diplomas e certificados» (acção cliente ``edu_documents.graduations``), como a do secPed-Express: os
    alunos que concluíram o curso, por ano lectivo e curso, com o diploma e o certificado de habilitações a imprimir,
    e o diploma a verificar e assinar; «Registar conclusões» traz os alunos da turma da classe final a quem o
    conselho de turma deu a conclusão. A conclusão emite-se (número do diploma) antes de se imprimir."""

    _name = 'edu.graduation.page'
    _description = 'Diplomas e certificados'

    @api.model
    def page_options(self):
        years = self.env['edu.academic.year'].search(
            [('company_id', 'in', self.env.companies.ids)], order='date_start desc'
        )
        courses = self.env['edu.course'].search([('company_id', 'in', self.env.companies.ids)], order='name')
        current = years.filtered('is_current')[:1]
        return {
            'years': [{'id': y.id, 'name': y.name, 'is_current': y.is_current} for y in years],
            'year_id': current.id or False,
            'courses': [{'id': c.id, 'name': c.name} for c in courses],
            'is_manager': self.env.user.has_group('edu_core.group_edu_manager'),
        }

    # Lista

    @api.model
    def _row(self, graduation):
        key = (
            'cancelled'
            if graduation.state == 'cancelled'
            else ('draft' if graduation.state == 'draft' else graduation.diploma_state)
        )
        label, tone = DIPLOMA_STATES[key]
        return {
            'id': graduation.id,
            'student': graduation.student_id.name,
            'diploma_number': graduation.diploma_number or '',
            'course': graduation.course_id.name or '',
            'course_code': graduation.course_id.code or '',
            'year': graduation.academic_year_id.name or '',
            'average': graduation.final_grade,
            'date': graduation.date.strftime('%d/%m/%Y') if graduation.date else '',
            'state': graduation.state,
            'diploma_state': key,
            'diploma_label': label,
            'tone': tone,
            'verified': bool(graduation.verified_by_id),
            'verified_label': self._who_when(graduation.verified_by_id, graduation.verified_date),
            'signed': bool(graduation.signed_by_id),
            'signed_label': self._who_when(graduation.signed_by_id, graduation.signed_date),
        }

    @api.model
    def _who_when(self, user, when):
        """«Maria, 12/07/2026» (na data local)."""
        if not user:
            return ''
        day = fields.Datetime.context_timestamp(self, when).strftime('%d/%m/%Y') if when else ''
        return ', '.join(filter(None, [user.name, day]))

    @api.model
    def graduations(self, year_id=False, course_id=False):
        domain = []
        if year_id:
            domain.append(('academic_year_id', '=', year_id))
        if course_id:
            domain.append(('course_id', '=', course_id))
        graduations = (
            self.env['edu.graduation']
            .search(domain)
            .sorted(lambda g: (g.academic_year_id.date_start, g.course_id.name or '', g.student_id.name))
        )
        valid = graduations.filtered(lambda g: g.state != 'cancelled')
        return {
            'rows': [self._row(g) for g in graduations],
            'summary': {
                'total': len(valid),
                'signed': len(valid.filtered(lambda g: g.state == 'issued' and g.diploma_state == 'signed')),
                'to_verify': len(valid.filtered(lambda g: g.state == 'issued' and g.diploma_state == 'to_verify')),
                'to_sign': len(valid.filtered(lambda g: g.state == 'issued' and g.diploma_state == 'to_sign')),
                'draft': len(valid.filtered(lambda g: g.state == 'draft')),
            },
        }

    # Acções de cada linha (as mesmas regras do formulário)

    @api.model
    def _graduation(self, graduation_id):
        graduation = self.env['edu.graduation'].browse(graduation_id).exists()
        if not graduation:
            raise UserError(self.env._('A conclusão já não existe.'))
        return graduation

    @api.model
    def issue(self, graduation_id):
        graduation = self._graduation(graduation_id)
        graduation.action_issue()
        return self._row(graduation)

    @api.model
    def verify(self, graduation_id):
        graduation = self._graduation(graduation_id)
        graduation.action_mark_verified()
        return self._row(graduation)

    @api.model
    def sign(self, graduation_id):
        graduation = self._graduation(graduation_id)
        graduation.action_mark_signed()
        return self._row(graduation)

    @api.model
    def print_document(self, graduation_id, kind):
        graduation = self._graduation(graduation_id)
        if kind not in ('diploma', 'certificate'):
            raise UserError(self.env._('Documento desconhecido.'))
        return graduation._graduation_document(kind).action_preview()

    @api.model
    def open_form(self, graduation_id):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.graduation',
            'res_id': self._graduation(graduation_id).id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    # Registar conclusões

    @api.model
    def final_classes(self, year_id):
        """As turmas da classe final do curso no ano (13.ª no técnico, 12.ª no geral)."""
        classes = self.env['edu.class'].search([('academic_year_id', '=', year_id)])
        finals = classes.filtered(lambda c: c.class_number == (c.curriculum_id.class_to or c.level_id.class_to))
        return [
            {'id': c.id, 'name': c._editor_label(), 'course': c.course_id.name or ''}
            for c in finals.sorted(lambda c: (c.course_id.name or '', c.name or ''))
        ]

    @api.model
    def finishers(self, class_id):
        """Os alunos da turma a quem o conselho deu a conclusão do curso, e se já estão registados."""
        results = self.env['edu.year.result'].search(
            [('class_id', '=', class_id), ('status', 'in', ('graduated', 'promoted'))]
        )
        results.invalidate_recordset(['graduation_id'])
        rows = []
        for result in results.sorted(lambda r: (r.enrollment_id.order_number or 9999, r.student_id.name)):
            rows.append(
                {
                    'result_id': result.id,
                    'student': result.student_id.name,
                    'number': result.enrollment_id.order_number or '',
                    'average': result.average if result.average else None,
                    'registered': bool(result.graduation_id),
                    'cancelled': result.graduation_id.state == 'cancelled',
                }
            )
        return rows

    @api.model
    def register(self, result_ids):
        """Regista as conclusões (com o estágio e a PAP aprovados) e calcula a classificação final."""
        results = self.env['edu.year.result'].browse(result_ids).exists()
        done, errors = 0, []
        for result in results.filtered(lambda r: not r.graduation_id):
            try:
                with self.env.cr.savepoint():
                    result._register_graduation()
                done += 1
            except (UserError, ValidationError) as error:
                errors.append(f'{result.student_id.name}: {error.args[0] if error.args else error}')
        return {'done': done, 'errors': errors}
