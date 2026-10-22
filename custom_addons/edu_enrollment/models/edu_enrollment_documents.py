from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models

DOCUMENT_DEADLINE_DAYS = 60
FIRST_ENROLLMENT_TYPES = ('new', 'transfer_in')


class EduEnrollmentDocumentType(models.Model):
    """Documentos da primeira matrícula (DP 162/23, art. 26.º): no primário, o boletim, a certidão de nascimento ou o
    BI e 2 fotografias; no secundário, o certificado de habilitações, o boletim, o BI e 4 fotografias. A escola pode
    acrescentar os seus."""

    _name = 'edu.enrollment.document.type'
    _description = 'Documento exigido na matrícula'
    _order = 'sequence, id'

    name = fields.Char(string='Documento', required=True, translate=True)
    sequence = fields.Integer(default=10)
    level_ids = fields.Many2many('edu.level', string='Níveis', help='Vazio: todos os níveis.')
    company_id = fields.Many2one(
        'res.company', string='Escola', index=True, help='Vazio: todas as escolas (os documentos da lei).'
    )
    active = fields.Boolean(default=True)


class EduEnrollmentDocument(models.Model):
    _name = 'edu.enrollment.document'
    _description = 'Documento entregue na matrícula'
    _order = 'enrollment_id, sequence, id'

    enrollment_id = fields.Many2one('edu.enrollment', string='Matrícula', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='enrollment_id.company_id', store=True)
    type_id = fields.Many2one('edu.enrollment.document.type', string='Documento', required=True)
    sequence = fields.Integer(related='type_id.sequence', store=True)
    delivered = fields.Boolean(string='Entregue')
    delivered_date = fields.Date(string='Entregue em')
    note = fields.Char(string='Observações')

    @api.onchange('delivered')
    def _onchange_delivered(self):
        if self.delivered and not self.delivered_date:
            self.delivered_date = fields.Date.context_today(self)


class EduEnrollment(models.Model):
    _inherit = 'edu.enrollment'

    document_ids = fields.One2many('edu.enrollment.document', 'enrollment_id', string='Documentos')
    documents_complete = fields.Boolean(
        string='Processo completo', compute='_compute_documents_complete', store=True, index=True
    )
    documents_missing = fields.Char(string='Documentos em falta', compute='_compute_documents_complete', store=True)
    documents_deadline = fields.Date(
        string='Prazo dos documentos',
        compute='_compute_documents_deadline',
        help='60 dias após o início do ano lectivo (DP 162/23, art. 24.º, n.º 10).',
    )
    documents_overdue = fields.Boolean(string='Processo incompleto fora do prazo', readonly=True, copy=False)

    @api.depends('document_ids.delivered')
    def _compute_documents_complete(self):
        for enrollment in self:
            missing = enrollment.document_ids.filtered(lambda d: not d.delivered).type_id
            enrollment.documents_complete = not missing
            enrollment.documents_missing = ', '.join(missing.mapped('name')) or False

    @api.depends('academic_year_id', 'date')
    def _compute_documents_deadline(self):
        for enrollment in self:
            start = max(filter(None, [enrollment.academic_year_id.date_start, enrollment.date]), default=False)
            enrollment.documents_deadline = start + timedelta(days=DOCUMENT_DEADLINE_DAYS) if start else False

    @api.model_create_multi
    def create(self, vals_list):
        enrollments = super().create(vals_list)
        if not self.env.context.get('edu_matricula_import'):
            enrollments.filtered(lambda e: e.enrollment_type in FIRST_ENROLLMENT_TYPES)._create_document_lines()
        return enrollments

    def _create_document_lines(self):
        """A lista do que se entrega na primeira matrícula; a confirmação não exige documentos (art. 27.º, n.º 3)."""
        types = self.env['edu.enrollment.document.type'].search([('active', '=', True)])
        for enrollment in self:
            level, company = enrollment.class_id.level_id, enrollment.company_id
            wanted = types.filtered(
                lambda t, lv=level, c=company: (
                    (not t.level_ids or lv in t.level_ids) and (not t.company_id or t.company_id == c)
                )
            )
            enrollment.document_ids = [fields.Command.create({'type_id': t.id}) for t in wanted]

    @api.model
    def _edu_alerts(self, today):
        """Situações que a direcção e a secretaria têm de resolver, como (título, matrículas). As avaliações
        acrescentam as matrículas condicionais por efectivar."""
        overdue = self.search(
            [
                ('state', 'in', ('active', 'irregular')),
                ('enrollment_type', 'in', FIRST_ENROLLMENT_TYPES),
                ('documents_complete', '=', False),
                ('documents_overdue', '=', False),
                ('academic_year_id.is_current', '=', True),
            ]
        ).filtered(lambda e: e.documents_deadline and e.documents_deadline < today)
        overdue.write({'documents_overdue': True})
        return [
            (
                self.env._(
                    'Processos de matrícula incompletos há mais de 60 dias (DP 162/23, art. 24.º, n.º 10): a matrícula '
                    'pode ser anulada (anulação oficiosa por processo incompleto).'
                ),
                overdue,
            )
        ]

    @api.model
    def _cron_alerts(self):
        """Avisa a direcção e a secretaria, no ano lectivo em curso, do que passou do prazo. Não anula nada."""
        today = fields.Date.context_today(self)
        groups = self.env.ref('edu_core.group_edu_manager') | self.env.ref('edu_core.group_edu_user')
        partners = groups.user_ids.filtered(lambda u: u.active and not u.share).partner_id
        for title, enrollments in self._edu_alerts(today):
            for year in enrollments.academic_year_id:
                rows = enrollments.filtered(lambda e, y=year: e.academic_year_id == y)
                items = Markup('').join(
                    Markup('<li>%s — %s%s</li>')
                    % (
                        e.student_id.name,
                        e.class_id.display_name,
                        f' ({e.documents_missing})' if e.documents_missing else '',
                    )
                    for e in rows
                )
                year.message_post(
                    body=Markup('<p>%s</p><ul>%s</ul>') % (title, items),
                    subject=title,
                    partner_ids=partners.filtered(lambda p, y=year: y.company_id in p.user_ids.company_ids).ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )
