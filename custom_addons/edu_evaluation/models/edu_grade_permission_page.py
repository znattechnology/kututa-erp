from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .edu_grade_edit_permission import MAX_DAYS

MONTHS = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]  # fmt: skip


class EduGradePermissionPage(models.AbstractModel):
    """Página «Autorizações para alterar notas» (acção cliente ``edu_evaluation.grade_permissions``), como a do
    secPed-Express: o professor só lança no trimestre corrente; para um trimestre passado ainda aberto (ou futuro), a
    secretaria dá-lhe uma autorização para a turma, a disciplina e o trimestre, com motivo e prazo (até 30 dias). Um
    trimestre encerrado não se autoriza: corrige-se por reapreciação."""

    _name = 'edu.grade.permission.page'
    _description = 'Autorizações para alterar notas'

    @api.model
    def _local_day(self, value):
        local = fields.Datetime.context_timestamp(self, value)
        return f'{local.day} de {MONTHS[local.month - 1]} de {local.year}'

    @api.model
    def _row(self, permission):
        if permission.revoked:
            situation, tone = f'Revogada a {self._local_day(permission.revoked_date or permission.write_date)}', 'muted'
        elif not permission.active_now:
            situation, tone = 'Expirada', 'muted'
        else:
            situation, tone = f'Até {self._local_day(permission.date_expiry)}', 'pos'
        trimester = permission.trimester_id
        return {
            'id': permission.id,
            'teacher': permission.teacher_id.name,
            'class': permission.class_id._editor_label(),
            'subject': permission.subject_id.name,
            'trimester': f'{trimester.number}.º, {trimester.academic_year_id.name}',
            'reason': permission.reason,
            'situation': situation,
            'tone': tone,
            'active': permission.active_now,
            'granted': f'{permission.create_uid.name}, {self._local_day(permission.create_date)}',
            'revoked_by': permission.revoked_by_id.name or '',
        }

    @api.model
    def permissions(self, only_active=True):
        Permission = self.env['edu.grade.edit.permission']
        domain = [('revoked', '=', False), ('date_expiry', '>', fields.Datetime.now())] if only_active else []
        records = Permission.search(domain)
        active = Permission.search_count([('revoked', '=', False), ('date_expiry', '>', fields.Datetime.now())])
        return {'rows': [self._row(p) for p in records], 'active_count': active}

    @api.model
    def revoke(self, permission_id):
        permission = self.env['edu.grade.edit.permission'].browse(permission_id).exists()
        if not permission:
            raise UserError(self.env._('A autorização já não existe.'))
        permission.action_revoke()
        return self._row(permission)

    # Nova autorização (formulário guiado)

    @api.model
    def form_options(self):
        """Os professores com disciplinas no ano em curso, as turmas e disciplinas de cada um e os trimestres que se
        podem autorizar (do ano em curso, nem o corrente nem os encerrados)."""
        year = self.env['edu.academic.year'].search(
            [('is_current', '=', True), ('company_id', 'in', self.env.companies.ids)], limit=1
        )
        assignments = self.env['edu.teaching.assignment'].search([('class_id.academic_year_id', '=', year.id)])
        teachers = {}
        for assignment in assignments.sorted(lambda a: (a.class_id._editor_label(), a.subject_id.name or '')):
            teacher = assignment.teacher_id
            entry = teachers.setdefault(teacher.id, {'id': teacher.id, 'name': teacher.name, 'options': []})
            key = f'{assignment.class_id.id}-{assignment.subject_id.id}'
            if all(o['key'] != key for o in entry['options']):
                entry['options'].append(
                    {
                        'key': key,
                        'class_id': assignment.class_id.id,
                        'subject_id': assignment.subject_id.id,
                        'label': f'{assignment.class_id._editor_label()}, {assignment.subject_id.name}',
                    }
                )
        # Dois professores com o mesmo nome distinguem-se pelo e-mail de trabalho.
        names = [t['name'] for t in teachers.values()]
        for entry in teachers.values():
            if names.count(entry['name']) > 1:
                email = self.env['hr.employee'].browse(entry['id']).work_email
                entry['name'] = f'{entry["name"]} ({email})' if email else entry['name']
        trimesters = year.trimester_ids.filtered(lambda t: not t.is_current and t.state != 'closed').sorted('number')
        today = fields.Date.context_today(self)
        return {
            'year': year.name or '',
            'teachers': sorted(teachers.values(), key=lambda t: t['name']),
            'trimesters': [{'id': t.id, 'label': f'{t.number}.º trimestre'} for t in trimesters],
            'default_until': fields.Date.to_string(today + timedelta(days=7)),
            'max_until': fields.Date.to_string(today + timedelta(days=MAX_DAYS)),
            'min_until': fields.Date.to_string(today),
        }

    @api.model
    def create_permission(self, values):
        """Cria (ou renova) a autorização; «Vale até» é um dia (vale até ao fim desse dia)."""
        until = fields.Date.to_date(values.get('until'))
        if not until:
            raise UserError(self.env._('Indique até quando vale a autorização.'))
        today = fields.Date.context_today(self)
        if until < today or until > today + timedelta(days=MAX_DAYS):
            raise UserError(self.env._('No máximo %s dias a partir de hoje.', MAX_DAYS))
        expiry = min(datetime.combine(until, time(23, 59, 59)), fields.Datetime.now() + timedelta(days=MAX_DAYS))
        permission = self.env['edu.grade.edit.permission'].create(
            {
                'teacher_id': values.get('teacher_id'),
                'class_id': values.get('class_id'),
                'subject_id': values.get('subject_id'),
                'trimester_id': values.get('trimester_id'),
                'reason': (values.get('reason') or '').strip(),
                'date_expiry': expiry,
            }
        )
        return self._row(permission)
