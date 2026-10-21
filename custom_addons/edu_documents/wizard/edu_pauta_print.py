import unicodedata

from odoo import api, fields, models
from odoo.addons.edu_evaluation.tools.grading import round_units

from ..models.report_helpers import Helpers

ROMAN = {1: 'I', 2: 'II', 3: 'III', 4: 'IV'}
# Largura das colunas da pauta (px a 96 ppp, medida no PDF) para dividir as disciplinas por folhas A3, como o
# secPed; as folhas cheias esticam a tabela à largura da página.
PAGE_WIDTH = 1500
IDENTITY_WIDTH = 180
GRADE_WIDTH = 22
ABSENCE_WIDTH = 12
FINAL_WIDTH = 19
TAIL_WIDTH = 120
LEGEND_TECHNICAL = (
    'NPP - Nota do Professor; NPT - Nota da Prova Trimestral; CT1/CT2/CT3 - Classificação do Trimestre: '
    'CT = (NPP+NPT)/2; CF - Classificação de Frequência (média das CT, atribuída pelo Conselho de Turma); '
    'PG - Prova Global; CA - Classificação Anual: CA = 60%CF + 40%PG'
)
LEGEND_GENERAL = (
    'MAC - Média das Avaliações Contínuas; NPT - Nota da Prova Trimestral; MT - Média do Trimestre: '
    'MT = (MAC+NPT)/2; MFD - Média Final da Disciplina: MFD = (MT1+MT2+MT3)/3'
)
LEGEND_NATIONAL = '; EN - Exame Nacional; MFED - Média Final de Exame da Disciplina'
LEGEND_COMMON = (
    'Ex - Exame; CFD - Classificação Final da Disciplina; a) Disciplina já feita; b) Sem elementos de avaliação; '
    'c) Matrícula anulada; d) Transferido; EEF - Excluído por excesso de faltas'
)
# Situação na coluna «Resultado»: texto e cor (azul transita, verde transferido, preto exame/pendente, vermelho).
VERDICTS = {
    'promoted': ('Transita', 'pos'),
    'graduated': ('Concluiu', 'pos'),
    'conditional': ('Transita c/ atraso', 'pos'),
    'exam': ('Exame', None),
    'retained': ('Não transita', 'neg'),
    'pending': ('Pendente', None),
}
EXIT_CODES = {'dropped': ('c)', 'Anulada', 'neg'), 'transferred': ('d)', 'Transferido', 'green')}


class EduPautaPrint(models.TransientModel):
    """Impressão da mini-pauta (disciplina e trimestre) e da pauta da turma (trimestral ou final)."""

    _name = 'edu.pauta.print'
    _description = 'Impressão de pautas'

    class_id = fields.Many2one('edu.class', string='Turma', required=True)
    company_id = fields.Many2one(related='class_id.company_id')
    academic_year_id = fields.Many2one(related='class_id.academic_year_id')
    kind = fields.Selection(
        [('mini', 'Mini-pauta (disciplina)'), ('final', 'Pauta da turma')],
        string='Documento',
        required=True,
        default='final',
    )
    subject_id = fields.Many2one('edu.subject', string='Disciplina')
    trimester_id = fields.Many2one(
        'edu.trimester',
        string='Trimestre',
        domain="[('academic_year_id', '=', academic_year_id)]",
        compute='_compute_trimester_id',
        store=True,
        readonly=False,
        help='A pauta mostra as classificações até este trimestre. A situação (transita, não transita) só sai na '
        'pauta do último trimestre.',
    )
    regime = fields.Char(compute='_compute_regime')

    @api.depends('class_id')
    def _compute_trimester_id(self):
        """No ano em curso, o trimestre em curso; num ano fechado, o último (o da pauta final)."""
        for wizard in self:
            trimesters = wizard.class_id.academic_year_id.trimester_ids.sorted('number')
            if wizard.trimester_id in trimesters:
                continue
            wizard.trimester_id = trimesters.filtered('is_current')[:1] or trimesters[-1:]

    @api.depends('class_id')
    def _compute_regime(self):
        for wizard in self:
            policy = self.env['edu.evaluation.policy']._get(wizard.class_id.company_id, wizard.class_id.level_id)
            wizard.regime = policy.regime

    def _trimester_number(self):
        """Até que trimestre vai a pauta (sem trimestre escolhido, o ano inteiro)."""
        trimesters = self.class_id.academic_year_id.trimester_ids
        return self.trimester_id.number or max(trimesters.mapped('number') or [3])

    def _is_final(self):
        """A pauta do último trimestre é a final: classificação do ano, exames e situação."""
        trimesters = self.class_id.academic_year_id.trimester_ids
        return self._trimester_number() >= max(trimesters.mapped('number') or [3])

    def _policy(self):
        return self.env['edu.evaluation.policy']._get(self.class_id.company_id, self.class_id.level_id)

    def _enrollments(self):
        return self.class_id.enrollment_ids.filtered(lambda e: e.state != 'draft').sorted('order_number')

    def _subjects(self):
        results = self.env['edu.subject.result'].search([('class_id', '=', self.class_id.id)])
        return Helpers.ordered(results).subject_id or self.class_id.subject_line_ids.subject_id

    def _results(self):
        return {
            (r.enrollment_id.id, r.subject_id.id): r
            for r in self.env['edu.subject.result'].search([('class_id', '=', self.class_id.id)])
        }

    def _terms(self):
        domain = [('class_id', '=', self.class_id.id), ('subject_id', '=', self.subject_id.id)]
        return {(t.enrollment_id.id, t.trimester_id.number): t for t in self.env['edu.term.result'].search(domain)}

    def _absences(self):
        domain = [('class_id', '=', self.class_id.id), ('subject_id', '=', self.subject_id.id)]
        if self.trimester_id:
            domain.append(('trimester_id', '=', self.trimester_id.id))
        rows = self.env['edu.absence.summary'].search(domain)
        totals = {}
        for row in rows:
            excused, absent = totals.get(row.enrollment_id.id, (0, 0))
            totals[row.enrollment_id.id] = (excused + row.excused, absent + row.absent)
        return totals

    # ------------------------------------------------------------------
    # Pauta da turma (mapa de aproveitamento), com a estrutura do secPed
    # ------------------------------------------------------------------
    def _pauta_data(self):
        """Tudo o que o modelo da pauta desenha: colunas por regime, linhas dos alunos (texto e cor de cada célula),
        professores, divisão das disciplinas por folhas, legenda e assinaturas. O HTML e o PDF usam o mesmo."""
        self.ensure_one()
        policy = self._policy()
        technical = self.regime == 'technical'
        number = self._trimester_number()
        final = self._is_final()
        trimester = (
            self.trimester_id or self.class_id.academic_year_id.trimester_ids.filtered(lambda t: t.number == number)[:1]
        )
        # Disciplinas por ordem alfabética, como na pauta do secPed.
        subjects = self._subjects().sorted(lambda s: unicodedata.normalize('NFKD', s.name or '').casefold())
        results = self._results()
        national = (
            final
            and not technical
            and policy._is_exam_class(self.class_id.class_number)
            and any(subjects.mapped('is_national_exam'))
        )
        base = ['NPP', 'NPT', 'CT', 'FJ', 'FI'] if technical else ['MAC', 'NPT', 'MT', 'FJ', 'FI']
        tail = []
        if final:
            tail = ['CF', 'PG', 'CA'] if technical else (['MFD', 'CFD', 'EN', 'MFED'] if national else ['MFD', 'CFD'])
        labels = base + tail
        pass_grade = policy.pass_grade
        terms = {
            (t.enrollment_id.id, t.subject_id.id): t
            for t in self.env['edu.term.result'].search(
                [('class_id', '=', self.class_id.id), ('trimester_id', '=', trimester.id)]
            )
        }
        absences = {}
        if 'edu.absence.summary' in self.env:
            for row in self.env['edu.absence.summary'].search(
                [('class_id', '=', self.class_id.id), ('trimester_id', '=', trimester.id)]
            ):
                key = (row.enrollment_id.id, row.subject_id.id)
                excused, absent = absences.get(key, (0, 0))
                absences[key] = (excused + row.excused, absent + row.absent)
        year_results = self._year_results()

        def grade(value, decimals=1, show=True):
            if not show or value is None:
                return ('', None)
            text = f'{value:.1f}'.replace('.', ',') if decimals else str(round_units(value))
            shown = value if decimals else round_units(value)
            return (text, 'pos' if shown >= pass_grade else 'neg')

        def count(value):
            return (str(value) if value else '', None)

        rows = []
        for enrollment in self._enrollments():
            exit_code = EXIT_CODES.get(enrollment.state)
            cells = {}
            for subject in subjects:
                key = (enrollment.id, subject.id)
                excused, absent = absences.get(key, (0, 0))
                if exit_code:
                    code = (exit_code[0], None)
                    cells[subject.id] = [code, code, code, count(excused), count(absent)] + [code] * len(tail)
                    continue
                term = terms.get(key)
                values = [
                    grade(term.mac, show=bool(term and term.has_mac)) if term else ('', None),
                    grade(term.npt, show=bool(term and term.has_npt)) if term else ('', None),
                    # CT/MT: classificação do trimestre, um inteiro (as importadas guardam as casas decimais).
                    grade(round_units(term.mt), show=bool(term and term.has_mt)) if term else ('', None),
                    count(excused),
                    count(absent),
                ]
                result = results.get(key)
                if final:
                    complete = bool(result and result.complete)
                    if technical:
                        values += [
                            grade(result.cf, 0, complete) if result else ('', None),
                            grade(result.pg, 0, bool(result and result.has_pg)) if result else ('', None),
                            grade(result.final, 0, complete) if result else ('', None),
                        ]
                    else:
                        values += [
                            grade(result.cf, 0, complete) if result else ('', None),
                            grade(result.cfd, 0, complete and result.terminal_subject) if result else ('', None),
                        ]
                        if national:
                            has_exam = bool(result and result.has_national and subject.is_national_exam)
                            values += [
                                grade(result.national, 0, has_exam) if result else ('', None),
                                grade(result.annual, 0, has_exam and complete) if result else ('', None),
                            ]
                cells[subject.id] = values
            year_result = year_results.get(enrollment.id)
            if exit_code:
                verdict, negatives = (exit_code[1], exit_code[2]), ''
            elif year_result and year_result.absence_excluded:
                verdict, negatives = ('EEF', 'neg'), str(year_result.negative_count)
            elif year_result:
                verdict, negatives = VERDICTS.get(year_result.status, ('', None)), str(year_result.negative_count)
            else:
                verdict, negatives = ('Pendente', None), ''
            rows.append(
                {
                    'number': enrollment.order_number or '',
                    'name': enrollment.student_id.name,
                    'cells': cells,
                    'negatives': negatives,
                    'verdict': verdict,
                }
            )

        teachers = {}
        assignments = self.env['edu.teaching.assignment'].sudo().search([('class_id', '=', self.class_id.id)])
        for subject in subjects:
            mine = assignments.filtered(lambda a, s=subject: a.subject_id == s)
            chosen = (
                mine.filtered(lambda a: a.trimester_id == trimester)[:1]
                or mine.filtered(lambda a: not a.trimester_id)[:1]
                or mine[:1]
            )
            teachers[subject.id] = chosen.teacher_id.name or '—'

        # Folhas: a 1.ª começa com Nº e Aluno; o Resultado tem de caber na última (como no secPed).
        width_of = {}
        for subject in subjects:
            columns = 3 * GRADE_WIDTH + 2 * ABSENCE_WIDTH + len(tail) * FINAL_WIDTH
            width_of[subject.id] = max(columns, len(subject.name) * 4)  # o nome quebra em duas linhas
        chunks, current, used = [], [], IDENTITY_WIDTH
        for subject in subjects:
            if current and used + width_of[subject.id] > PAGE_WIDTH:
                chunks.append(current)
                current, used = [], 0
            current.append(subject)
            used += width_of[subject.id]
        if current:
            chunks.append(current)
        if final and chunks:
            while True:
                last = chunks[-1]
                start = IDENTITY_WIDTH if len(chunks) == 1 else 0
                if start + sum(width_of[s.id] for s in last) + TAIL_WIDTH <= PAGE_WIDTH or len(last) <= 1:
                    break
                chunks.append([last.pop()])

        legend = LEGEND_TECHNICAL if technical else LEGEND_GENERAL + (LEGEND_NATIONAL if national else '')
        context = [
            f'ANO LECTIVO: {self.class_id.academic_year_id.name}',
            f'CLASSE: {self.class_id.class_number}ª',
            f'TURMA: {self.class_id.name}',
        ]
        if self.class_id.course_id:
            context.append(f'CURSO: {self.class_id.course_id.name}')
        return {
            'technical': technical,
            'final': final,
            'labels': labels,
            'span': len(labels),
            'subjects': subjects,
            'chunks': chunks or [subjects],
            'rows': rows,
            'teachers': teachers,
            'title': f'MAPA DE APROVEITAMENTO DO {ROMAN.get(number, number)}º TRIMESTRE',
            'context': '\u2003\u2003'.join(context),
            'legend': f'{legend}; {LEGEND_COMMON}',
            'scale': f'Escala 0–{policy.scale_max} · aprovação mínima {round_units(pass_grade)} valores.',
        }

    def _year_results(self):
        return {
            r.enrollment_id.id: r for r in self.env['edu.year.result'].search([('class_id', '=', self.class_id.id)])
        }

    def _report(self):
        return self.env.ref(
            'edu_documents.action_report_mini_pauta' if self.kind == 'mini' else 'edu_documents.action_report_pauta'
        )

    def action_preview(self):
        self.ensure_one()
        return self._report().preview_action(self)

    def action_print(self):
        self.ensure_one()
        return self._report().report_action(self)
