from odoo import api, fields, models
from odoo.exceptions import UserError

DOCUMENT_TYPES = [
    ('frequency', 'Declaração de frequência'),
    ('grades', 'Declaração com notas'),
    ('transfer_declaration', 'Declaração para transferência'),
    ('transfer_guide', 'Guia de transferência'),
    ('term', 'Termo de frequência e aproveitamento'),
    ('certificate', 'Certificado de habilitações'),
    ('diploma', 'Diploma'),
]
PREFIXES = {
    'frequency': 'DSN',
    'grades': 'DCN',
    'transfer_declaration': 'DTR',
    'transfer_guide': 'GT',
    'term': 'TFA',
    'certificate': 'CH',
    'diploma': 'DIP',
}
REPORTS = {
    'frequency': 'edu_documents.action_report_declaration_frequency',
    'grades': 'edu_documents.action_report_declaration_grades',
    'transfer_declaration': 'edu_documents.action_report_declaration_transfer',
    'transfer_guide': 'edu_documents.action_report_transfer_guide',
    'term': 'edu_documents.action_report_term',
    'certificate': 'edu_documents.action_report_certificate',
    'diploma': 'edu_documents.action_report_diploma',
}


class EduDocument(models.Model):
    """Registo dos documentos emitidos pela secretaria: número por tipo e ano lectivo, finalidade e 2.ª via."""

    _name = 'edu.document'
    _description = 'Documento emitido'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Referência', readonly=True, copy=False, default='/')
    document_type = fields.Selection(DOCUMENT_TYPES, string='Documento', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    student_id = fields.Many2one('edu.student', string='Aluno', required=True, index=True, check_company=True)
    enrollment_id = fields.Many2one(
        'edu.enrollment', string='Matrícula', check_company=True, domain="[('student_id', '=', student_id)]"
    )
    academic_year_id = fields.Many2one(related='enrollment_id.academic_year_id', store=True)
    transfer_id = fields.Many2one(
        'edu.transfer', string='Transferência', check_company=True, domain="[('student_id', '=', student_id)]"
    )
    graduation_id = fields.Many2one(
        'edu.graduation', string='Conclusão', check_company=True, domain="[('student_id', '=', student_id)]"
    )
    purpose = fields.Char(string='Destina-se a', default='todos os efeitos legais')
    date = fields.Date(string='Data', required=True, default=fields.Date.context_today)
    state = fields.Selection(
        [('draft', 'Rascunho'), ('issued', 'Emitido'), ('cancelled', 'Anulado')],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    issued_by_id = fields.Many2one('res.users', string='Emitido por', readonly=True)
    print_count = fields.Integer(string='Impressões', readonly=True)
    note = fields.Text(string='Observações')

    def _check_requirements(self):
        self.ensure_one()
        kind = self.document_type
        if kind in ('frequency', 'grades', 'transfer_declaration', 'term') and not self.enrollment_id:
            raise UserError(self.env._('Escolha a matrícula do aluno.'))
        if kind == 'frequency' and self.enrollment_id.state not in ('active', 'irregular'):
            raise UserError(self.env._('A declaração de frequência exige a matrícula em curso.'))
        if kind in ('grades', 'transfer_declaration'):
            if not self.enrollment_id.subject_result_ids.filtered('complete'):
                raise UserError(self.env._('A matrícula ainda não tem classificações finais.'))
        if kind == 'transfer_guide' and (not self.transfer_id or self.transfer_id.transfer_type != 'external'):
            raise UserError(self.env._('A guia de transferência exige uma transferência para outra escola.'))
        if kind == 'transfer_guide' and self.transfer_id.state != 'completed':
            raise UserError(self.env._('A guia só se emite depois de a transferência estar concluída.'))
        if kind in ('certificate', 'diploma') and (not self.graduation_id or self.graduation_id.state != 'issued'):
            raise UserError(self.env._('O certificado e o diploma exigem a conclusão emitida.'))

    def action_issue(self):
        for document in self.filtered(lambda d: d.state == 'draft'):
            document._check_requirements()
            year = document.academic_year_id or document.company_id.edu_current_year_id
            label = (year.name or str(document.date.year)).replace('/', '-')
            sequence = document._sequence()
            number = sequence.next_by_id()
            document.write(
                {
                    'name': f'{PREFIXES[document.document_type]}/Nº{int(number):02d}/{label}',
                    'state': 'issued',
                    'issued_by_id': self.env.uid,
                }
            )
        return True

    def _sequence(self):
        self.ensure_one()
        code = f'edu.document.{self.document_type}'
        Sequence = self.env['ir.sequence'].sudo()
        year = self.academic_year_id or self.company_id.edu_current_year_id
        name = f'{dict(DOCUMENT_TYPES)[self.document_type]} {year.name or ""}'.strip()
        sequence = Sequence.search(
            [('code', '=', code), ('company_id', '=', self.company_id.id), ('name', '=', name)], limit=1
        )
        return sequence or Sequence.create(
            {'name': name, 'code': code, 'company_id': self.company_id.id, 'implementation': 'no_gap', 'padding': 0}
        )

    def action_print(self):
        self.ensure_one()
        if self.state == 'draft':
            self.action_issue()
        if self.state != 'issued':
            raise UserError(self.env._('O documento está anulado.'))
        self.sudo().print_count += 1
        return self.env.ref(REPORTS[self.document_type]).report_action(self)

    def action_preview(self):
        # Ver o documento tal como sai impresso, sem o emitir nem contar como impressão.
        self.ensure_one()
        return self.env.ref(REPORTS[self.document_type]).preview_action(self)

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if self.filtered(lambda d: d.state != 'draft'):
            raise UserError(self.env._('Um documento emitido não se elimina: anule-o.'))


class EduStudent(models.Model):
    _inherit = 'edu.student'

    birth_municipality = fields.Char(string='Município de naturalidade')
    document_ids = fields.One2many('edu.document', 'student_id', string='Documentos')

    def action_new_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Emitir documento'),
            'res_model': 'edu.document',
            'view_mode': 'form',
            'context': {
                'default_student_id': self.id,
                'default_enrollment_id': self.current_enrollment_id.id or self.enrollment_ids[:1].id,
            },
        }


class EduTransfer(models.Model):
    _inherit = 'edu.transfer'

    document_ids = fields.One2many('edu.document', 'transfer_id', string='Documentos de saída')

    def _exit_document(self, kind, enrollment):
        """O documento de saída desta transferência (o já emitido, ou um novo, emitido agora)."""
        self.ensure_one()
        if self.transfer_type != 'external' or self.state != 'completed':
            raise UserError(
                self.env._('Os documentos de saída emitem-se depois de concluída a saída para outra escola.')
            )
        document = self.document_ids.filtered(lambda d: d.document_type == kind and d.state == 'issued')[:1]
        if not document:
            document = self.env['edu.document'].create(
                {
                    'document_type': kind,
                    'student_id': self.student_id.id,
                    'enrollment_id': enrollment.id,
                    'transfer_id': self.id,
                    'purpose': self.env._('efeitos de transferência'),
                }
            )
            document.action_issue()
        return document.action_preview()

    def action_print_transfer_guide(self):
        """Guia de transferência: a carta à escola de destino com a lista dos documentos do processo individual."""
        return self._exit_document('transfer_guide', self.enrollment_id)

    def action_print_transfer_declaration(self):
        """Declaração com as notas da última classe concluída (numa saída a meio do ano, a do ano anterior)."""
        self.ensure_one()
        # Só uma classe com a decisão final tomada (pendente ou em exame ainda não se declara).
        finished = self.student_id.enrollment_ids.filtered(
            lambda e: (
                e.subject_result_ids.filtered('complete')
                and e.sudo().year_result_id.status in ('promoted', 'graduated', 'conditional', 'retained')
            )
        )
        enrollment = finished.sorted(lambda e: e.academic_year_id.date_start, reverse=True)[:1]
        if not enrollment:
            raise UserError(self.env._('O aluno ainda não tem nenhuma classe com classificações finais.'))
        return self._exit_document('transfer_declaration', enrollment)
