import base64

from odoo import api, fields, models
from odoo.exceptions import UserError

ALERT_DAYS = 5  # pedidos em curso com a resposta a menos de cinco dias


def _fmt(day):
    return day.strftime('%d/%m/%Y') if day else ''


class EduAppealPage(models.AbstractModel):
    """Página «Reapreciações» (acção cliente ``edu_documents.appeals``): o processo da lei (Despacho 60/08, art. 15.º;
    DE 424/25, art. 36.º). A secretaria regista o pedido (o aluno pela turma ou pelo nome, a disciplina e a pauta
    contestada, o requerente, o fundamento e os documentos) e informa o interessado; a direcção admite ou indefere
    liminarmente e regista a deliberação do conselho de turma extraordinário (técnico) ou da comissão (geral) e, sem
    provimento no técnico, a do Conselho Pedagógico."""

    _name = 'edu.appeal.page'
    _description = 'Reapreciações'

    @api.model
    def _row(self, appeal):
        today = fields.Date.context_today(self)
        open_ = appeal.state in ('pending', 'review', 'appealed')
        days_left = (appeal.answer_deadline - today).days if appeal.answer_deadline else None
        return {
            'id': appeal.id,
            'student': appeal.student_id.name,
            'class': appeal.class_id._editor_label(),
            'subject': appeal.subject_id.name,
            'moment': appeal.trimester_id.name or 'Classificação final do ano',
            'request_date': _fmt(appeal.request_date),
            'answer_deadline': _fmt(appeal.answer_deadline),
            'days_left': days_left,
            'alert': open_ and days_left is not None and days_left <= ALERT_DAYS,
            'late': appeal.late,
            'state': appeal.state,
            'state_label': dict(appeal._fields['state']._description_selection(self.env))[appeal.state],
            'notified': _fmt(appeal.notified_date),
        }

    @api.model
    def appeals(self, tab='open'):
        Appeal = self.env['edu.grade.appeal']
        domain = (
            [('state', 'in', ('pending', 'review', 'appealed'))]
            if tab == 'open'
            else [('state', 'in', ('granted', 'denied', 'rejected'))]
        )
        records = Appeal.search(domain, order='answer_deadline, id' if tab == 'open' else 'id desc')
        open_count = Appeal.search_count([('state', 'in', ('pending', 'review', 'appealed'))])
        rows = [self._row(a) for a in records]
        return {
            'rows': rows,
            'open_count': open_count,
            'alerts': sum(1 for r in rows if r['alert']),
            'is_manager': self.env.user.has_group('edu_core.group_edu_manager'),
        }

    # Registar o pedido

    @api.model
    def request_options(self, enrollment_id):
        enrollment = self.env['edu.enrollment'].browse(enrollment_id).exists()
        if not enrollment:
            raise UserError(self.env._('A matrícula já não existe.'))
        subjects = (enrollment.subject_ids - enrollment._dropped_subjects()).sorted('name')
        trimesters = enrollment.academic_year_id.trimester_ids.sorted('number')
        closed = trimesters.filtered(lambda t: t.state == 'closed')
        technical = enrollment.class_id.level_id.subsystem == 'technical'
        # Técnico: cada pauta trimestral e a final; geral: a avaliação de fim de ano (DE 424/25, art. 36.º).
        moments = [{'id': t.id, 'label': t.name} for t in closed] if technical else []
        moments.append({'id': 0, 'label': 'Classificação final do ano'})
        student = enrollment.student_id.sudo()
        return {
            'student': student.name,
            'class': enrollment.class_id._editor_label(),
            'technical': technical,
            'subjects': [{'id': s.id, 'name': s.name} for s in subjects],
            'moments': moments,
            'guardian': student.primary_guardian_id.name or '',
            'today': fields.Date.to_string(fields.Date.context_today(self)),
        }

    @api.model
    def create_request(self, values):
        attachments = self.env['ir.attachment']
        for item in values.get('attachments') or []:
            attachments |= attachments.create(
                {
                    'name': item.get('name') or 'documento',
                    # O Odoo 20 recebe o conteúdo em bytes (raw); a página envia-o em base64.
                    'raw': base64.b64decode(item.get('datas') or ''),
                    'res_model': 'edu.grade.appeal',
                }
            )
        appeal = self.env['edu.grade.appeal'].create(
            {
                'enrollment_id': values.get('enrollment_id'),
                'subject_id': values.get('subject_id'),
                'trimester_id': values.get('trimester_id') or False,
                'requester_type': values.get('requester_type') or 'guardian',
                'requester_name': values.get('requester_name') or False,
                'request_date': values.get('request_date') or fields.Date.context_today(self),
                'posting_date': values.get('posting_date') or False,
                'reason': (values.get('reason') or '').strip(),
                'attachment_ids': [fields.Command.set(attachments.ids)],
            }
        )
        attachments.write({'res_id': appeal.id})
        return self.detail(appeal.id)

    # O processo

    @api.model
    def _appeal(self, appeal_id):
        appeal = self.env['edu.grade.appeal'].browse(appeal_id).exists()
        if not appeal:
            raise UserError(self.env._('A reapreciação já não existe.'))
        return appeal

    @api.model
    def detail(self, appeal_id):
        appeal = self._appeal(appeal_id)
        domain = [('enrollment_id', '=', appeal.enrollment_id.id), ('subject_id', '=', appeal.subject_id.id)]
        if appeal.trimester_id:
            domain.append(('trimester_id', '=', appeal.trimester_id.id))
        grades = self.env['edu.grade'].sudo().search(domain)
        return {
            **self._row(appeal),
            'regime': appeal.regime,
            'body': 'conselho de turma extraordinário' if appeal.regime == 'technical' else 'comissão de reavaliação',
            'requester': self._requester(appeal),
            'reason': appeal.reason,
            'posting_date': _fmt(appeal.posting_date),
            'deadline_date': _fmt(appeal.deadline_date),
            'admitted_date': _fmt(appeal.admitted_date),
            'meeting_date': _fmt(appeal.meeting_date),
            'meeting_iso': fields.Date.to_string(appeal.meeting_date) if appeal.meeting_date else '',
            'minutes_ref': appeal.minutes_ref or '',
            'decision': appeal.decision or '',
            'pedagogical_decision': appeal.pedagogical_decision or '',
            'grade': f'{appeal.grade_id.assessment_id.name}: {appeal.original_score:g} → {appeal.new_score:g}'
            if appeal.grade_id and appeal.state == 'granted'
            else '',
            'decided_by': appeal.decided_by_id.name or '',
            'attachments': [{'id': a.id, 'name': a.name} for a in appeal.attachment_ids],
            'grades': [
                {
                    'id': g.id,
                    'label': f'{g.assessment_id.name} ({g.trimester_id.name or ""})',
                    'score': g.score if g.graded else None,
                }
                for g in grades.sorted(lambda g: (g.trimester_id.number or 9, g.assessment_id.name or ''))
            ],
        }

    @api.model
    def _requester(self, appeal):
        kind = dict(appeal._fields['requester_type']._description_selection(self.env))[appeal.requester_type]
        return f'{kind}: {appeal.requester_name}' if appeal.requester_name else kind

    @api.model
    def admit(self, appeal_id, meeting_date=False):
        self._appeal(appeal_id).action_admit(meeting_date or None)
        return self.detail(appeal_id)

    @api.model
    def reject(self, appeal_id, reason):
        self._appeal(appeal_id).action_reject(reason)
        return self.detail(appeal_id)

    @api.model
    def deliberate(self, appeal_id, values):
        """Regista a deliberação do órgão (ou do Conselho Pedagógico): deferido (corrige a nota) ou sem provimento."""
        appeal = self._appeal(appeal_id)
        appeal._check_manager()
        text = (values.get('text') or '').strip()
        vals = {'minutes_ref': values.get('minutes_ref') or appeal.minutes_ref}
        vals['pedagogical_decision' if appeal.state == 'appealed' else 'decision'] = text or False
        if values.get('outcome') == 'grant':
            if not values.get('grade_id'):
                raise UserError(self.env._('Escolha a nota que a deliberação corrige.'))
            vals.update({'grade_id': values['grade_id'], 'new_score': float(values.get('new_score') or 0)})
            if values.get('new_score') in (None, ''):
                raise UserError(self.env._('Escreva a nova nota antes de deferir.'))
            appeal.write(vals)
            appeal.action_grant()
        else:
            appeal.write(vals)
            appeal.action_deny()
        return self.detail(appeal_id)

    @api.model
    def notify(self, appeal_id, date=False):
        self._appeal(appeal_id).action_notify(date or None)
        return self.detail(appeal_id)
