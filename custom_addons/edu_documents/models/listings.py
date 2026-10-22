from datetime import date

from odoo import api, models

EM = '  '


def _label(record, field):
    return dict(record._fields[field]._description_selection(record.env)).get(record[field], '') or ''


class EduListingMixin(models.AbstractModel):
    """«Visualizar e imprimir» das listas das matrículas: o mesmo documento (cabeçalho e assinaturas da pauta, tabela
    por grupos) para candidaturas, matrículas, anulações, transferências, confirmação e alunos. Cada modelo diz o
    título, as colunas e os grupos em ``_listing_data``; sem linhas escolhidas, imprime-se o ano em curso."""

    _name = 'edu.listing.mixin'
    _description = 'Lista imprimível'
    _listing_report = 'edu_documents.action_report_listing_enrollment'

    @api.model
    def _listing_default(self):
        return self.search([('academic_year_id.is_current', '=', True)])

    def action_print_listing(self):
        records = self or self._listing_default()
        return self.env.ref(self._listing_report).preview_action(records)

    def _listing_year(self):
        years = self.mapped('academic_year_id') if 'academic_year_id' in self._fields else self.browse()
        return ', '.join(years.sorted('date_start').mapped('name')) or self.env.company.edu_current_year_id.name or ''


class EduApplication(models.Model):
    _name = 'edu.application'
    _inherit = ['edu.application', 'edu.listing.mixin']
    _listing_report = 'edu_documents.action_report_listing_application'

    def _listing_data(self):
        groups = []
        for course in self.desired_course_id.sorted('name'):
            rows = self.filtered(lambda a, c=course: a.desired_course_id == c)
            groups.append((course.name, rows))
        without = self.filtered(lambda a: not a.desired_course_id)
        if without:
            groups.append((self.env._('Sem curso indicado'), without))
        return {
            'title': self.env._('LISTA DE CANDIDATURAS'),
            'context': EM.join([f'ANO LECTIVO: {self._listing_year()}', self.env._('%s CANDIDATURAS', len(self))]),
            'columns': [
                ('Nº', 5, 'c'),
                (self.env._('Candidato(a)'), 0, 'l'),
                (self.env._('BI'), 16, 'l'),
                (self.env._('Classe'), 8, 'c'),
                (self.env._('Prova de acesso'), 10, 'c'),
                (self.env._('Resultado'), 13, 'l'),
                (self.env._('Estado'), 11, 'l'),
            ],
            'groups': [
                {
                    'label': label,
                    'rows': [
                        [
                            index + 1,
                            a.name,
                            a.id_number or '',
                            a.desired_class_number and f'{a.desired_class_number}ª' or '',
                            f'{a.admission_score:g}' if a.has_admission_score else '',
                            _label(a, 'admission_result'),
                            _label(a, 'state'),
                        ]
                        for index, a in enumerate(
                            rows.sorted(lambda a: (a.admission_rank or 10**6, -a.admission_score, a.name or ''))
                        )
                    ],
                }
                for label, rows in groups
            ],
        }

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref('edu_documents.action_report_application_receipt').preview_action(self)


class EduEnrollment(models.Model):
    _name = 'edu.enrollment'
    _inherit = ['edu.enrollment', 'edu.listing.mixin']

    @api.model
    def _listing_default(self):
        if self.env.context.get('edu_listing_dropped'):
            return self.search([('state', '=', 'dropped')])
        return super()._listing_default()

    def _listing_data(self):
        if self and all(e.state == 'dropped' for e in self):
            return self._listing_drops()
        groups = []
        for edu_class in self.class_id.sorted(lambda c: (c.class_number, c.course_id.code or '', c.name)):
            rows = self.filtered(lambda e, c=edu_class: e.class_id == c).sorted(lambda e: (e.order_number, e.id))
            groups.append(
                {
                    'label': f'{edu_class._editor_label()} · {edu_class.course_id.name}',
                    'rows': [
                        [
                            e.order_number or '',
                            e.student_id.matricula_number or '',
                            e.student_id.name,
                            _label(e, 'enrollment_type'),
                            _label(e, 'state'),
                        ]
                        for e in rows
                    ],
                }
            )
        return {
            'title': self.env._('LISTA DE MATRÍCULAS'),
            'context': EM.join([f'ANO LECTIVO: {self._listing_year()}', self.env._('%s MATRÍCULAS', len(self))]),
            'columns': [
                ('Nº', 5, 'c'),
                (self.env._('N.º de matrícula'), 13, 'l'),
                (self.env._('Aluno'), 0, 'l'),
                (self.env._('Tipo'), 20, 'l'),
                (self.env._('Estado'), 12, 'l'),
            ],
            'groups': groups,
        }

    def _listing_drops(self):
        groups = []
        for year in self.academic_year_id.sorted('date_start', reverse=True):
            rows = self.filtered(lambda e, y=year: e.academic_year_id == y).sorted(lambda e: e.drop_date or e.date)
            groups.append(
                {
                    'label': year.name,
                    'rows': [
                        [
                            e.drop_date and e.drop_date.strftime('%d/%m/%Y') or '',
                            e.student_id.name,
                            e.class_id._editor_label(),
                            _label(e, 'drop_reason_code'),
                            _label(e, 'drop_requested_by'),
                            self.env._('Sim') if e.drop_justified else self.env._('Não'),
                        ]
                        for e in rows
                    ],
                }
            )
        return {
            'title': self.env._('ANULAÇÕES DE MATRÍCULA'),
            'context': EM.join([f'ANO LECTIVO: {self._listing_year()}', self.env._('%s ANULAÇÕES', len(self))]),
            'columns': [
                (self.env._('Data'), 10, 'c'),
                (self.env._('Aluno'), 0, 'l'),
                (self.env._('Turma'), 12, 'l'),
                (self.env._('Motivo'), 22, 'l'),
                (self.env._('Pedida por'), 15, 'l'),
                (self.env._('Justificada'), 9, 'c'),
            ],
            'groups': groups,
        }


class EduTransfer(models.Model):
    _name = 'edu.transfer'
    _inherit = ['edu.transfer', 'edu.listing.mixin']
    _listing_report = 'edu_documents.action_report_listing_transfer'

    def _listing_data(self):
        def destination(t):
            if t.transfer_type == 'external':
                return t.external_school or ''
            return t.to_class_id._editor_label() if t.to_class_id else ''

        def origin(t):
            return t.origin_school if t.transfer_type == 'incoming' else t.from_class_id._editor_label()

        groups = []
        for kind, label in self._fields['transfer_type']._description_selection(self.env):
            rows = self.filtered(lambda t, k=kind: t.transfer_type == k).sorted(
                lambda t: (not t.effective_date, t.effective_date or date.min, t.id)
            )
            if rows:
                groups.append(
                    {
                        'label': label,
                        'rows': [
                            [
                                t.effective_date and t.effective_date.strftime('%d/%m/%Y') or '',
                                t.student_id.name or t.incoming_name or '',
                                origin(t) or '',
                                destination(t),
                                _label(t, 'state'),
                            ]
                            for t in rows
                        ],
                    }
                )
        return {
            'title': self.env._('TRANSFERÊNCIAS'),
            'context': EM.join([f'ANO LECTIVO: {self._listing_year()}', self.env._('%s PEDIDOS', len(self))]),
            'columns': [
                (self.env._('Data'), 10, 'c'),
                (self.env._('Aluno'), 0, 'l'),
                (self.env._('De'), 20, 'l'),
                (self.env._('Para'), 22, 'l'),
                (self.env._('Estado'), 11, 'l'),
            ],
            'groups': groups,
        }


class EduStudent(models.Model):
    _name = 'edu.student'
    _inherit = ['edu.student', 'edu.listing.mixin']
    _listing_report = 'edu_documents.action_report_listing_student'

    @api.model
    def _listing_default(self):
        return self.search([('student_status', '=', self.env.context.get('edu_listing_status', 'enrolled'))])

    def _listing_year(self):
        return self.env.company.edu_current_year_id.name or ''

    def _listing_data(self):
        groups = []
        for status, label in self._fields['student_status']._description_selection(self.env):
            rows = self.filtered(lambda s, st=status: s.student_status == st).sorted('name')
            if rows:
                groups.append(
                    {
                        'label': label,
                        'rows': [
                            [
                                s.matricula_number or '',
                                s.name,
                                s.current_class_id._editor_label() if s.current_class_id else '',
                                s.last_academic_year_id.name or '',
                            ]
                            for s in rows
                        ],
                    }
                )
        return {
            'title': self.env._('LISTA DE ALUNOS'),
            'context': EM.join([f'ANO LECTIVO: {self._listing_year()}', self.env._('%s ALUNOS', len(self))]),
            'columns': [
                (self.env._('N.º de matrícula'), 14, 'l'),
                (self.env._('Aluno'), 0, 'l'),
                (self.env._('Turma actual'), 16, 'l'),
                (self.env._('Último ano'), 12, 'c'),
            ],
            'groups': groups,
        }


MONTHS = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro',
    'Dezembro',
]  # fmt: skip


class EduCalendarEvent(models.Model):
    _name = 'edu.calendar.event'
    _inherit = ['edu.calendar.event', 'edu.listing.mixin']
    _listing_report = 'edu_documents.action_report_listing_calendar'

    def _listing_data(self):
        groups = {}
        for event in self.sorted('date_start'):
            key = (event.date_start.year, event.date_start.month)
            groups.setdefault(key, []).append(event)

        def when(event):
            end = event.date_end
            if end and end != event.date_start:
                return f'{event.date_start.strftime("%d/%m")} a {end.strftime("%d/%m")}'
            return event.date_start.strftime('%d/%m')

        return {
            'title': self.env._('CALENDÁRIO ESCOLAR'),
            'context': EM.join([f'ANO LECTIVO: {self._listing_year()}', self.env._('%s EVENTOS', len(self))]),
            'columns': [
                (self.env._('Data'), 15, 'c'),
                (self.env._('Evento'), 0, 'l'),
                (self.env._('Níveis'), 22, 'l'),
            ],
            'groups': [
                {
                    'label': f'{MONTHS[month - 1]} {year}',
                    'rows': [[when(e), e.name, ', '.join(e.level_ids.mapped('name')) or 'Todos'] for e in events],
                }
                for (year, month), events in groups.items()
            ],
        }
