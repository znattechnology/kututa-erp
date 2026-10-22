from odoo import api, fields, models
from odoo.addons.edu_evaluation.tools import grading
from odoo.exceptions import UserError

from ..tools import extenso

COMPONENT_ORDER = {'socio_cultural': 0, 'scientific': 1, 'technical': 2, 'internship': 3}
COMPONENT_LABELS = {
    'socio_cultural': 'Componente sócio-cultural',
    'scientific': 'Componente científica',
    'technical': 'Componente técnica, tecnológica e prática',
    'internship': 'Estágio',
}
STATUS_LABELS = {
    'promoted': 'TRANSITA',
    'graduated': 'CONCLUIU',
    'conditional': 'TRANSITA (C/ DISCIPLINAS EM ATRASO)',
    'exam': 'ADMITIDO A EXAME',
    'retained': 'NÃO TRANSITA',
    'pending': 'PENDENTE',
}


class Helpers:
    """Funções de formatação usadas nos modelos QWeb (h.grade(15), h.klass(12)…)."""

    def __init__(self, env, company):
        self.env = env
        self.company = company

    @staticmethod
    def grade(value, style='upper'):
        return extenso.grade_text(value, style)

    @staticmethod
    def num(value, show=True):
        return extenso.grade_number(value) if show and value is not None else ''

    @staticmethod
    def words(value):
        return extenso.number_words(grading.round_units(value or 0))

    @staticmethod
    def klass(number):
        return extenso.class_label(number)

    @staticmethod
    def ordinal(number):
        return extenso.ordinal_feminine(number)

    @staticmethod
    def date(day, upper=False):
        return extenso.date_long(day, upper)

    @staticmethod
    def color(value, pass_grade=10):
        """Azul para as positivas, vermelho para as negativas (RAA, art. 35.º)."""
        return 'edu-pos' if (value or 0) >= pass_grade else 'edu-neg'

    @staticmethod
    def by_gender(gender, male, female):
        return female if gender in {'female', 'f'} else male

    @staticmethod
    def role_case(text):
        """«O DIRECTOR DE TURMA» → «O Director de Turma» (as assinaturas da pauta, como no secPed)."""
        small = {'de', 'da', 'do', 'das', 'dos', 'e'}
        words = (text or '').lower().split()
        return ' '.join(w if w in small and i else w[:1].upper() + w[1:] for i, w in enumerate(words))

    @staticmethod
    def employee_role(employee, male, female, unknown):
        """Cargo de quem assina pelo sexo do funcionário. O sexo é um campo do RH: lê-se só ele, sem dar acesso à
        ficha (a secretaria e os professores imprimem pautas e horários)."""
        sex = employee.sudo().sex if employee else False
        if not sex:
            return unknown
        return female if sex in {'female', 'f'} else male

    def director_title(self):
        title = (self.company.edu_director_title or 'Director Geral').upper()
        if self.company.edu_director_gender == 'f':
            title = title.replace('DIRECTOR', 'DIRECTORA')
            return f'A {title}'
        return f'O {title}'

    def pedagogical_title(self):
        return (
            'A SUBDIRECTORA PEDAGÓGICA'
            if self.company.edu_pedagogical_director_gender == 'f'
            else 'O SUBDIRECTOR PEDAGÓGICO'
        )

    def city(self):
        return self.company.edu_document_city or self.company.city or ''

    @staticmethod
    def status(code):
        return STATUS_LABELS.get(code, '')

    @staticmethod
    def ordered(results):
        """Ordem das disciplinas nos documentos: Língua Portuguesa, depois por componente e nome."""
        return results.sorted(
            lambda r: (
                r.subject_id.code != 'LP',
                COMPONENT_ORDER.get(r.subject_id.component, 9),
                r.subject_id.name or '',
            )
        )

    @staticmethod
    def components(results):
        groups = []
        for code in ('socio_cultural', 'scientific', 'technical', 'internship', False):
            items = results.filtered(lambda r, c=code: (r.subject_id.component or False) == c)
            if items:
                groups.append(
                    (COMPONENT_LABELS.get(code, 'Outras disciplinas'), items.sorted(lambda r: r.subject_id.name))
                )
        return groups


class EduReportMixin(models.AbstractModel):
    _name = 'edu.report.mixin'
    _description = 'Base dos documentos escolares'
    _report_model = None

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env[self._report_model].browse(docids)
        company = docs[:1].company_id or self.env.company
        return {
            'doc_ids': docids,
            'doc_model': self._report_model,
            'docs': docs,
            'h': Helpers(self.env, company),
            'company': company,
            'today': fields.Date.context_today(self),
            **self._extra_values(docs),
        }

    def _extra_values(self, docs):
        return {}


def _document_report(template, model='edu.document'):
    return type(
        f'Report{template.title().replace("_", "")}',
        (models.AbstractModel,),
        {
            '_name': f'report.edu_documents.{template}',
            '_inherit': 'edu.report.mixin',
            '_description': f'Documento escolar: {template}',
            '_report_model': model,
            '__module__': __name__,
        },
    )


ReportDeclarationFrequency = _document_report('report_declaration_frequency')
ReportDeclarationGrades = _document_report('report_declaration_grades')
ReportDeclarationTransfer = _document_report('report_declaration_transfer')
ReportTransferGuide = _document_report('report_transfer_guide')
ReportCertificate = _document_report('report_certificate')
ReportDiploma = _document_report('report_diploma')
ReportClassList = _document_report('report_class_list', 'edu.class')
ReportClassSchedule = _document_report('report_class_schedule', 'edu.class')
ReportStudentCard = _document_report('report_student_card', 'edu.student')
ReportPauta = _document_report('report_pauta', 'edu.pauta.print')
ReportMiniPauta = _document_report('report_mini_pauta', 'edu.pauta.print')
ReportCurriculum = _document_report('report_curriculum', 'edu.curriculum')
ReportTeachers = _document_report('report_teachers', 'hr.employee.public')
ReportTeacherSchedule = _document_report('report_teacher_schedule', 'hr.employee.public')
ReportAssignments = _document_report('report_assignments', 'edu.teaching.assignment')
ReportClassDirectors = _document_report('report_class_directors', 'edu.class')
ReportListingApplication = _document_report('report_listing_application', 'edu.application')
ReportListingEnrollment = _document_report('report_listing_enrollment', 'edu.enrollment')
ReportListingTransfer = _document_report('report_listing_transfer', 'edu.transfer')
ReportListingStudent = _document_report('report_listing_student', 'edu.student')
ReportListingConfirmation = _document_report('report_listing_confirmation', 'edu.enrollment.confirmation')
ReportApplicationReceipt = _document_report('report_application_receipt', 'edu.application')
ReportListingCalendar = _document_report('report_listing_calendar', 'edu.calendar.event')


class ReportTerm(models.AbstractModel):
    _name = 'report.edu_documents.report_term'
    _inherit = 'edu.report.mixin'
    _description = 'Documento escolar: termo de frequência'
    _report_model = 'edu.document'

    def _extra_values(self, docs):
        """Por documento: as matrículas do aluno no curso, por classe, e as disciplinas de todas elas."""
        terms = {}
        for document in docs:
            enrollment = document.enrollment_id
            enrollments = document.student_id.enrollment_ids.filtered(
                lambda e, c=enrollment.course_id: e.course_id == c and e.state not in ('draft',)
            ).sorted(lambda e: e.class_number)
            results = enrollments.subject_result_ids
            subjects = Helpers.ordered(results).subject_id
            cells = {(r.enrollment_id.id, r.subject_id.id): r for r in results}
            terms[document.id] = {'enrollments': enrollments, 'subjects': subjects, 'cells': cells}
        return {'terms': terms}


SCHEDULE_DAYS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']


class EduClass(models.Model):
    _inherit = 'edu.class'

    def _document_context(self, *extra):
        """A linha da turma por baixo do título da pauta, da mini-pauta e do horário."""
        self.ensure_one()
        context = [
            f'ANO LECTIVO: {self.academic_year_id.name}',
            f'CLASSE: {self.class_number}ª',
            f'TURMA: {self.name}',
        ]
        if self.course_id:
            context.append(f'CURSO: {self.course_id.name}')
        return '\u2003\u2003'.join(context + [p for p in extra if p])

    def _schedule_doc(self):
        """Horário da turma no estilo da pauta: grelha com os tempos na vertical e segunda a sexta (e o sábado, se
        tiver aulas) na horizontal; em cada aula a disciplina, o professor e a sala."""
        self.ensure_one()
        schedules = self._edu_current_schedules()
        days = [0, 1, 2, 3, 4] + ([5] if schedules.filtered(lambda s: s.weekday == '5') else [])
        rows = sorted({(s.hour_from, s.hour_to) for s in schedules})
        cells = {(int(s.weekday), s.hour_from, s.hour_to): s for s in schedules}

        def hour(value):
            hours, minutes = divmod(round(value * 60), 60)
            return f'{hours:02d}:{minutes:02d}'

        grid = []
        for hour_from, hour_to in rows:
            line = []
            for day in days:
                schedule = cells.get((day, hour_from, hour_to))
                line.append(
                    [p for p in [schedule.subject_id.name, schedule.teacher_id.name, schedule.room_id.name] if p]
                    if schedule
                    else None
                )
            grid.append({'hours': (hour(hour_from), hour(hour_to)), 'cells': line})
        return {
            'title': 'HORÁRIO DA TURMA',
            'context': self._document_context(
                self.shift_id and f'TURNO: {self.shift_id.name}', self.room_id and f'SALA: {self.room_id.name}'
            ),
            'days': [SCHEDULE_DAYS[d] for d in days],
            'rows': grid,
            'day_width': (100 - 8) / len(days),
        }

    def action_print_directors(self):
        """As turmas escolhidas ou, sem escolha, as do ano lectivo em curso."""
        records = self or self.search([('academic_year_id.is_current', '=', True)])
        return self.env.ref('edu_documents.action_report_class_directors').preview_action(records)

    def _directors_context(self):
        with_director = len(self.filtered('director_id'))
        return '\u2003\u2003'.join(
            [
                f'ANO LECTIVO: {_current_year_name(self.env)}',
                self.env._('%(with)s DE %(total)s TURMAS COM DIRECTOR', total=len(self), **{'with': with_director}),
            ]
        )

    def action_print_class_list(self):
        # Abre a pré-visualização; o visualizador de PDF imprime e descarrega.
        return self.env.ref('edu_documents.action_report_class_list').preview_action(self)

    def action_print_schedule(self):
        return self.env.ref('edu_documents.action_report_class_schedule').preview_action(self)

    def action_print_pautas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Imprimir pautas'),
            'res_model': 'edu.pauta.print',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_class_id': self.id},
        }


class EduCurriculum(models.Model):
    _inherit = 'edu.curriculum'

    def _curriculum_context(self):
        """A linha por baixo do título do plano: curso, nível e classes."""
        self.ensure_one()
        parts = [
            self.course_id and f'CURSO: {self.course_id.name}',
            f'NÍVEL: {self.level_id.name}',
            self.class_from and f'CLASSES: {self.class_from}ª A {self.class_to}ª',
        ]
        return '\u2003\u2003'.join(p for p in parts if p)

    def action_print_curriculum(self):
        return self.env.ref('edu_documents.action_report_curriculum').preview_action(self)


class EduCourse(models.Model):
    _inherit = 'edu.course'

    def action_print_curriculum(self):
        self.ensure_one()
        if not self.curriculum_id:
            raise UserError(self.env._('O curso ainda não tem plano curricular.'))
        return self.curriculum_id.action_print_curriculum()


def _current_year_name(env):
    return env.company.edu_current_year_id.name or ''


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    def _edu_teachers(self):
        """Os professores escolhidos na lista ou, sem escolha, todos os da escola."""
        return self or self.search([('edu_is_teacher', '=', True), ('company_id', '=', self.env.company.id)])

    def action_print_teachers(self):
        return self.env.ref('edu_documents.action_report_teachers').preview_action(self._edu_teachers())

    def action_print_teacher_schedule(self):
        return self.env.ref('edu_documents.action_report_teacher_schedule').preview_action(self)

    def _teachers_context(self):
        directors = len(self.filtered('edu_directed_class'))
        return '\u2003\u2003'.join(
            [
                f'ANO LECTIVO: {_current_year_name(self.env)}',
                self.env._('%s DOCENTES', len(self)),
                self.env._('%s DIRECTORES DE TURMA', directors),
            ]
        )

    def _teacher_schedule_context(self):
        self.ensure_one()
        parts = [
            f'PROFESSOR(A): {self.name}',
            f'ANO LECTIVO: {_current_year_name(self.env)}',
            self.edu_load_label and self.env._('TEMPOS SEMANAIS: %s', self.edu_load_label),
        ]
        return '\u2003\u2003'.join(p for p in parts if p)


class EduTeachingAssignment(models.Model):
    _inherit = 'edu.teaching.assignment'

    def action_print_assignments(self):
        """As colocações escolhidas ou, sem escolha, as do ano lectivo em curso."""
        records = self or self.search([('academic_year_id.is_current', '=', True)])
        return self.env.ref('edu_documents.action_report_assignments').preview_action(records)

    def _assignment_groups(self):
        """Por turma (com a sigla do curso): as colocações e as disciplinas do plano ainda sem professor."""
        groups = []
        classes = self.class_id
        # Impressas todas as colocações do ano: entram também as turmas ainda sem nenhum professor.
        years = self.academic_year_id
        if len(years) == 1 and len(self) == self.search_count([('academic_year_id', '=', years.id)]):
            classes |= (
                self.env['edu.class'].search([('academic_year_id', '=', years.id)]).filtered('missing_teacher_subjects')
            )
        for edu_class in classes.sorted(lambda c: (c.class_number, c.course_id.code or '', c.name)):
            rows = self.filtered(lambda a, c=edu_class: a.class_id == c).sorted(lambda a: a.subject_id.name or '')
            groups.append({'class': edu_class, 'rows': rows, 'missing': edu_class.missing_teacher_subjects})
        return groups

    def _assignments_context(self):
        return '\u2003\u2003'.join(
            [f'ANO LECTIVO: {_current_year_name(self.env)}', self.env._('%s PROFESSORES', len(self.teacher_id))]
        )


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def report_action(self, docids, data=None, config=True):
        # Os documentos escolares têm timbre próprio: não passam pelo assistente do layout das facturas.
        report = self
        if self.report_name and self.report_name.startswith('edu_documents.'):
            report = self.with_context(discard_logo_check=True)
        return super(IrActionsReport, report).report_action(docids, data=data, config=config)
