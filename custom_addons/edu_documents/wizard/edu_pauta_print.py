import unicodedata

from odoo import api, fields, models
from odoo.addons.edu_evaluation.tools.grading import grade_text, round_units, technical_chain

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
    'P1 - Nota do Professor; P2 - Nota da Prova Trimestral; CT - Classificação do Trimestre, que engloba os '
    'anteriores: CT1 = (P1+P2)/2, CT2 = (CT1 + média do 2.º)/2, CT3 = (CT2 + P1 do 3.º)/2; '
    'PG - Prova Global, no 3.º trimestre no lugar da P2 (disciplinas com 3 ou mais tempos semanais); '
    'CF - Classificação de Frequência (o CT3, atribuída pelo Conselho de Turma); '
    'CA - Classificação Anual: CA = 60%CF + 40%PG; CFD - Classificação Final da Disciplina '
    '(no ano terminal: média das CA dos anos em que é leccionada)'
)
LEGEND_GENERAL = (
    'MAC - Média das Avaliações Contínuas; NPT - Nota da Prova Trimestral; MT - Média do Trimestre: '
    'MT = (MAC+NPT)/2; MFD - Média Final da Disciplina: MFD = (MT1+MT2+MT3)/3'
)
LEGEND_NATIONAL = '; EN - Exame Nacional; MFED - Média Final de Exame da Disciplina'
LEGEND_COMMON = (
    'Ex - Exame; CFD - Classificação Final da Disciplina; a) Disciplina já feita; b) Sem elementos de avaliação; '
    'c) Matrícula anulada; d) Transferido; e) Feita na classe anterior; EEF - Excluído por excesso de faltas'
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
# Menções não negativas, a azul (DE 424/25, art. 35.º; Termos do Despacho 60/08): anulação e transferência.
EXIT_CODES = {'dropped': ('c)', 'Anulou a matrícula', 'pos'), 'transferred': ('d)', 'Transferido', 'pos')}


class EduPautaPrint(models.TransientModel):
    """Impressão da mini-pauta (disciplina e trimestre) e da pauta da turma (trimestral ou final)."""

    _name = 'edu.pauta.print'
    _description = 'Impressão de pautas'

    class_id = fields.Many2one('edu.class', string='Turma', required=True)
    company_id = fields.Many2one(related='class_id.company_id')
    academic_year_id = fields.Many2one(related='class_id.academic_year_id')
    kind = fields.Selection(
        [('mini', 'Mini-pauta (mapa condensado)'), ('final', 'Pauta da turma')],
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
        """As disciplinas do plano da turma e as que têm resultados (mesmo as que ainda não têm notas aparecem)."""
        results = self.env['edu.subject.result'].search([('class_id', '=', self.class_id.id)])
        # O director de turma (professor) não lê o plano curricular.
        return Helpers.ordered(results).subject_id | self.class_id.sudo().subject_line_ids.subject_id.with_env(self.env)

    def _national_subjects(self):
        """Disciplinas com exame nacional na turma: a marca da linha do plano ou a da disciplina."""
        lines = self.class_id.sudo().subject_line_ids
        national = lines.filtered(lambda line: line.is_national_exam or line.subject_id.is_national_exam).subject_id
        return national.with_env(self.env)

    def _results(self):
        Result = self.env['edu.subject.result']
        found = Result.search([('class_id', '=', self.class_id.id)])
        for enrollment, subjects in self._visitors().items():
            found |= Result.search([('enrollment_id', '=', enrollment.id), ('subject_id', 'in', subjects.ids)])
        return {(r.enrollment_id.id, r.subject_id.id): r for r in found}

    def _visitors(self):
        """Alunos de outras turmas que fazem aqui uma disciplina (Decreto Executivo 60/08, arts. 9.º e 10.º): por
        matrícula, as disciplinas que cá fazem."""
        visitors = {}
        if 'edu.enrollment.lower.subject' not in self.env:
            return visitors
        lines = self.env['edu.enrollment.lower.subject'].sudo().search([('class_id', '=', self.class_id.id)])
        for line in lines.filtered(lambda line: line.enrollment_id.state != 'draft'):
            visitors.setdefault(line.enrollment_id, self.env['edu.subject'])
            visitors[line.enrollment_id] |= line.subject_id
        return visitors

    def _terms(self, trimester):
        """Classificações do trimestre da turma e as dos alunos que cá fazem uma disciplina."""
        Term = self.env['edu.term.result']
        found = Term.search([('class_id', '=', self.class_id.id), ('trimester_id', '=', trimester.id)])
        for enrollment, subjects in self._visitors().items():
            found |= Term.search(
                [
                    ('enrollment_id', '=', enrollment.id),
                    ('subject_id', 'in', subjects.ids),
                    ('trimester_id', 'in', enrollment.academic_year_id.trimester_ids.filtered(
                        lambda t, n=trimester.number: t.number == n).ids),
                ]
            )  # fmt: skip
        return {(t.enrollment_id.id, t.subject_id.id): t for t in found}

    def _technical_cts(self, trimester):
        """O CT do técnico no trimestre, por (matrícula, disciplina): engloba os trimestres anteriores (Despacho 60/08,
        art. 17.º, n.º 5): CT1 = média do 1.º, CT2 = (CT1 + média do 2.º)/2, CT3 = (CT2 + média do 3.º)/2, sem
        arredondar. A partir da primeira nota do ano calcula-se até ao 3.º, com os trimestres ainda sem nota a contar 0
        (grading.technical_chain)."""
        trimesters = self.class_id.academic_year_id.trimester_ids.filtered(lambda t: t.number <= trimester.number)
        maps = [self._terms(t) for t in trimesters.sorted('number')]
        cts = {}
        for key in {key for found in maps for key in found}:
            values = [m[key].mt if key in m and m[key].has_mt else None for m in maps]
            ct = technical_chain(values)[-1] if values else None
            if ct is not None:
                cts[key] = ct
        return cts

    def _cell_mark(self, enrollment, subject):
        """«c)» na disciplina anulada, «e)» na que o aluno faz numa turma da classe anterior."""
        if 'subject_drop_ids' in enrollment._fields and subject in enrollment.subject_drop_ids.subject_id:
            return 'c)'
        if 'lower_subject_ids' in enrollment._fields and subject in enrollment.lower_subject_ids.subject_id:
            return 'e)'
        return False

    def _trimester_absences(self, trimester):
        """Faltas justificadas e injustificadas do trimestre por (matrícula, disciplina)."""
        totals = {}
        if 'edu.absence.summary' not in self.env:
            return totals
        domain = [('class_id', '=', self.class_id.id), ('trimester_id', '=', trimester.id)]
        for row in self.env['edu.absence.summary'].search(domain):
            key = (row.enrollment_id.id, row.subject_id.id)
            excused, absent = totals.get(key, (0, 0))
            totals[key] = (excused + row.excused, absent + row.absent)
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
        national_subjects = self._national_subjects()
        national = (
            final and not technical and policy._is_exam_class(self.class_id.class_number) and bool(national_subjects)
        )
        # Técnico: P1 e P2; no 3.º trimestre a P2 dá lugar à prova global (nas disciplinas com 3 ou mais tempos).
        if technical:
            base = ['P1', 'PG' if final else 'P2', 'CT', 'FJ', 'FI']
        else:
            base = ['MAC', 'NPT', 'MT', 'FJ', 'FI']
        tail = []
        if final:
            tail = ['CF', 'CA', 'CFD'] if technical else (['MFD', 'CFD', 'EN', 'MFED'] if national else ['MFD', 'CFD'])
        with_pg = {line.subject_id.id for line in self.class_id.sudo().subject_line_ids if line.has_global_exam}
        labels = base + tail
        pass_grade = policy.pass_grade
        terms = self._terms(trimester)
        cts = self._technical_cts(trimester) if technical else {}
        absences = self._trimester_absences(trimester)
        year_results = self._year_results()

        def grade(value, decimals=1, show=True):
            if not show or value is None:
                return ('', None)
            if not decimals:
                text, shown = str(round_units(value)), round_units(value)
            elif technical:
                # Técnico: as notas com as casas decimais que tiverem; só a CA e a CFD se arredondam.
                text, shown = grade_text(value), value
            else:
                text, shown = f'{value:.1f}'.replace('.', ','), value
            return (text, 'pos' if shown >= pass_grade else 'neg')

        def count(value):
            return (str(value) if value else '', None)

        rows = []
        visitors = self._visitors()
        for enrollment in self._enrollments() | self.env['edu.enrollment'].concat(*visitors):
            exit_code = EXIT_CODES.get(enrollment.state)
            only = visitors.get(enrollment) if enrollment.class_id != self.class_id else None
            cells = {}
            for subject in subjects:
                key = (enrollment.id, subject.id)
                excused, absent = absences.get(key, (0, 0))
                if only is not None and subject not in only:
                    cells[subject.id] = [('', None)] * (len(base) + len(tail))
                    continue
                mark = exit_code[0] if exit_code else self._cell_mark(enrollment, subject)
                if mark:
                    code = (mark, None)
                    cells[subject.id] = [code, code, code, count(excused), count(absent)] + [code] * len(tail)
                    continue
                term = terms.get(key)
                if technical:
                    # CT: engloba os anteriores e existe a partir da primeira nota do ano, mesmo sem nota neste.
                    classification = grade(cts.get(key))
                elif term:
                    classification = grade(round_units(term.mt), show=term.has_mt)
                else:
                    classification = ('', None)
                result = results.get(key)
                if technical and final:
                    # 3.º trimestre do técnico: a PG no lugar da P2; «—» nas disciplinas sem prova global.
                    if subject.id in with_pg or (result and result.has_global_exam):
                        second = grade(result.pg, show=result.has_pg) if result else ('', None)
                    else:
                        second = ('—', None)
                else:
                    second = grade(term.npt, show=bool(term and term.has_npt)) if term else ('', None)
                values = [
                    grade(term.mac, show=bool(term and term.has_mac)) if term else ('', None),
                    second,
                    classification,
                    count(excused),
                    count(absent),
                ]
                if final:
                    complete = bool(result and result.complete)
                    if technical:
                        # CF e CA calculadas a partir da primeira nota do ano; a CF sem arredondar, a CA arredondada.
                        started = bool(result and result.trimesters_graded)
                        values += [
                            grade(result.cf, show=started) if result else ('', None),
                            grade(result.final, 0, started) if result else ('', None),
                            # CFD no ano terminal da disciplina (a que conta nas negativas e no certificado).
                            grade(result.cfd, 0, complete and result.terminal_subject) if result else ('', None),
                        ]
                    else:
                        values += [
                            # MFD: a classificação final do ano (com a bonificação do conselho ou o exame).
                            grade(result.final, 0, complete) if result else ('', None),
                            grade(result.cfd, 0, complete and result.terminal_subject) if result else ('', None),
                        ]
                        if national:
                            has_exam = bool(result and result.has_national and subject in national_subjects)
                            values += [
                                grade(result.national, 0, has_exam) if result else ('', None),
                                grade(result.annual, 0, has_exam and complete) if result else ('', None),
                            ]
                cells[subject.id] = values
            year_result = year_results.get(enrollment.id)
            if only is not None:
                verdict, negatives = (f'Da {enrollment.class_id.class_number}ª classe', None), ''
            elif exit_code:
                verdict, negatives = (exit_code[1], exit_code[2]), ''
            elif year_result and year_result.absence_excluded:
                verdict, negatives = ('EEF', 'neg'), str(year_result.negative_count)
            elif year_result:
                verdict, negatives = VERDICTS.get(year_result.status, ('', None)), str(year_result.negative_count)
            else:
                verdict, negatives = ('Pendente', None), ''
            rows.append(
                {
                    'number': '' if only is not None else enrollment.order_number or '',
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
            'context': self.class_id._document_context(),
            'legend': f'{legend}; {LEGEND_COMMON}',
            'scale': f'Escala 0–{policy.scale_max} · aprovação mínima {round_units(pass_grade)} valores.',
        }

    def _mini_pauta_data(self):
        """Mini-pauta como a do secPed: mapa condensado do trimestre da turma — uma letra por disciplina (A), B)…, a
        referência das disciplinas em dívida), por aluno e disciplina a classificação do trimestre (CT no técnico,
        MT no geral; no último trimestre a CF) com as faltas justificadas e injustificadas, e a média."""
        self.ensure_one()
        policy = self._policy()
        technical = self.regime == 'technical'
        number = self._trimester_number()
        final = self._is_final()
        trimester = (
            self.trimester_id or self.class_id.academic_year_id.trimester_ids.filtered(lambda t: t.number == number)[:1]
        )
        subjects = self._subjects().sorted(lambda s: unicodedata.normalize('NFKD', s.name or '').casefold())
        label = 'CF' if final else (f'CT{number}' if technical else 'MT')
        if final:
            description = 'classificação de frequência do ano' if technical else 'classificação final do ano'
        else:
            description = 'classificação do trimestre, que engloba os anteriores' if technical else 'média do trimestre'
        results = self._results()
        terms = self._terms(trimester)
        cts = self._technical_cts(trimester) if technical else {}
        absences = self._trimester_absences(trimester)
        rows = []
        visitors = self._visitors()
        for enrollment in self._enrollments() | self.env['edu.enrollment'].concat(*visitors):
            only = visitors.get(enrollment) if enrollment.class_id != self.class_id else None
            cells, values = {}, []
            for subject in subjects:
                key = (enrollment.id, subject.id)
                mark = self._cell_mark(enrollment, subject)
                if (only is not None and subject not in only) or mark:
                    cells[subject.id] = (mark or '', False, '', '')
                    continue
                if final:
                    result = results.get(key)
                    if technical:
                        # A CF assim que o último trimestre tem notas (sem esperar pela PG), como a grelha e a pauta;
                        # a importada da pauta assinada, quando existe.
                        value = result.cf if result and result.has_imported_cf else cts.get(key)
                    elif result and result.complete:
                        # Geral: a classificação final (com a bonificação ou o exame).
                        value = result.final
                    else:
                        value = result.cf if result and result.trimesters_graded else None
                else:
                    term = terms.get(key)
                    if technical:
                        value = cts.get(key)
                    else:
                        value = term.mt if term and term.has_mt else None
                excused, absent = absences.get(key, (0, 0))
                # Técnico: o CT e a CF com as casas decimais que tiverem (só a CA e a CFD se arredondam).
                shown = value if technical else (round_units(value) if value is not None else None)
                cells[subject.id] = (
                    '—' if shown is None else (grade_text(shown) if technical else str(shown)),
                    shown is not None and shown < policy.pass_grade,
                    str(excused) if excused else '·',
                    str(absent) if absent else '·',
                )
                if value is not None:
                    values.append(value)
            average = sum(values) / len(values) if values else None
            if average is None:
                average_text = '—'
            elif technical:
                average_text = grade_text(average)  # técnico: com as casas decimais (só a CA e a CFD se arredondam)
            else:
                average_text = str(round_units(average))
            rows.append(
                {
                    'number': '' if only is not None else enrollment.order_number or '',
                    'name': enrollment.student_id.name,
                    'cells': cells,
                    'average': average_text,
                }
            )
        count = max(len(subjects), 1)
        name_pct = 22 if count <= 8 else (19 if count <= 12 else 16)
        subject_pct = (100 - 2.2 - 3.2 - name_pct) / count
        return {
            'subjects': subjects,
            'letters': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'label': label,
            'rows': rows,
            'title': f'MAPA DE APROVEITAMENTO REFERENTE AO {ROMAN.get(number, number)} TRIMESTRE',
            'context': self.class_id._document_context(),
            'note': f'{label} — {description} · FJ/FI — faltas justificadas/injustificadas · negativas '
            f'(< {round_units(policy.pass_grade)}) a vermelho.',
            'name_pct': name_pct,
            'subject_pct': subject_pct,
            # Colunas estreitas: os nomes das disciplinas em minúsculas e mais pequenos, para não partirem a meio.
            'tight': subject_pct < 7.5,
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
