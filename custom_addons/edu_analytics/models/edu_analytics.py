from collections import Counter, defaultdict

from odoo import api, models
from odoo.exceptions import AccessError

# O resultado de cada matrícula no ano, pela ordem das barras.
OUTCOMES = [
    ('promoted', 'Transitou'),
    ('graduated', 'Concluiu o curso'),
    ('conditional', 'Transitou com disciplinas em atraso'),
    ('retained', 'Reprovou'),
    ('dropped', 'Desistiu'),
    ('transferred', 'Transferido'),
    ('ongoing', 'Em curso'),
]
PASSED = ('promoted', 'graduated', 'conditional')
DECIDED = ('promoted', 'graduated', 'conditional', 'retained')
# No percurso, quem já não está: saiu num ano anterior (desistiu, foi transferido ou não renovou a matrícula).
COHORT = [*OUTCOMES, ('left', 'Já tinha saído')]
# As médias finais por faixas, na escala de 0 a 20 (arredondadas).
BANDS = [(0, 10, 'Menos de 10'), (10, 14, '10 a 13'), (14, 17, '14 a 16'), (17, 21, '17 a 20')]
TYPES = [('new', 'Novas'), ('renewal', 'Confirmações'), ('repeat', 'Repetentes'), ('transfer_in', 'Transferidos')]
SUBJECT_ROWS = 12
SUBJECT_MIN = 15
# As negativas da decisão do ano por grupos (no técnico contam também as disciplinas em atraso das classes anteriores).
NEGATIVES = [(0, 0, 'Nenhuma'), (1, 1, '1'), (2, 2, '2'), (3, 4, '3 ou 4'), (5, 999, '5 ou mais')]
# Quem sai da escola no fim ou a meio do ano.
EXITS = [('dropped', 'Desistiu'), ('transferred', 'Transferido'), ('not_renewed', 'Não renovou')]
# Os meses do ano lectivo, de Setembro a Agosto.
MONTHS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
MONTH_NAMES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
# As turmas pelo número de alunos, para comparar o tamanho com o resultado.
SIZES = [(0, 29, 'Até 29 alunos'), (30, 39, '30 a 39'), (40, 44, '40 a 44'), (45, 999, '45 ou mais')]
ARREARS_ROWS = 10


def _rate(part, total):
    return round(100 * part / total, 1) if total else None


def _mean(values):
    return round(sum(values) / len(values), 2) if values else None


def _bucket(value, buckets):
    return next(index for index, (low, high, _label) in enumerate(buckets) if low <= value <= high)


def _band(value):
    rounded = int(value + 0.5)
    return next(index for index, (low, high, _label) in enumerate(BANDS) if low <= rounded < high)


class EduAnalytics(models.AbstractModel):
    """«Análise de dados» da secretaria: os números da escola ao longo dos anos lectivos, para a direcção e a
    secretaria. Resumo (matrículas e resultado de cada ano), percurso dos alunos que entraram num ano (onde estão nos
    anos seguintes) e aproveitamento (os trimestres, as médias por faixas, as disciplinas com mais negativas, os cursos
    e as turmas). Cada número abre a lista dos alunos que conta."""

    _name = 'edu.analytics'
    _description = 'Análise de dados'

    def _check_access(self):
        if not self.env.user.has_group('edu_core.group_edu_user'):
            raise AccessError(self.env._('A análise de dados é da direcção e da secretaria.'))

    # Opções e filtros

    @api.model
    def options(self):
        self._check_access()
        company = self.env.company
        years = self.env['edu.academic.year'].search([('date_start', '!=', False)], order='date_start')
        Enrollment = self.env['edu.enrollment']
        counts = dict(Enrollment._read_group([('company_id', '=', company.id)], ['academic_year_id'], ['__count']))
        years = years.filtered(counts.get)
        numbers = sorted({n for (n,) in Enrollment._read_group([('company_id', '=', company.id)], ['class_number'])})
        return {
            'years': [{'id': y.id, 'name': y.name, 'current': y.is_current} for y in years],
            'courses': [
                {'id': c.id, 'name': c.name, 'code': c.code}
                for c in self.env['edu.course'].search([('company_id', 'in', [company.id, False])], order='name')
            ],
            'class_numbers': [{'id': n, 'name': self.env._('Iniciação') if n == 0 else f'{n}ª'} for n in numbers],
            'shifts': [{'id': s.id, 'name': s.name} for s in self.env['edu.shift'].search([])],
            'outcomes': [{'key': k, 'label': label} for k, label in OUTCOMES],
            'cohort_keys': [{'key': k, 'label': label} for k, label in COHORT],
            'bands': [{'index': i, 'label': label} for i, (_l, _h, label) in enumerate(BANDS)],
            'types': [{'key': k, 'label': label} for k, label in TYPES],
            'negatives': [{'index': i, 'label': label} for i, (_l, _h, label) in enumerate(NEGATIVES)],
            'exits': [{'key': k, 'label': label} for k, label in EXITS],
            'sizes': [{'index': i, 'label': label} for i, (_l, _h, label) in enumerate(SIZES)],
            'months': [{'id': m, 'name': MONTH_NAMES[m - 1]} for m in MONTHS],
        }

    def _domain(self, filters, with_years=True):
        domain = [('company_id', '=', self.env.company.id), ('state', '!=', 'draft')]
        if with_years and filters.get('year_ids'):
            domain.append(('academic_year_id', 'in', filters['year_ids']))
        if filters.get('course_id'):
            domain.append(('course_id', '=', filters['course_id']))
        if filters.get('class_number') not in (None, False, ''):
            domain.append(('class_number', '=', filters['class_number']))
        if filters.get('shift_id'):
            domain.append(('class_id.shift_id', '=', filters['shift_id']))
        return domain

    def _rows(self, enrollments):
        """Uma linha por matrícula com o resultado do ano e a média (na escala de 0 a 20)."""
        results = {
            r.enrollment_id.id: r
            for r in self.env['edu.year.result'].search([('enrollment_id', 'in', enrollments.ids)])
        }
        scales = {}

        def scale(level):
            if level not in scales:
                scales[level] = self.env['edu.evaluation.policy']._get(self.env.company, level).scale_max or 20
            return scales[level]

        rows = []
        for e in enrollments:
            result = results.get(e.id)
            status = result.status if result else False
            if e.state in ('dropped', 'transferred'):
                outcome = e.state
            elif status in ('promoted', 'graduated', 'conditional', 'retained'):
                outcome = status
            elif status == 'exam':
                outcome = 'conditional'
            else:
                outcome = 'ongoing'
            average = None
            if result and status in DECIDED and result.average:
                average = result.average * 20 / scale(result.level_id or e.class_id.level_id)
            decided = bool(result) and status in DECIDED
            rows.append(
                {
                    'id': e.id,
                    'student': e.student_id.id,
                    'year': e.academic_year_id.id,
                    'class': e.class_id.id,
                    'class_number': e.class_number,
                    'course': e.course_id.id,
                    'type': e.enrollment_type,
                    'outcome': outcome,
                    'average': average,
                    'negatives': result.negative_count if decided else None,
                    'arrears': result.negative_subject_ids.ids if decided and outcome == 'conditional' else [],
                    'manual': decided and bool(result.manual),
                    'decision_reason': result.reason if decided and result.manual else False,
                    'result': result.id if result else False,
                    'reason': e.drop_reason_code if e.state == 'dropped' else False,
                    'requested': e.drop_requested_by if e.state == 'dropped' else False,
                    'justified': e.drop_justified if e.state == 'dropped' else False,
                    'month': e.drop_date.month if e.state in ('dropped', 'transferred') and e.drop_date else False,
                }
            )
        return rows

    # O painel

    @api.model
    def dashboard(self, filters):
        self._check_access()
        enrollments = self.env['edu.enrollment'].search(self._domain(filters))
        rows = self._rows(enrollments)
        years = enrollments.academic_year_id.sorted('date_start')
        summary = self._summary(rows, years, enrollments)
        return {
            'years': [{'id': y.id, 'name': y.name, 'current': y.is_current} for y in years],
            'summary': summary,
            'highlights': self._highlights(summary, rows, years),
            'cohort': self._cohort(filters),
            'performance': self._performance(filters, rows, years, enrollments),
            'decisions': self._decisions(filters, rows, years),
            'exits': self._exits(rows, years),
            'capacity': self._capacity(filters, rows, years),
        }

    def _summary(self, rows, years, enrollments):
        classes = defaultdict(set)
        for e in enrollments:
            classes[e.academic_year_id.id].add(e.class_id)
        out = []
        for year in years:
            mine = [r for r in rows if r['year'] == year.id]
            outcomes = Counter(r['outcome'] for r in mine)
            types = Counter(r['type'] for r in mine)
            decided = sum(outcomes[k] for k in DECIDED)
            year_classes = classes[year.id]
            out.append(
                {
                    'year_id': year.id,
                    'year': year.name,
                    'current': year.is_current,
                    'enrolled': len(mine),
                    'types': {k: types[k] for k, _l in TYPES},
                    'outcomes': {k: outcomes[k] for k, _l in OUTCOMES},
                    'decided': decided,
                    'transition': _rate(sum(outcomes[k] for k in PASSED), decided),
                    'conditional': _rate(outcomes['conditional'], decided),
                    'retention': _rate(outcomes['retained'], decided),
                    'dropout': _rate(outcomes['dropped'], len(mine)),
                    'transferred': outcomes['transferred'],
                    'average': _mean([r['average'] for r in mine if r['average'] is not None]),
                    'classes': len(year_classes),
                    'capacity': sum(c.capacity for c in year_classes),
                }
            )
        return out

    def _highlights(self, summary, rows, years):
        """Frases curtas com o que mudou entre os dois últimos anos fechados e o que mais pesa no último."""
        notes = []
        closed = [s for s in summary if s['decided']]
        if summary:
            last = summary[-1]
            if len(summary) >= 2 and summary[-2]['enrolled']:
                before = summary[-2]
                change = _rate(last['enrolled'] - before['enrolled'], before['enrolled'])
                if change:
                    notes.append(
                        {
                            'tone': 'info',
                            'icon': 'north' if change > 0 else 'south',
                            'text': self.env._(
                                '%(year)s tem %(n)s matrículas, %(change)s%% face a %(before)s.',
                                year=last['year'],
                                n=f'{last["enrolled"]:,}'.replace(',', '\u00a0'),
                                change=f'{change:+.0f}'.replace('.', ','),
                                before=before['year'],
                            ),
                        }
                    )
        if len(closed) >= 2:
            last, before = closed[-1], closed[-2]
            for key, label, worse_up in (
                ('transition', self.env._('A taxa de transição'), False),
                ('retention', self.env._('A reprovação'), True),
                ('dropout', self.env._('A desistência'), True),
            ):
                if last[key] is None or before[key] is None:
                    continue
                delta = round(last[key] - before[key], 1)
                if abs(delta) < 1:
                    continue
                worse = (delta > 0) == worse_up
                notes.append(
                    {
                        'tone': 'bad' if worse else 'good',
                        'icon': 'north' if delta > 0 else 'south',
                        'text': self.env._(
                            '%(label)s %(verb)s %(delta)s pontos em %(year)s '
                            '(%(now)s%%, contra %(then)s%% em %(before)s).',
                            label=label,
                            verb=self.env._('subiu') if delta > 0 else self.env._('desceu'),
                            delta=f'{abs(delta):.1f}'.replace('.', ','),
                            year=last['year'],
                            now=f'{last[key]:.1f}'.replace('.', ','),
                            then=f'{before[key]:.1f}'.replace('.', ','),
                            before=before['year'],
                        ),
                    }
                )
        if closed and closed[-1]['outcomes']['conditional']:
            last = closed[-1]
            notes.append(
                {
                    'tone': 'warn',
                    'icon': 'warning',
                    'text': self.env._(
                        'Em %(year)s, %(n)s alunos transitaram com disciplinas em atraso (%(rate)s%% dos avaliados).',
                        year=last['year'],
                        n=last['outcomes']['conditional'],
                        rate=f'{last["conditional"]:.1f}'.replace('.', ','),
                    ),
                }
            )
        return notes

    # Percurso dos alunos

    def _cohort_steps(self, filters):
        """Os alunos que entraram num ano (nova matrícula ou transferência de outra escola) e, ano a ano, onde estão:
        o resultado desse ano, ou já fora (saíram antes, ou não renovaram a matrícula), ou já concluíram."""
        company = self.env.company
        Enrollment = self.env['edu.enrollment']
        all_years = self.env['edu.academic.year'].search([('date_start', '!=', False)], order='date_start')
        entry_years = Enrollment.search(
            [*self._domain(filters, with_years=False), ('enrollment_type', 'in', ('new', 'transfer_in'))]
        ).academic_year_id.sorted('date_start')
        if not entry_years:
            return None, all_years.browse(), []
        entry = entry_years.filtered(lambda y: y.id == filters.get('cohort_year_id')) or entry_years[0]
        entrants = Enrollment.search(
            [
                *self._domain(filters, with_years=False),
                ('academic_year_id', '=', entry.id),
                ('enrollment_type', 'in', ('new', 'transfer_in')),
            ]
        )
        students = set(entrants.student_id.ids)
        later = all_years.filtered(lambda y: y.date_start >= entry.date_start)
        history = Enrollment.search(
            [
                ('company_id', '=', company.id),
                ('state', '!=', 'draft'),
                ('student_id', 'in', list(students)),
                ('academic_year_id', 'in', later.ids),
            ]
        )
        by_student_year = {(r['student'], r['year']): r for r in self._rows(history)}
        classes = {e.id: e.class_number for e in history}
        steps = []
        gone, graduated = set(), set()
        previous = None
        for year in later:
            groups = defaultdict(set)
            numbers = Counter()
            for student in students:
                row = by_student_year.get((student, year.id))
                if row:
                    # Também quem saiu e voltou a matricular-se mais tarde.
                    gone.discard(student)
                    groups[row['outcome']].add(student)
                    numbers[classes[row['id']]] += 1
                    continue
                if student in graduated:
                    groups['graduated'].add(student)
                elif previous is not None and student not in gone:
                    # Estava no ano anterior e não renovou a matrícula.
                    gone.add(student)
                    groups['left'].add(student)
                else:
                    groups['left'].add(student)
            if not any(groups[k] for k, _l in OUTCOMES if k != 'graduated'):
                break
            steps.append({'year': year, 'groups': groups, 'numbers': numbers})
            gone |= groups['dropped'] | groups['transferred']
            graduated |= groups['graduated']
            previous = year
        return entry, entry_years, steps

    def _cohort(self, filters):
        entry, entry_years, steps = self._cohort_steps(filters)
        if not entry:
            return None
        size = sum(len(g) for g in steps[0]['groups'].values()) if steps else 0
        last = steps[-1]['groups'] if steps else {}
        present = sum(len(last.get(k, ())) for k in ('promoted', 'conditional', 'retained', 'ongoing'))
        ever_retained = set().union(*(s['groups'].get('retained', set()) for s in steps)) if steps else set()
        return {
            'entry_year_id': entry.id,
            'entry_year': entry.name,
            'entry_years': [{'id': y.id, 'name': y.name} for y in entry_years],
            'size': size,
            'kpis': {
                'present': present,
                'graduated': len(last.get('graduated', ())),
                'left': len(last.get('left', ())) + len(last.get('dropped', ())) + len(last.get('transferred', ())),
                'ever_retained': len(ever_retained),
            },
            'steps': [
                {
                    'year_id': s['year'].id,
                    'year': s['year'].name,
                    'classes': ', '.join(
                        (self.env._('Iniciação') if n == 0 else f'{n}ª') for n, _c in sorted(s['numbers'].items())
                    ),
                    'segments': {k: len(s['groups'].get(k, ())) for k, _l in COHORT},
                }
                for s in steps
            ],
        }

    # Aproveitamento

    def _performance(self, filters, rows, years, enrollments):
        return {
            'trimesters': self._trimesters(enrollments, years),
            'bands': self._bands(rows, years),
            'subjects': self._subjects(enrollments, years),
            'courses': self._courses(rows, years),
            'classes': self._classes(filters, rows, years),
        }

    def _trimesters(self, enrollments, years):
        """A média das notas de cada trimestre (MT), por ano: o percurso T1, T2, T3 de cada ano lado a lado."""
        if not enrollments:
            return []
        self.env.cr.execute(
            """
            SELECT e.academic_year_id, c.level_id, t.trimester_number, AVG(t.mt), COUNT(*)
              FROM edu_term_result t
              JOIN edu_enrollment e ON e.id = t.enrollment_id
              JOIN edu_class c ON c.id = e.class_id
             WHERE t.enrollment_id IN %s AND t.has_mt
             GROUP BY 1, 2, 3
            """,
            [tuple(enrollments.ids)],
        )
        sums = defaultdict(lambda: [0.0, 0])
        Level = self.env['edu.level']
        for year_id, level_id, number, average, count in self.env.cr.fetchall():
            scale = self.env['edu.evaluation.policy']._get(self.env.company, Level.browse(level_id)).scale_max or 20
            cell = sums[(year_id, number)]
            cell[0] += float(average) * 20 / scale * count
            cell[1] += count
        out = []
        for year in years:
            values = [
                round(sums[(year.id, n)][0] / sums[(year.id, n)][1], 2) if sums[(year.id, n)][1] else None
                for n in (1, 2, 3)
            ]
            if any(v is not None for v in values):
                out.append({'year_id': year.id, 'year': year.name, 'values': values})
        return out

    def _bands(self, rows, years):
        out = []
        for year in years:
            averages = [r['average'] for r in rows if r['year'] == year.id and r['average'] is not None]
            if averages:
                counts = Counter(_band(a) for a in averages)
                out.append(
                    {
                        'year_id': year.id,
                        'year': year.name,
                        'total': len(averages),
                        'counts': [counts[i] for i in range(len(BANDS))],
                    }
                )
        return out

    def _subjects(self, enrollments, years):
        """As disciplinas com mais negativas (classificações fechadas sem aprovação), por ano: as que mais
        reprovam no conjunto dos anos primeiro."""
        if not enrollments:
            return {'rows': [], 'years': []}
        self.env.cr.execute(
            """
            SELECT s.subject_id, e.academic_year_id, COUNT(*), COUNT(*) FILTER (WHERE NOT s.passed)
              FROM edu_subject_result s
              JOIN edu_enrollment e ON e.id = s.enrollment_id
             WHERE s.enrollment_id IN %s AND s.complete
             GROUP BY 1, 2
            """,
            [tuple(enrollments.ids)],
        )
        cells = defaultdict(dict)
        for subject_id, year_id, total, failed in self.env.cr.fetchall():
            cells[subject_id][year_id] = (total, failed)
        ranked = []
        for subject_id, by_year in cells.items():
            total = sum(t for t, _f in by_year.values())
            failed = sum(f for _t, f in by_year.values())
            if total >= SUBJECT_MIN and failed:
                ranked.append((failed / total, total, failed, subject_id))
        ranked.sort(reverse=True)
        subjects = self.env['edu.subject'].browse([r[3] for r in ranked[:SUBJECT_ROWS]])
        names = {s.id: s.name for s in subjects}
        with_data = [y for y in years if any(y.id in cells[r[3]] for r in ranked[:SUBJECT_ROWS])]
        return {
            'years': [{'id': y.id, 'name': y.name} for y in with_data],
            'rows': [
                {
                    'subject_id': subject_id,
                    'subject': names[subject_id],
                    'rate': round(100 * rate, 1),
                    'failed': failed,
                    'total': total,
                    'cells': [
                        {
                            'year_id': y.id,
                            'total': cells[subject_id].get(y.id, (0, 0))[0],
                            'failed': cells[subject_id].get(y.id, (0, 0))[1],
                            'rate': _rate(
                                cells[subject_id].get(y.id, (0, 0))[1], cells[subject_id].get(y.id, (0, 0))[0]
                            ),
                        }
                        for y in with_data
                    ],
                }
                for rate, total, failed, subject_id in ranked[:SUBJECT_ROWS]
            ],
        }

    def _courses(self, rows, years):
        courses = self.env['edu.course'].browse(sorted({r['course'] for r in rows if r['course']}))
        out = []
        for course in courses.sorted('name'):
            cells = []
            for year in years:
                mine = [r for r in rows if r['year'] == year.id and r['course'] == course.id]
                outcomes = Counter(r['outcome'] for r in mine)
                decided = sum(outcomes[k] for k in DECIDED)
                cells.append(
                    {
                        'year_id': year.id,
                        'enrolled': len(mine),
                        'transition': _rate(sum(outcomes[k] for k in PASSED), decided),
                        'average': _mean([r['average'] for r in mine if r['average'] is not None]),
                    }
                )
            out.append({'course_id': course.id, 'course': course.name, 'code': course.code, 'cells': cells})
        return out

    def _classes(self, filters, rows, years):
        """As turmas de um ano (o último com resultados, se não se escolher outro): alunos, média e transição."""
        decided_years = [y for y in years if any(r['year'] == y.id and r['outcome'] in DECIDED for r in rows)]
        if not decided_years:
            return None
        year = next((y for y in decided_years if y.id == filters.get('class_year_id')), decided_years[-1])
        by_class = defaultdict(list)
        for r in rows:
            if r['year'] == year.id:
                by_class[r['class']].append(r)
        classes = self.env['edu.class'].browse(list(by_class))
        out = []
        for edu_class in classes.sorted(lambda c: (c.class_number, c.course_id.code or '', c.name)):
            mine = by_class[edu_class.id]
            outcomes = Counter(r['outcome'] for r in mine)
            decided = sum(outcomes[k] for k in DECIDED)
            out.append(
                {
                    'class_id': edu_class.id,
                    'name': edu_class._editor_label(),
                    'students': len(mine),
                    'average': _mean([r['average'] for r in mine if r['average'] is not None]),
                    'transition': _rate(sum(outcomes[k] for k in PASSED), decided),
                    'retained': outcomes['retained'],
                    'dropped': outcomes['dropped'],
                }
            )
        return {
            'year_id': year.id,
            'year': year.name,
            'years': [{'id': y.id, 'name': y.name} for y in decided_years],
            'rows': out,
        }

    # Decisões e disciplinas em atraso

    def _decisions(self, filters, rows, years):
        """As negativas da decisão de cada ano, as disciplinas que mais ficam em atraso, as decisões tomadas à mão
        (pela direcção ou vindas das pautas assinadas) e os exames especiais."""
        closed = [y for y in years if any(r['year'] == y.id and r['negatives'] is not None for r in rows)]
        if not closed:
            return None
        per_year = []
        for year in closed:
            mine = [r for r in rows if r['year'] == year.id and r['negatives'] is not None]
            buckets = Counter(_bucket(r['negatives'], NEGATIVES) for r in mine)
            manual = [r for r in mine if r['manual']]
            per_year.append(
                {
                    'year_id': year.id,
                    'year': year.name,
                    'decided': len(mine),
                    'negatives': [buckets[i] for i in range(len(NEGATIVES))],
                    'manual': len(manual),
                    'manual_outcomes': {k: sum(1 for r in manual if r['outcome'] == k) for k in DECIDED},
                    'passed_with_many': sum(
                        1 for r in mine if r['outcome'] in ('promoted', 'graduated') and r['negatives'] >= 3
                    ),
                }
            )
        year = next((y for y in closed if y.id == filters.get('detail_year_id')), closed[-1])
        conditional = [r for r in rows if r['year'] == year.id and r['outcome'] == 'conditional']
        arrears = Counter(subject for r in conditional for subject in r['arrears'])
        subjects = self.env['edu.subject'].browse([s for s, _n in arrears.most_common(ARREARS_ROWS)])
        names = {s.id: s.name for s in subjects}
        manual = [r for r in rows if r['year'] == year.id and r['manual']]
        return {
            'years': per_year,
            'manual_reasons': [
                {'reason': reason or self.env._('Sem fundamento registado'), 'count': n}
                for reason, n in Counter(r['decision_reason'] for r in manual).most_common(3)
            ],
            'detail_year_id': year.id,
            'detail_year': year.name,
            'detail_years': [{'id': y.id, 'name': y.name} for y in closed],
            'conditional': len(conditional),
            'arrears': [
                {'subject_id': s, 'subject': names[s], 'count': n, 'share': _rate(n, len(conditional))}
                for s, n in arrears.most_common(ARREARS_ROWS)
            ],
            'exams': self._exams(rows, closed),
        }

    def _exams(self, rows, years):
        """Os exames especiais (recurso, disciplina em atraso, melhoria) pedidos pela decisão de cada ano."""
        results = [r['result'] for r in rows if r['result']]
        if not results:
            return []
        Requirement = self.env['edu.exam.requirement']
        kinds = dict(Requirement._fields['kind']._description_selection(self.env))
        groups = Requirement._read_group(
            [('year_result_id', 'in', results)],
            ['year_result_id', 'kind', 'state', 'passed'],
            ['__count'],
        )
        cells = defaultdict(lambda: {'pending': 0, 'done': 0, 'passed': 0})
        year_of = {r['result']: r['year'] for r in rows if r['result']}
        for result, kind, state, passed, count in groups:
            cell = cells[(year_of[result.id], kind)]
            cell[state] += count
            if state == 'done' and passed:
                cell['passed'] += count
        return [
            {
                'year_id': y.id,
                'year': y.name,
                'kind': kind,
                'label': kinds[kind].split(' (')[0],
                **cells[(y.id, kind)],
            }
            for y in years
            for kind in kinds
            if (y.id, kind) in cells
        ]

    # Saídas

    def _not_renewed(self, rows, years):
        """As matrículas de quem acabou o ano e não voltou a matricular-se no ano seguinte (quando já existe): sem
        contar quem concluiu o curso nem quem transitou da última classe do plano."""
        all_years = self.env['edu.academic.year'].search([('date_start', '!=', False)], order='date_start')
        following = {a.id: b.id for a, b in zip(all_years, all_years[1:], strict=False)}
        self.env.cr.execute(
            'SELECT DISTINCT student_id, academic_year_id FROM edu_enrollment WHERE company_id = %s AND state != %s',
            [self.env.company.id, 'draft'],
        )
        enrolled = set(self.env.cr.fetchall())
        classes = self.env['edu.class'].browse({r['class'] for r in rows})
        last_class = {}
        for edu_class in classes:
            numbers = edu_class.curriculum_id.year_ids.mapped('class_number')
            last_class[edu_class.id] = bool(numbers) and edu_class.class_number == max(numbers)
        out = defaultdict(set)
        for r in rows:
            nxt = following.get(r['year'])
            if not nxt or r['outcome'] not in ('promoted', 'conditional', 'retained'):
                continue
            if r['outcome'] != 'retained' and last_class.get(r['class']):
                continue
            if (r['student'], nxt) not in enrolled:
                out[r['year']].add(r['id'])
        return out, following

    def _exits(self, rows, years):
        not_renewed, following = self._not_renewed(rows, years)
        per_year = []
        for year in years:
            mine = [r for r in rows if r['year'] == year.id]
            outcomes = Counter(r['outcome'] for r in mine)
            gone = len(not_renewed[year.id]) if following.get(year.id) and not year.is_current else None
            per_year.append(
                {
                    'year_id': year.id,
                    'year': year.name,
                    'current': year.is_current,
                    'enrolled': len(mine),
                    'counts': {
                        'dropped': outcomes['dropped'],
                        'transferred': outcomes['transferred'],
                        'not_renewed': gone,
                    },
                    'not_renewed_retained': sum(
                        1 for r in mine if r['id'] in not_renewed[year.id] and r['outcome'] == 'retained'
                    ),
                    'rate': _rate(outcomes['dropped'] + outcomes['transferred'] + (gone or 0), len(mine)),
                }
            )
        numbers = sorted({r['class_number'] for r in rows})
        by_class = []
        for number in numbers:
            cells = []
            for year in years:
                mine = [r for r in rows if r['year'] == year.id and r['class_number'] == number]
                gone = sum(1 for r in mine if r['id'] in not_renewed[year.id])
                cells.append(
                    {
                        'year_id': year.id,
                        'enrolled': len(mine),
                        'out': sum(1 for r in mine if r['outcome'] in ('dropped', 'transferred')) + gone,
                    }
                )
            by_class.append({'class_number': number, 'name': f'{number}ª' if number else 'Iniciação', 'cells': cells})
        dropped = [r for r in rows if r['outcome'] == 'dropped']
        Enrollment = self.env['edu.enrollment']
        reasons = dict(Enrollment._fields['drop_reason_code']._description_selection(self.env))
        requesters = dict(Enrollment._fields['drop_requested_by']._description_selection(self.env))
        reason_counts = Counter(r['reason'] or 'none' for r in dropped)
        moved = [r for r in rows if r['month']]
        months = Counter(r['month'] for r in moved)
        top = max(months.values()) if months else 0
        return {
            'years': per_year,
            'by_class': by_class,
            'dropped': len(dropped),
            'reasons': [
                {'key': k, 'label': reasons.get(k, self.env._('Sem motivo registado')), 'count': n}
                for k, n in reason_counts.most_common()
            ],
            'requesters': [
                {'label': requesters.get(k, self.env._('Não registado')), 'count': n}
                for k, n in Counter(r['requested'] or 'none' for r in dropped).most_common()
            ],
            'justified': sum(1 for r in dropped if r['justified']),
            'months': [{'month': m, 'count': months[m]} for m in MONTHS],
            # Quase todas no mesmo mês: datas postas pela migração, não as da saída.
            'one_month': len(moved) >= 10 and top >= 0.9 * len(moved),
        }

    # Turmas e capacidade

    def _capacity(self, filters, rows, years):
        domain = [('company_id', '=', self.env.company.id), ('academic_year_id', 'in', years.ids)]
        if filters.get('course_id'):
            domain.append(('course_id', '=', filters['course_id']))
        if filters.get('class_number') not in (None, False, ''):
            domain.append(('class_number', '=', filters['class_number']))
        if filters.get('shift_id'):
            domain.append(('shift_id', '=', filters['shift_id']))
        classes = self.env['edu.class'].search(domain)
        if not classes:
            return None
        by_class = defaultdict(list)
        for r in rows:
            by_class[r['class']].append(r)

        def stats(edu_class):
            mine = by_class.get(edu_class.id, [])
            students = sum(1 for r in mine if r['outcome'] not in ('dropped', 'transferred'))
            outcomes = Counter(r['outcome'] for r in mine)
            decided = sum(outcomes[k] for k in DECIDED)
            return {
                'class_id': edu_class.id,
                'name': edu_class._editor_label(),
                'shift': edu_class.shift_id.name or '',
                'students': students,
                'capacity': edu_class.capacity,
                'occupancy': _rate(students, edu_class.capacity),
                'transition': _rate(sum(outcomes[k] for k in PASSED), decided),
                'passed': sum(outcomes[k] for k in PASSED),
                'decided': decided,
                'average': _mean([r['average'] for r in mine if r['average'] is not None]),
                'averages': [r['average'] for r in mine if r['average'] is not None],
            }

        per_class = {c.id: stats(c) for c in classes}
        per_year = []
        for year in years:
            mine = [per_class[c.id] for c in classes if c.academic_year_id == year]
            shifts = defaultdict(lambda: [0, 0, 0])
            for c in mine:
                cell = shifts[c['shift'] or self.env._('Sem turno')]
                cell[0] += 1
                cell[1] += c['students']
                cell[2] += c['capacity']
            students, capacity = sum(c['students'] for c in mine), sum(c['capacity'] for c in mine)
            per_year.append(
                {
                    'year_id': year.id,
                    'year': year.name,
                    'classes': len(mine),
                    'students': students,
                    'capacity': capacity,
                    'occupancy': _rate(students, capacity),
                    'over': sum(1 for c in mine if c['capacity'] and c['students'] > c['capacity']),
                    'low': sum(1 for c in mine if c['capacity'] and c['students'] < c['capacity'] / 2),
                    'shifts': [
                        {'name': name, 'classes': n, 'students': st, 'occupancy': _rate(st, cap)}
                        for name, (n, st, cap) in sorted(shifts.items())
                    ],
                }
            )
        year = next((y for y in years if y.id == filters.get('capacity_year_id')), years[-1])
        listed = sorted(
            (per_class[c.id] for c in classes if c.academic_year_id == year),
            key=lambda c: (-(c['occupancy'] or 0), c['name']),
        )
        sizes = defaultdict(lambda: {'classes': 0, 'passed': 0, 'decided': 0, 'averages': []})
        for c in per_class.values():
            if c['decided']:
                cell = sizes[_bucket(c['students'], SIZES)]
                cell['classes'] += 1
                cell['passed'] += c['passed']
                cell['decided'] += c['decided']
                cell['averages'] += c['averages']
        for c in per_class.values():
            c.pop('averages')
        return {
            'years': per_year,
            'year_id': year.id,
            'year': year.name,
            'classes': listed,
            'sizes': [
                {
                    'index': i,
                    'classes': sizes[i]['classes'],
                    'transition': _rate(sizes[i]['passed'], sizes[i]['decided']),
                    'average': _mean(sizes[i]['averages']),
                }
                for i in range(len(SIZES))
                if sizes[i]['classes']
            ],
        }

    # Os alunos de cada número

    @api.model
    def students(self, filters, kind, params):
        """A lista dos alunos que um número conta: um segmento, uma faixa, uma disciplina ou uma turma."""
        self._check_access()
        params = params or {}
        ids, title = set(), self.env._('Alunos')
        year = self.env['edu.academic.year'].browse(params.get('year_id') or [])
        if kind == 'cohort':
            entry, _entry_years, steps = self._cohort_steps(filters)
            step = next((s for s in steps if s['year'].id == params.get('year_id')), None)
            if step:
                ids = step['groups'].get(params.get('key'), set())
                title = self.env._(
                    'Entraram em %(entry)s · %(year)s: %(what)s',
                    entry=entry.name,
                    year=step['year'].name,
                    what=dict(COHORT)[params['key']].lower(),
                )
        elif kind == 'subject':
            subject = self.env['edu.subject'].browse(params['subject_id'])
            domain = [('subject_id', '=', subject.id), ('complete', '=', True), ('passed', '=', False)]
            enrollments = self.env['edu.enrollment'].search(
                self._domain({**filters, 'year_ids': year.ids or filters.get('year_ids')})
            )
            results = self.env['edu.subject.result'].search([*domain, ('enrollment_id', 'in', enrollments.ids)])
            ids = set(results.student_id.ids)
            title = self.env._('Negativa a %(subject)s · %(year)s', subject=subject.name, year=year.name or '')
        else:
            year_ids = year.ids or filters.get('year_ids')
            enrollments = self.env['edu.enrollment'].search(self._domain({**filters, 'year_ids': year_ids}))
            if kind == 'class':
                enrollments = enrollments.filtered(lambda e: e.class_id.id == params['class_id'])
                title = self.env._('Turma %s', enrollments.class_id[:1]._editor_label() if enrollments else '')
            rows = self._rows(enrollments)
            if kind == 'exit' and params.get('key') == 'not_renewed':
                not_renewed, _following = self._not_renewed(rows, enrollments.academic_year_id)
                wanted = set().union(*not_renewed.values()) if not_renewed else set()
                rows = [r for r in rows if r['id'] in wanted]
                title = f'{year.name} · {dict(EXITS)["not_renewed"]}'
            elif kind == 'exit':
                rows = [r for r in rows if r['outcome'] == params['key']]
                title = f'{year.name} · {dict(EXITS)[params["key"]]}'
            elif kind == 'negatives':
                rows = [
                    r
                    for r in rows
                    if r['negatives'] is not None and _bucket(r['negatives'], NEGATIVES) == params['index']
                ]
                title = self.env._('%(year)s · negativas: %(n)s', year=year.name, n=NEGATIVES[params['index']][2])
            elif kind == 'arrears':
                subject = self.env['edu.subject'].browse(params['subject_id'])
                rows = [r for r in rows if r['outcome'] == 'conditional' and subject.id in r['arrears']]
                title = self.env._('%(year)s · em atraso a %(subject)s', year=year.name, subject=subject.name)
            elif kind == 'manual':
                rows = [r for r in rows if r['manual'] and params.get('key') in (None, r['outcome'])]
                title = self.env._('%s · decisões tomadas à mão', year.name)
            elif kind == 'exam':
                requirements = self.env['edu.exam.requirement'].search(
                    [
                        ('year_result_id', 'in', [r['result'] for r in rows if r['result']]),
                        ('kind', '=', params['kind']),
                        ('state', '=', params['state']),
                    ]
                )
                wanted = set(requirements.student_id.ids)
                rows = [r for r in rows if r['student'] in wanted]
                title = self.env._('%s · exames especiais', year.name)
            elif kind == 'reason':
                rows = [r for r in rows if r['outcome'] == 'dropped' and (r['reason'] or 'none') == params['key']]
                title = self.env._('Desistências por motivo')
            elif kind == 'month':
                rows = [r for r in rows if r['month'] == params['month']]
                title = self.env._('Saídas em %s', MONTH_NAMES[params['month'] - 1])
            elif kind == 'outcome':
                rows = [r for r in rows if r['outcome'] == params['key']]
                title = f'{year.name} · {dict(OUTCOMES)[params["key"]]}'
            elif kind == 'type':
                rows = [r for r in rows if r['type'] == params['key']]
                title = f'{year.name} · {dict(TYPES)[params["key"]]}'
            elif kind == 'band':
                rows = [r for r in rows if r['average'] is not None and _band(r['average']) == params['band']]
                title = self.env._('%(year)s · média final: %(band)s', year=year.name, band=BANDS[params['band']][2])
            elif kind == 'year':
                title = self.env._('Matrículas de %s', year.name)
            ids = {r['student'] for r in rows}
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'edu.student',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', sorted(ids))],
            'context': {'create': False, 'active_test': False},
        }
