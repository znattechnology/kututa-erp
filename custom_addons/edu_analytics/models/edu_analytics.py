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


def _rate(part, total):
    return round(100 * part / total, 1) if total else None


def _mean(values):
    return round(sum(values) / len(values), 2) if values else None


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
            rows.append(
                {
                    'id': e.id,
                    'student': e.student_id.id,
                    'year': e.academic_year_id.id,
                    'class': e.class_id.id,
                    'course': e.course_id.id,
                    'type': e.enrollment_type,
                    'outcome': outcome,
                    'average': average,
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
            if kind == 'outcome':
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
