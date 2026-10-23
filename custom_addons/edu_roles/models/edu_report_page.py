import base64
import io
from collections import defaultdict

import xlsxwriter

from odoo import api, fields, models
from odoo.addons.edu_evaluation.models.edu_evaluation_policy import LEVEL_DEFAULTS
from odoo.addons.edu_evaluation.tools import grading
from odoo.exceptions import AccessError, UserError

GROUPS = {'subsystem': 'Subsistema', 'level': 'Nível', 'course': 'Curso', 'class': 'Turma'}
# Matrículas que contam no ano: a frequentar e, num ano fechado, as que terminaram (concluiu ou ficou retido).
COUNTED = ('active', 'irregular', 'completed', 'retained')
APPROVED = ('promoted', 'graduated', 'conditional')
# Contam só as matrículas do ano: um aluno que saiu (transferido, anulou) fica de fora das notas e dos resultados.
COUNTED_DOMAIN = [('enrollment_id.state', 'in', COUNTED)]


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _avg(total, count):
    return round(total / count, 1) if count else None


class EduReportPage(models.AbstractModel):
    """Página «Relatórios» (acção cliente ``edu_roles.reports``), como a do secPed-Express: os números da escola num ano
    lectivo, por subsistema, nível, curso ou turma. Durante o ano contam as matrículas, as notas do trimestre e as
    chamadas; o resultado final e as classificações por disciplina aparecem quando os conselhos de turma fecham.
    Cada quadro diz primeiro, numa frase, o que conta; tudo exporta para Excel e PDF."""

    _name = 'edu.report.page'
    _description = 'Relatórios da escola'

    @api.model
    def options(self):
        years = self.env['edu.academic.year'].search(
            [('company_id', 'in', self.env.companies.ids)], order='date_start desc'
        )
        current = years.filtered('is_current')[:1] or years[:1]
        several = len(years.company_id) > 1
        return {
            'years': [
                {'id': y.id, 'name': f'{y.name} · {y.company_id.name}' if several else y.name, 'current': y.is_current}
                for y in years
            ],
            'year_id': current.id or False,
            'groups': [{'value': k, 'label': v} for k, v in GROUPS.items()],
        }

    # Agrupar

    @api.model
    def _group_of(self, edu_class, group_by):
        """(chave, nome, linha de baixo) do grupo da turma."""
        level = edu_class.level_id
        if group_by == 'subsystem':
            label = dict(level._fields['subsystem']._description_selection(self.env)).get(level.subsystem, '')
            return level.subsystem or '', label, ''
        if group_by == 'level':
            return level.id, level.name, ''
        if group_by == 'course':
            return edu_class.course_id.id, edu_class.course_id.name or '', level.name
        return edu_class.id, edu_class._editor_label(), edu_class.course_id.name or ''

    @api.model
    def _fold(self, classes, group_by, per_class, empty):
        """Junta os números de cada turma (``per_class``: {turma: dict}) nos grupos; ``empty`` dá os zeros."""
        groups = {}
        for edu_class in classes.sorted(lambda c: (c.class_number, c.course_id.name or '', c.name)):
            values = per_class.get(edu_class.id)
            if not values:
                continue
            key, label, sub = self._group_of(edu_class, group_by)
            group = groups.setdefault(key, {'key': str(key), 'label': label, 'sub': sub, **empty()})
            for name, value in values.items():
                group[name] += value
        return list(groups.values())

    @api.model
    def _policies(self, classes):
        """Nota mínima, arredondamento e escala de cada turma, lidos de uma vez (sem criar regimes que faltem: usa os
        valores do RAA para o nível)."""
        policies = (
            self.env['edu.evaluation.policy']
            .sudo()
            .search([('company_id', 'in', classes.company_id.ids), ('level_id', 'in', classes.level_id.ids)])
        )
        by_key = {(p.company_id.id, p.level_id.id): p for p in policies}
        result = {}
        for edu_class in classes:
            policy = by_key.get((edu_class.company_id.id, edu_class.level_id.id))
            if policy:
                result[edu_class.id] = (policy.pass_grade, grading.rounder(policy.rounding), policy.scale_max)
            else:
                defaults = LEVEL_DEFAULTS.get(edu_class.level_id.code, {})
                result[edu_class.id] = (
                    defaults.get('pass_grade', 10),
                    grading.rounder(defaults.get('rounding', 'integer')),
                    defaults.get('scale_max', 20),
                )
        return result

    # Quadros

    @api.model
    def _enrollments(self, year, classes, group_by):
        Enrollment = self.env['edu.enrollment']
        counts = {
            edu_class.id: count
            for edu_class, count in Enrollment._read_group(
                [('academic_year_id', '=', year.id), ('state', 'in', COUNTED), ('class_id', 'in', classes.ids)],
                ['class_id'],
                ['__count'],
            )
        }
        rows = self._fold(classes, group_by, {c: {'total': n} for c, n in counts.items()}, lambda: {'total': 0})
        total = sum(counts.values())
        for row in rows:
            row['pct'] = _pct(row['total'], total)
        return {'total': total, 'classes': len([c for c in counts if c]), 'rows': rows}

    @api.model
    def _trimester_grades(self, year, classes, group_by, trimester_id):
        trimesters = year.trimester_ids.sorted('number')
        TermResult = self.env['edu.term.result']
        with_grades = {
            trimester.id
            for (trimester,) in TermResult._read_group(
                [('trimester_id', 'in', trimesters.ids), ('has_mt', '=', True)], ['trimester_id']
            )
        }
        trimester = trimesters.browse(trimester_id) if trimester_id in trimesters.ids else None
        if not trimester:
            # Sem escolha: o trimestre em curso, se já tem notas; senão o último com notas.
            current = trimesters.filtered('is_current')
            trimester = (
                current if current.id in with_grades else trimesters.filtered(lambda t: t.id in with_grades)[-1:]
            )
            trimester = trimester or current or trimesters[:1]
        data = {
            'trimesters': [
                {'id': t.id, 'name': t.name, 'current': t.is_current, 'closed': t.state == 'closed'} for t in trimesters
            ],
            'trimester_id': trimester.id or False,
            'trimester': trimester.name or '',
        }
        results = (
            TermResult.search_read(
                [
                    ('trimester_id', '=', trimester.id),
                    ('has_mt', '=', True),
                    ('class_id', 'in', classes.ids),
                    *COUNTED_DOMAIN,
                ],
                ['class_id', 'enrollment_id', 'mt'],
            )
            if trimester
            else []
        )
        policies = self._policies(classes)
        per_class = defaultdict(lambda: {'grades': 0, 'positive': 0, 'sum': 0.0})
        negative = defaultdict(set)
        students = defaultdict(set)
        for result in results:
            class_id = result['class_id'][0]
            row = per_class[class_id]
            row['grades'] += 1
            row['sum'] += result['mt']
            students[class_id].add(result['enrollment_id'][0])
            pass_grade, round_fn, _scale = policies[class_id]
            # Como na grelha e na pauta: a nota arredondada pela regra da escola (9,5 é 10, positiva).
            if round_fn(result['mt']) >= pass_grade:
                row['positive'] += 1
            else:
                negative[class_id].add(result['enrollment_id'][0])
        for class_id, row in per_class.items():
            row['students'] = len(students[class_id])
            row['with_negative'] = len(negative[class_id])
        rows = self._fold(
            classes,
            group_by,
            per_class,
            lambda: {'grades': 0, 'positive': 0, 'sum': 0.0, 'students': 0, 'with_negative': 0},
        )
        for row in rows:
            row['pct'] = _pct(row['positive'], row['grades'])
            # Por subsistema não há média: o primário dá notas de 0 a 10 e o resto de 0 a 20.
            row['average'] = None if group_by == 'subsystem' else _avg(row.pop('sum'), row['grades'])
            row.pop('sum', None)
        grades = sum(r['grades'] for r in rows)
        # Distribuição das notas de 0 a 20 (o primário, de 0 a 10, fica de fora): quantas com cada valor, arredondado
        # às unidades; a linha e a cor seguem a nota mínima mais comum nessas turmas.
        histogram = [0] * 21
        pass_marks = defaultdict(int)
        for result in results:
            pass_grade, _round_fn, scale = policies[result['class_id'][0]]
            if scale == 20:
                histogram[min(20, max(0, grading.round_units(result['mt'])))] += 1
                pass_marks[pass_grade] += 1
        data.update(
            {
                'grades': grades,
                'pct': _pct(sum(r['positive'] for r in rows), grades),
                'students': sum(len(s) for s in students.values()),
                'with_negative': sum(len(s) for s in negative.values()),
                'rows': rows,
                'histogram': histogram if sum(histogram) else [],
                'histogram_pass': max(pass_marks, key=pass_marks.get) if pass_marks else 10,
                'by_trimester': self._grades_by_trimester(trimesters, classes, policies),
            }
        )
        return data

    @api.model
    def _grades_by_trimester(self, trimesters, classes, policies):
        """A percentagem de positivas em cada trimestre do ano: a evolução ao longo do ano."""
        counts = defaultdict(lambda: [0, 0])
        for result in self.env['edu.term.result'].search_read(
            [
                ('trimester_id', 'in', trimesters.ids),
                ('has_mt', '=', True),
                ('class_id', 'in', classes.ids),
                *COUNTED_DOMAIN,
            ],
            ['class_id', 'trimester_id', 'mt'],
        ):
            pass_grade, round_fn, _scale = policies[result['class_id'][0]]
            count = counts[result['trimester_id'][0]]
            count[0] += 1
            count[1] += round_fn(result['mt']) >= pass_grade
        return [
            {'name': t.name, 'grades': counts[t.id][0], 'pct': _pct(counts[t.id][1], counts[t.id][0])}
            for t in trimesters
        ]

    @api.model
    def _years_trend(self, company):
        """A taxa de transição de cada ano lectivo com resultados, na escola toda: a evolução de ano para ano. Contam
        os decididos (transitou ou ficou retido); quem está em exame de recurso ainda não tem resultado."""
        per_year = defaultdict(lambda: [0, 0])
        for year, status, count in self.env['edu.year.result']._read_group(
            [('status', 'not in', ('pending', 'exam')), ('company_id', '=', company.id), *COUNTED_DOMAIN],
            ['academic_year_id', 'status'],
            ['__count'],
        ):
            per_year[year][0] += count
            per_year[year][1] += count if status in APPROVED else 0
        return [
            {'id': year.id, 'name': year.name, 'evaluated': n, 'approved': a, 'pct': _pct(a, n)}
            for year, (n, a) in sorted(per_year.items(), key=lambda item: item[0].date_start)
        ]

    @api.model
    def _attendance(self, year, classes, group_by):
        Attendance = self.env['edu.lesson.attendance']
        per_class = defaultdict(lambda: {'calls': 0, 'present': 0, 'excluded': 0})
        for edu_class, state, count in Attendance._read_group(
            [('class_id', 'in', classes.ids), ('lesson_state', '=', 'done')], ['class_id', 'state'], ['__count']
        ):
            row = per_class[edu_class.id]
            row['calls'] += count
            if state in ('present', 'late'):  # chegar atrasado conta como presença
                row['present'] += count
        if per_class:
            # O estado das faltas calcula-se linha a linha: só as do ano, de quem conta, com faltas que possam pesar.
            candidates = self.env['edu.absence.summary'].search(
                [('academic_year_id', '=', year.id), ('year_absent', '>=', 2), ('class_id', 'in', classes.ids)]
            )
            counted = set(
                self.env['edu.enrollment']
                .search([('id', 'in', candidates.enrollment_id.ids), ('state', 'in', COUNTED)])
                .ids
            )
            excluded = defaultdict(set)
            for summary in candidates.filtered(lambda s: s.enrollment_id.id in counted and s.status == 'failed'):
                excluded[summary.class_id.id].add(summary.enrollment_id.id)
            for class_id, enrollments in excluded.items():
                per_class[class_id]['excluded'] = len(enrollments)
        rows = self._fold(classes, group_by, per_class, lambda: {'calls': 0, 'present': 0, 'excluded': 0})
        for row in rows:
            row['pct'] = _pct(row['present'], row['calls'])
        calls = sum(r['calls'] for r in rows)
        return {
            'calls': calls,
            'pct': _pct(sum(r['present'] for r in rows), calls),
            'excluded': sum(r['excluded'] for r in rows),
            'rows': rows,
        }

    @api.model
    def _final_results(self, year, classes, group_by, enrolled):
        """Transitaram ou concluíram entre os decididos (os em exame de recurso ainda não têm resultado e contam à
        parte); a média só com os que a têm."""
        YearResult = self.env['edu.year.result']
        empty = {'evaluated': 0, 'decided': 0, 'approved': 0, 'exam': 0, 'retained': 0, 'sum': 0.0, 'with_avg': 0}
        per_class = defaultdict(lambda: dict(empty))
        base = [
            ('academic_year_id', '=', year.id),
            ('status', '!=', 'pending'),
            ('class_id', 'in', classes.ids),
            *COUNTED_DOMAIN,
        ]
        for edu_class, status, count in YearResult._read_group(base, ['class_id', 'status'], ['__count']):
            row = per_class[edu_class.id]
            row['evaluated'] += count
            if status in APPROVED:
                row['approved'] += count
                row['decided'] += count
            elif status == 'exam':
                row['exam'] += count
            else:
                row['retained'] += count
                row['decided'] += count
        for edu_class, count, average_sum in YearResult._read_group(
            [*base, ('average', '>', 0)], ['class_id'], ['__count', 'average:sum']
        ):
            per_class[edu_class.id]['sum'] += average_sum
            per_class[edu_class.id]['with_avg'] += count
        rows = self._fold(classes, group_by, per_class, lambda: dict(empty))
        for row in rows:
            row['pct'] = _pct(row['approved'], row['decided'])
            row['average'] = None if group_by == 'subsystem' else _avg(row['sum'], row['with_avg'])
            row.pop('sum')
            row.pop('with_avg')
        evaluated = sum(r['evaluated'] for r in rows)
        decided = sum(r['decided'] for r in rows)
        return {
            'evaluated': evaluated,
            'decided': decided,
            'approved': sum(r['approved'] for r in rows),
            'exam': sum(r['exam'] for r in rows),
            'pct': _pct(sum(r['approved'] for r in rows), decided),
            'enrolled': enrolled,
            'missing': enrolled - evaluated,
            'rows': rows,
        }

    @api.model
    def _subjects(self, year, classes, class_id):
        """Classificações por disciplina: só as completas (uma classificação por fechar não é um zero)."""
        class_id = class_id if class_id in classes.ids else False
        scope = [
            ('academic_year_id', '=', year.id),
            ('class_id', 'in', [class_id] if class_id else classes.ids),
            *COUNTED_DOMAIN,
        ]
        SubjectResult = self.env['edu.subject.result']
        complete = [*scope, ('complete', '=', True)]
        approved = dict(SubjectResult._read_group([*complete, ('passed', '=', True)], ['subject_id'], ['__count']))
        rows = []
        for subject, count, final_sum in SubjectResult._read_group(complete, ['subject_id'], ['__count', 'final:sum']):
            passed = approved.get(subject, 0)
            rows.append(
                {
                    'key': str(subject.id),
                    'label': subject.name,
                    'sub': subject.code or '',
                    'count': count,
                    'passed': passed,
                    'pct': _pct(passed, count),
                    'average': _avg(final_sum, count),
                }
            )
        # As piores primeiro: é onde a direcção olha.
        rows.sort(key=lambda r: (r['pct'] if r['pct'] is not None else 101, r['label']))
        count = sum(r['count'] for r in rows)
        return {
            'classes': [
                {'id': c.id, 'label': c._editor_label()}
                for c in classes.sorted(lambda c: (c.class_number, c.course_id.name or '', c.name))
            ],
            'class_id': class_id,
            'count': count,
            'pct': _pct(sum(r['passed'] for r in rows), count),
            'incomplete': SubjectResult.search_count([*scope, ('complete', '=', False)]),
            'rows': rows,
        }

    @api.model
    def report(self, year_id, group_by='subsystem', trimester_id=False, class_id=False):
        if not self.env.user.has_group('edu_core.group_edu_user'):
            raise AccessError(self.env._('Os relatórios da escola são da secretaria e da direcção.'))
        year = self.env['edu.academic.year'].browse(year_id).exists()
        if not year:
            raise UserError(self.env._('Escolha o ano lectivo.'))
        if group_by not in GROUPS:
            group_by = 'subsystem'
        # As turmas arquivadas também contam: os seus alunos estão nos totais do ano.
        classes = self.env['edu.class'].with_context(active_test=False).search([('academic_year_id', '=', year.id)])
        enrollments = self._enrollments(year, classes, group_by)
        return {
            'year': year.name,
            'group_by': group_by,
            'group_label': GROUPS[group_by],
            'enrollments': enrollments,
            'grades': self._trimester_grades(year, classes, group_by, trimester_id),
            'attendance': self._attendance(year, classes, group_by),
            'final': self._final_results(year, classes, group_by, enrollments['total']),
            'subjects': self._subjects(year, classes, class_id),
            'years_trend': self._years_trend(year.company_id),
        }

    # Exportar

    @api.model
    def _tables(self, data):
        """Os quadros como tabelas (título, colunas, linhas), para o Excel e o PDF."""
        group = data['group_label']
        grades, final, subjects = data['grades'], data['final'], data['subjects']

        def num(value):
            return '' if value is None else value

        return [
            (
                'Matrículas',
                [group, 'Alunos', '% dos alunos'],
                [[r['label'], r['total'], num(r['pct'])] for r in data['enrollments']['rows']],
            ),
            (
                f'Notas do {grades["trimester"] or "trimestre"}',
                [group, 'Notas', 'Positivas', '% positivas', 'Média', 'Alunos', 'Alunos com negativa'],
                [
                    [
                        r['label'],
                        r['grades'],
                        r['positive'],
                        num(r['pct']),
                        num(r['average']),
                        r['students'],
                        r['with_negative'],
                    ]
                    for r in grades['rows']
                ],
            ),
            (
                'Assiduidade',
                [group, 'Chamadas', '% presenças', 'Excluídos por faltas'],
                [[r['label'], r['calls'], num(r['pct']), r['excluded']] for r in data['attendance']['rows']],
            ),
            (
                'Resultado final',
                [group, 'Com resultado', 'Transitaram', '% dos decididos', 'Exame de recurso', 'Retidos', 'Média'],
                [
                    [
                        r['label'],
                        r['evaluated'],
                        r['approved'],
                        num(r['pct']),
                        r['exam'],
                        r['retained'],
                        num(r['average']),
                    ]
                    for r in final['rows']
                ],
            ),
            (
                'Classificações por disciplina'
                + (
                    ' ({})'.format(next(c['label'] for c in subjects['classes'] if c['id'] == subjects['class_id']))
                    if subjects['class_id']
                    else ''
                ),
                ['Disciplina', 'Classificações', 'Aprovados', '% aprovação', 'Média'],
                [[r['label'], r['count'], r['passed'], num(r['pct']), num(r['average'])] for r in subjects['rows']],
            ),
        ]

    @api.model
    def export_xlsx(self, year_id, group_by='subsystem', trimester_id=False, class_id=False):
        data = self.report(year_id, group_by, trimester_id, class_id)
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
        bold = workbook.add_format({'bold': True})
        for title, columns, rows in self._tables(data):
            sheet = workbook.add_worksheet(title[:31])
            sheet.write(0, 0, f'{title}, {data["year"]}, por {data["group_label"].lower()}', bold)
            sheet.write_row(2, 0, columns, bold)
            for index, row in enumerate(rows, start=3):
                sheet.write_row(index, 0, row)
            sheet.set_column(0, 0, 40)
            sheet.set_column(1, len(columns), 14)
        workbook.close()
        return {
            'name': f'Relatorios {data["year"].replace("/", "-")}.xlsx',
            'datas': base64.b64encode(stream.getvalue()).decode(),
        }

    @api.model
    def print_pdf(self, year_id, group_by='subsystem', trimester_id=False, class_id=False):
        """Só os parâmetros vão no pedido: os números calculam-se de novo ao imprimir, com o acesso de quem imprime."""
        self.report(year_id, group_by, trimester_id, class_id)
        return self.env.ref('edu_roles.action_report_school_figures').report_action(
            None,
            data={'year_id': year_id, 'group_by': group_by, 'trimester_id': trimester_id, 'class_id': class_id},
        )

    @api.model
    def _pdf_values(self, params):
        data = self.report(
            params.get('year_id'), params.get('group_by'), params.get('trimester_id'), params.get('class_id')
        )
        return {
            'year': data['year'],
            'group_label': data['group_label'],
            'tables': [{'title': t, 'columns': c, 'rows': r} for t, c, r in self._tables(data)],
            'printed': fields.Date.context_today(self).strftime('%d/%m/%Y'),
        }

    @api.model
    def analysis_action(self, kind, year_id, class_id=False):
        """A tabela dinâmica da «Análise detalhada», já no ano (e na turma) escolhidos."""
        xmlid = {
            'final': 'edu_roles.action_edu_year_result_analysis',
            'subjects': 'edu_roles.action_edu_subject_result_analysis',
        }[kind]
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        domain = [('academic_year_id', '=', year_id)]
        if class_id:
            domain.append(('class_id', '=', class_id))
        action['domain'] = domain
        return action


class ReportSchoolFigures(models.AbstractModel):
    _name = 'report.edu_roles.report_school_figures'
    _description = 'Relatórios da escola (PDF)'

    @api.model
    def _get_report_values(self, docids, data=None):
        return {**self.env['edu.report.page']._pdf_values(data or {}), 'company': self.env.company}
