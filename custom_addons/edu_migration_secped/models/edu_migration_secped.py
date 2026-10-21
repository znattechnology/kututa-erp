"""Migração de uma escola do secPed-Express para a Secretaria Express.

Cada fase lê as tabelas do secPed, constrói os valores do Odoo e cria ou actualiza os registos. A identidade de cada
registo importado fica em ``ir.model.data`` (módulo ``__secped__``, nome ``<tabela>_<id do secPed>``), o que torna a
migração idempotente: correr de novo actualiza em vez de duplicar. Os dados derivados (médias, notas, resultados)
usam a chave natural do Odoo (matrícula, disciplina, trimestre).
"""

import logging
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

XID_MODULE = '__secped__'
PHASES = (
    'school',
    'calendar',
    'curriculum',
    'classes',
    'people',
    'enrollments',
    'teaching',
    'grades',
    'decisions',
    'exams',
    'fees',
)
IMPORT_CONTEXT = {
    'tracking_disable': True,
    'mail_create_nolog': True,
    'mail_create_nosubscribe': True,
    'mail_notrack': True,
    'edu_no_materialize': True,
    'edu_matricula_import': True,
    'edu_schedule_import': True,
    'edu_enrollment_reseed': True,
    'edu_defer_results': True,
}
SCHOOL_TYPES = {'GERAL': 'general', 'TECNICO_PROFISSIONAL': 'technical', 'MAGISTERIO': 'teacher_training'}
OWNERSHIPS = {
    'PUBLICA': 'public',
    'PRIVADA': 'private',
    'PUBLICO_PRIVADA': 'public_private',
    'COMUNITARIA': 'community',
    'RELIGIOSA': 'religious',
}
BILLING_MODES = {'MONTHLY_TUITION': 'monthly', 'FEE_FREE': 'fee_free', 'SUBSIDIZED': 'subsidized'}
SHIFT_TYPES = {'MORNING': 'morning', 'AFTERNOON': 'afternoon', 'EVENING': 'evening', 'FULL_DAY': 'full_day'}
COMPONENTS = {
    'SOCIO_CULTURAL': 'socio_cultural',
    'CIENTIFICA': 'scientific',
    'TECNICA_PRATICA': 'technical',
    'ESTAGIO': 'internship',
}
COORDINATION_TYPES = {'CURSO': 'course', 'DISCIPLINA': 'subject'}
ENROLLMENT_STATES = {'ACTIVE': 'active', 'DROPPED': 'dropped', 'TRANSFERRED': 'transferred', 'PENDING': 'draft'}
FEE_CATEGORIES = {
    'MATRICULA': 'enrollment',
    'PROPINA': 'tuition',
    'EXAME': 'exam',
    'SERVICO': 'service',
    'CARTAO': 'card',
}
RECURRENCES = {'ONE_OFF': 'one_off', 'MONTHLY': 'monthly', 'QUARTERLY': 'quarterly', 'ANNUAL': 'annual'}
# Decisão assinada (secPed) → decisões do Odoo que lhe correspondem.
SIGNED_MATCHES = {
    'PROMOTED': ('promoted', 'graduated', 'conditional'),
    'RETAINED': ('retained',),
    'PENDING': ('pending',),
}
SIGNED_REASON = 'Decisão da pauta assinada (migração do secPed-Express)'


def round_half_up(value):
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def secped_final(cf, pg, points, scale_max=20):
    """Classificação do ano como o secPed a calcula: CA = 60% CF + 40% PG com a CF e a PG por arredondar e um
    único arredondamento; sem PG, CA = CF; mais a bonificação do conselho, com tecto na escala."""
    if cf is None:
        return None
    ca = round_half_up(0.6 * cf + 0.4 * pg) if pg is not None else round_half_up(cf)
    return min(scale_max, ca + (points or 0))


def full_name(user):
    return re.sub(r'\s+', ' ', f'{user.get("firstName") or ""} {user.get("lastName") or ""}').strip()


def to_date(value):
    return value.date() if hasattr(value, 'date') and callable(value.date) else value


def minutes(value):
    return (value or 0) / 60.0


def number(value):
    return float(value) if value is not None else None


class MigrationRun:
    """Estado de uma passagem: fonte, empresa, mapa secPed → Odoo, contagens e avisos."""

    def __init__(self, env, source, company):
        self.env = env
        self.src = source
        self.company = company
        self.counts = defaultdict(lambda: {'created': 0, 'updated': 0})
        self.issues = []
        self.metrics = {}
        self.ids = defaultdict(dict)  # tabela → {id do secPed: id do Odoo}
        for row in env['ir.model.data'].search_read([('module', '=', XID_MODULE)], ['name', 'model', 'res_id']):
            table, _sep, sid = row['name'].rpartition('__')
            self.ids[table][sid] = row['res_id']
        users = source.rows('users')
        self.test_users = {u['id'] for u in users if (u.get('email') or '').lower().endswith('.test')}
        self.users = {u['id']: u for u in users if u['id'] not in self.test_users}

    def issue(self, kind, detail):
        self.issues.append((kind, detail))

    def ref(self, table, sid):
        return self.ids[table].get(sid) if sid else None

    def upsert(self, table, model, items):
        """Cria ou actualiza: ``items`` são pares (id do secPed, valores). Devolve {id do secPed: id do Odoo}."""
        Model = self.env[model]
        mapped = self.ids[table]
        existing = Model.browse([mapped[sid] for sid, _vals in items if sid in mapped]).exists()
        alive = set(existing.ids)
        to_create = []
        for sid, vals in items:
            res_id = mapped.get(sid)
            if res_id in alive:
                if vals:
                    Model.browse(res_id).write(vals)
                self.counts[table]['updated'] += 1
            else:
                to_create.append((sid, vals))
        if to_create:
            records = Model.create([vals for _sid, vals in to_create])
            data = self.env['ir.model.data']
            stale = data.search(
                [('module', '=', XID_MODULE), ('name', 'in', [f'{table}__{sid}' for sid, _v in to_create])]
            )
            stale.unlink()
            data.create(
                [
                    {
                        'module': XID_MODULE,
                        'name': f'{table}__{sid}',
                        'model': model,
                        'res_id': record.id,
                        'noupdate': True,
                    }
                    for (sid, _vals), record in zip(to_create, records, strict=True)
                ]
            )
            for (sid, _vals), record in zip(to_create, records, strict=True):
                mapped[sid] = record.id
            self.counts[table]['created'] += len(records)
        return {sid: mapped[sid] for sid, _vals in items}

    def report(self):
        return {
            'counts': dict(self.counts),
            'issues': list(self.issues),
            'metrics': dict(self.metrics),
            'mismatches': list(getattr(self, 'mismatches', [])),
        }


class EduMigrationSecped(models.AbstractModel):
    _name = 'edu.migration.secped'
    _description = 'Migração do secPed-Express'

    @api.model
    def _run(self, source, company=None, phases=PHASES, commit=None):
        """Corre as fases pedidas e a reconciliação. ``commit`` (opcional) é chamado no fim de cada fase."""
        company = company or self.env.company
        env = self.env(su=True, context=dict(self.env.context, **IMPORT_CONTEXT, allowed_company_ids=[company.id]))
        run = MigrationRun(env, source, company.with_env(env))
        Migration = env[self._name]
        for phase in PHASES:
            if phase not in phases:
                continue
            _logger.info('secPed: fase %s', phase)
            getattr(Migration, f'_phase_{phase}')(run)
            env.flush_all()
            if commit:
                commit()
        Migration._verify(run)
        return run.report()

    # ------------------------------------------------------------------
    # 1. Escola
    # ------------------------------------------------------------------
    def _phase_school(self, run):
        school = run.src.school
        country = self.env.ref('base.ao')
        state = self.env['res.country.state'].search(
            [('country_id', '=', country.id), ('name', '=ilike', school.get('province') or '')], limit=1
        )
        vals = {
            'name': school['name'],
            'email': school.get('email') or False,
            'phone': school.get('phone') or False,
            'website': school.get('website') or False,
            'street': school.get('street') or school.get('neighborhood') or school.get('address') or False,
            'street2': school.get('neighborhood') if school.get('street') else False,
            'city': school.get('municipality') or False,
            'state_id': state.id or False,
            'country_id': country.id,
            'edu_is_school': True,
            'edu_school_type': SCHOOL_TYPES.get(school.get('type'), 'general'),
            'edu_ownership': OWNERSHIPS.get(school.get('schoolOwnership')) or False,
            'edu_billing_mode': BILLING_MODES.get(school.get('billingMode'), 'monthly'),
            'edu_institution_code': school.get('institutionCode') or False,
            'edu_mined_code': school.get('minedCode') or False,
            'edu_license_number': school.get('licenseNumber') or False,
            'edu_established_year': school.get('establishedYear') or 0,
            'edu_letterhead_subtitle': school.get('letterheadSubtitle') or False,
            'edu_director_name': school.get('directorName') or False,
            'edu_pedagogical_director_name': school.get('pedagogicalDirectorName') or False,
            'edu_student_capacity': school.get('studentCapacity') or 0,
        }
        run.company.write(vals)
        if school.get('taxNumber') and run.company.vat != school['taxNumber']:
            try:
                with self.env.cr.savepoint():
                    run.company.vat = school['taxNumber']
            except Exception as error:  # noqa: BLE001 (NIF recusado pela validação: fica no relatório)
                run.issue('escola', f'NIF {school["taxNumber"]} recusado: {error}')
        if school.get('logoUrl'):
            run.issue('escola', 'O logótipo está no armazenamento do secPed e não foi descarregado.')
        run.counts['schools']['updated'] += 1

    # ------------------------------------------------------------------
    # 2. Calendário e instalações
    # ------------------------------------------------------------------
    def _phase_calendar(self, run):
        src = run.src
        cid = run.company.id
        years = src.rows('academic_years')
        run.upsert(
            'academic_years',
            'edu.academic.year',
            [
                (
                    y['id'],
                    {
                        'name': y['name'],
                        'company_id': cid,
                        'date_start': to_date(y['startDate']),
                        'date_end': to_date(y['endDate']),
                    },
                )
                for y in years
            ],
        )
        trimesters = src.rows('trimesters')
        run.upsert(
            'trimesters',
            'edu.trimester',
            [
                (
                    t['id'],
                    {
                        'academic_year_id': run.ref('academic_years', t['academicYearId']),
                        'company_id': cid,
                        'name': t['name'],
                        'number': t['number'],
                        'date_start': to_date(t['startDate']),
                        'date_end': to_date(t['endDate']),
                        'state': 'closed' if t.get('closedAt') else 'open',
                        'closed_date': t.get('closedAt') or False,
                    },
                )
                for t in trimesters
                if run.ref('academic_years', t['academicYearId'])
            ],
        )
        # O ano e o trimestre em curso marcam-se no fim: marcar um desmarca os outros.
        for y in years:
            if y.get('current'):
                self.env['edu.academic.year'].browse(run.ref('academic_years', y['id'])).is_current = True
        for t in trimesters:
            if t.get('current') and run.ref('trimesters', t['id']):
                self.env['edu.trimester'].browse(run.ref('trimesters', t['id'])).is_current = True

        run.upsert(
            'departments',
            'edu.coordination',
            [
                (
                    d['id'],
                    {
                        'name': d['name'],
                        'code': d.get('code') or False,
                        'company_id': cid,
                        'coordination_type': COORDINATION_TYPES.get(d.get('type')) or False,
                    },
                )
                for d in src.rows('departments')
            ],
        )
        run.upsert(
            'school_shifts',
            'edu.shift',
            [
                (
                    s['id'],
                    {
                        'name': s['name'],
                        'company_id': cid,
                        'shift_type': SHIFT_TYPES.get(s.get('type'), 'morning'),
                        'hour_from': minutes(s['startTime']),
                        'hour_to': minutes(s['endTime']),
                        'active': s.get('isActive', True),
                    },
                )
                for s in src.rows('school_shifts')
            ],
        )
        # Tempos lectivos: o Odoo não aceita tempos sobrepostos no mesmo turno (há duas grelhas de tarde no secPed).
        # Fica a primeira grelha; as aulas guardam as suas horas mesmo sem tempo associado.
        slots = []
        taken = defaultdict(list)
        known = {
            (slot.shift_id.id, slot.hour_from, slot.hour_to): slot
            for slot in self.env['edu.time.slot'].search([('company_id', '=', cid)])
        }
        for slot in sorted(src.rows('time_slots'), key=lambda s: (s['shiftId'], s.get('orderIndex') or 0)):
            shift_id = run.ref('school_shifts', slot['shiftId'])
            start, end = minutes(slot['startTime']), minutes(slot['endTime'])
            if not shift_id:
                continue
            overlap = any(start < other_end and end > other_start for other_start, other_end in taken[shift_id])
            if overlap and (shift_id, start, end) not in known:
                run.issue('tempos', f'{slot["name"]}: sobrepõe-se a outro tempo do turno e ficou de fora')
                continue
            taken[shift_id].append((start, end))
            slots.append(
                (
                    slot['id'],
                    {
                        'name': slot['name'],
                        'shift_id': shift_id,
                        'company_id': cid,
                        'hour_from': start,
                        'hour_to': end,
                        'is_break': bool(slot.get('isBreak')),
                    },
                )
            )
        run.upsert('time_slots', 'edu.time.slot', slots)
        room_types = dict(self.env['edu.room']._fields['room_type'].selection)
        run.upsert(
            'rooms',
            'edu.room',
            [
                (
                    r['id'],
                    {
                        'name': r['name'],
                        'code': r.get('code') or False,
                        'company_id': cid,
                        'room_type': (r.get('type') or '').lower()
                        if (r.get('type') or '').lower() in room_types
                        else 'classroom',
                        'capacity': r.get('capacity') or 0,
                        'floor': r.get('floor') or 0,
                        'has_projector': bool(r.get('hasProjector')),
                        'has_ac': bool(r.get('hasAC')),
                        'note': r.get('notes') or False,
                    },
                )
                for r in src.rows('rooms')
            ],
        )

    # ------------------------------------------------------------------
    # 3. Disciplinas, cursos e planos
    # ------------------------------------------------------------------
    def _level(self, code):
        return self.env['edu.level'].search([('code', '=', code)], limit=1)

    def _phase_curriculum(self, run):
        src = run.src
        cid = run.company.id
        run.upsert(
            'subjects',
            'edu.subject',
            [
                (
                    s['id'],
                    {
                        'name': s['name'],
                        'code': s.get('code') or False,
                        'company_id': cid,
                        'component': COMPONENTS.get(s.get('component')) or False,
                        'duration_years': s.get('durationYears') or 1,
                        'start_year': s.get('startYear') or 1,
                        'is_national_exam': bool(s.get('isNationalExamSubject')),
                        'coordination_id': run.ref('departments', s.get('departmentId')) or False,
                    },
                )
                for s in src.rows('subjects')
            ],
        )
        courses = []
        for c in src.rows('courses'):
            level = self._level(c.get('level'))
            if not level:
                run.issue('cursos', f'{c["name"]}: nível {c.get("level")} sem correspondência')
                continue
            courses.append(
                (
                    c['id'],
                    {
                        'name': c['name'],
                        'code': c.get('code') or False,
                        'company_id': cid,
                        'level_id': level.id,
                        'coordination_id': run.ref('departments', c.get('departmentId')) or False,
                        'duration_years': c.get('duration') or 0,
                        'description': c.get('description') or False,
                        'requires_internship': bool(c.get('requiresInternship')),
                        'requires_final_project': bool(c.get('requiresFinalProject')),
                        'has_national_exam': bool(c.get('hasNationalExam')),
                        'has_special_exam': bool(c.get('hasSpecialExam')),
                    },
                )
            )
        run.upsert('courses', 'edu.course', courses)
        curricula = []
        for k in src.rows('curricula'):
            level = self._level(k.get('level'))
            if not level:
                run.issue('planos', f'{k["name"]}: nível {k.get("level")} sem correspondência')
                continue
            curricula.append(
                (
                    k['id'],
                    {
                        'name': k['name'],
                        'company_id': cid,
                        'course_id': run.ref('courses', k.get('courseId')) or False,
                        'level_id': level.id,
                        'description': k.get('description') or False,
                        'is_national': bool(k.get('isNational')),
                        'active': bool(k.get('isActive', True)),
                    },
                )
            )
        run.upsert('curricula', 'edu.curriculum', curricula)
        run.upsert(
            'curriculum_years',
            'edu.curriculum.year',
            [
                (
                    y['id'],
                    {
                        'curriculum_id': run.ref('curricula', y['curriculumId']),
                        'year': y['year'],
                        'class_number': y['classNumber'],
                        'name': y.get('name') or False,
                    },
                )
                for y in src.rows('curriculum_years')
                if run.ref('curricula', y['curriculumId'])
            ],
        )
        lines = []
        for sequence, line in enumerate(src.rows('curriculum_subjects')):
            year_id = run.ref('curriculum_years', line['curriculumYearId'])
            subject_id = run.ref('subjects', line['subjectId'])
            if not year_id or not subject_id:
                continue
            lines.append(
                (
                    line['id'],
                    {
                        'year_id': year_id,
                        'subject_id': subject_id,
                        'sequence': sequence,
                        'weekly_hours': line.get('weeklyHours') or 0,
                        'component': COMPONENTS.get(line.get('component')) or False,
                        'is_compulsory': bool(line.get('isCompulsory', True)),
                        'is_national_exam': bool(line.get('isNationalExam')),
                    },
                )
            )
        run.upsert('curriculum_subjects', 'edu.curriculum.line', lines)
        self._setup_policy(run)

    def _setup_policy(self, run):
        """Regime de avaliação da escola com os valores do secPed e o arredondamento único na CA."""
        rules = {r.get('level'): r for r in run.src.rows('promotion_rules')}
        for policy_row in run.src.rows('evaluation_policies'):
            level = self._level(policy_row.get('level'))
            if not level or policy_row.get('isActive') is False:
                continue
            policy = self.env['edu.evaluation.policy']._get(run.company, level)
            vals = {
                'pass_grade': number(policy_row.get('minPassGrade')) or policy.pass_grade,
                'min_attendance': number(policy_row.get('minAttendanceRate')) or policy.min_attendance,
                'max_retentions': policy_row.get('maxRetentions') or policy.max_retentions,
                'rounding': 'decimal2' if policy_row.get('roundingMode') == 'DECIMAL' else 'integer',
            }
            if policy.regime == 'technical':
                vals['technical_ca_precise'] = True
            rule = rules.get(policy_row.get('level'))
            if rule and rule.get('maxNegatives') is not None:
                vals['conditional_max'] = rule['maxNegatives']
            policy.write(vals)

    # ------------------------------------------------------------------
    # 4. Turmas: uma por oferta anual
    # ------------------------------------------------------------------
    def _phase_classes(self, run):
        src = run.src
        classes = {c['id']: c for c in src.rows('school_classes')}
        used = {(e['classId'], e['academicYearId']) for e in src.rows('enrollments')}
        curricula = defaultdict(list)
        for k in src.rows('curricula'):
            if k.get('courseId') and run.ref('curricula', k['id']):
                curricula[k['courseId']].append(k)
        years = self.env['edu.curriculum.year']
        rooms_taken = set()
        items = []
        for offering in src.rows('class_offerings'):
            school_class = classes.get(offering['classId'])
            year_id = run.ref('academic_years', offering['academicYearId'])
            if not school_class or not year_id:
                continue
            if not offering.get('isActive') and (offering['classId'], offering['academicYearId']) not in used:
                continue
            course_id = run.ref('courses', school_class['courseId'])
            if not course_id:
                run.issue('turmas', f'{school_class["name"]}: curso por importar')
                continue
            plans = sorted(curricula.get(school_class['courseId'], []), key=lambda k: not k.get('isActive', True))
            curriculum_id = run.ref('curricula', plans[0]['id']) if plans else False
            curriculum_year = years.search(
                [('curriculum_id', '=', curriculum_id), ('class_number', '=', school_class['classNumber'])], limit=1
            )
            letter = re.sub(r'^\s*\d+\s*[ªº.]?\s*', '', school_class['name']).strip() or school_class['name']
            shift_id = run.ref('school_shifts', school_class.get('shiftId')) or False
            room_id = run.ref('rooms', school_class.get('roomId')) or False
            if room_id and shift_id:
                key = (room_id, shift_id, year_id)
                if key in rooms_taken:
                    run.issue(
                        'turmas', f'{school_class["name"]}: sala já usada por outra turma no turno; ficou sem sala'
                    )
                    room_id = False
                rooms_taken.add(key)
            items.append(
                (
                    offering['id'],
                    {
                        'name': letter,
                        'company_id': run.company.id,
                        'academic_year_id': year_id,
                        'course_id': course_id,
                        'curriculum_id': curriculum_id,
                        'curriculum_year_id': curriculum_year.id or False,
                        'class_number': school_class['classNumber'],
                        'capacity': offering.get('capacity') or school_class.get('capacity') or 0,
                        'shift_id': shift_id,
                        'room_id': room_id,
                    },
                )
            )
            if not curriculum_year:
                run.issue('turmas', f'{school_class["name"]}: o plano não tem a {school_class["classNumber"]}ª classe')
        run.upsert('class_offerings', 'edu.class', items)

    def _class_for(self, run, class_id, year_id):
        """Turma do Odoo para (turma persistente, ano lectivo) do secPed."""
        if not hasattr(run, 'offerings'):
            run.offerings = {(o['classId'], o['academicYearId']): o['id'] for o in run.src.rows('class_offerings')}
        offering = run.offerings.get((class_id, year_id))
        return run.ref('class_offerings', offering) if offering else None

    # ------------------------------------------------------------------
    # 5. Pessoas: alunos, professores, direcção e encarregados
    # ------------------------------------------------------------------
    def _phase_people(self, run):
        src = run.src
        cid = run.company.id
        country = self.env.ref('base.ao')
        states = {s.name.lower(): s.id for s in self.env['res.country.state'].search([('country_id', '=', country.id)])}
        students = []
        for profile in src.rows('student_profiles'):
            user = run.users.get(profile['userId'])
            if not user:
                continue
            gender = {'M': 'male', 'F': 'female'}.get((profile.get('gender') or '').upper()[:1], False)
            students.append(
                (
                    profile['userId'],
                    {
                        'name': full_name(user),
                        'company_id': cid,
                        'birth_date': to_date(profile.get('dateOfBirth')) or False,
                        'gender': gender,
                        'id_number': profile.get('idNumber') or False,
                        'id_issuer': profile.get('idIssuer') or False,
                        'id_issue_date': to_date(profile.get('idIssueDate')) or False,
                        'birthplace': profile.get('naturality') or False,
                        'birth_state_id': states.get((profile.get('province') or '').lower(), False),
                        'father_name': profile.get('fatherName') or False,
                        'mother_name': profile.get('motherName') or False,
                        'street': profile.get('address') or False,
                        'phone': user.get('phone') or False,
                        'matricula_number': profile.get('matriculaNumber') or False,
                        'matricula_year': profile.get('matriculaYear') or 0,
                        'matricula_seq': profile.get('matriculaSeq') or 0,
                        'enrollment_date': to_date(profile.get('enrolledAt')) or False,
                    },
                )
            )
        run.upsert('students', 'edu.student', students)
        self.env['edu.student']._sync_matricula_sequence(run.company)

        teachers = []
        for profile in src.rows('teacher_profiles'):
            user = run.users.get(profile['userId'])
            if not user:
                continue
            teachers.append(
                (
                    profile['userId'],
                    {
                        'name': full_name(user),
                        'company_id': cid,
                        'edu_is_teacher': True,
                        'edu_specialization': profile.get('specialization') or False,
                        'edu_coordination_id': run.ref('departments', profile.get('departmentId')) or False,
                        'job_title': self.env._('Professor(a)'),
                        'mobile_phone': user.get('phone') or False,
                    },
                )
            )
        run.upsert('teachers', 'hr.employee', teachers)

        # Direcção: as contas de pessoas (não as de serviço, como secretaria@ ou financas@).
        school = src.school
        titles = {
            (school.get('directorName') or '').lower(): self.env._('Director(a) geral'),
            (school.get('pedagogicalDirectorName') or '').lower(): self.env._('Subdirector(a) pedagógico(a)'),
        }
        staff = [
            (
                user['id'],
                {'name': full_name(user), 'company_id': cid, 'job_title': titles[full_name(user).lower()]},
            )
            for user in run.users.values()
            if user.get('role') == 'SCHOOL_ADMIN' and full_name(user).lower() in titles and full_name(user)
        ]
        run.upsert('staff', 'hr.employee', staff)
        for department in src.rows('departments'):
            head = run.ref('teachers', department.get('headId')) or run.ref('staff', department.get('headId'))
            if head and run.ref('departments', department['id']):
                self.env['edu.coordination'].browse(run.ref('departments', department['id'])).head_id = head

        guardians = []
        for guardian in src.rows('guardians'):
            if guardian.get('userId') in run.test_users:
                continue
            guardians.append(
                (
                    guardian['id'],
                    {
                        'partner_id': self._guardian_partner(run, guardian).id,
                        'company_id': cid,
                        'id_number': guardian.get('idNumber') or False,
                        'occupation': guardian.get('occupation') or False,
                    },
                )
            )
        run.upsert('guardians', 'edu.guardian', guardians)
        links = []
        for link in src.rows('student_guardians'):
            student_id = run.ref('students', link['studentId'])
            guardian_id = run.ref('guardians', link['guardianId'])
            if not student_id or not guardian_id:
                continue
            links.append(
                (
                    link['id'],
                    {
                        'student_id': student_id,
                        'guardian_id': guardian_id,
                        'relationship': (link.get('relationship') or 'other').lower(),
                        'is_primary': bool(link.get('isPrimary')),
                        'is_emergency': bool(link.get('isEmergency')),
                        'can_pickup': bool(link.get('canPickup')),
                        'can_access_portal': bool(link.get('canAccessPortal')),
                        'receive_notifications': bool(link.get('receiveNotifications')),
                    },
                )
            )
        run.upsert('student_guardians', 'edu.student.guardian', links)
        excluded = len(run.test_users)
        if excluded:
            run.issue('pessoas', f'{excluded} contas de teste do secPed (endereços .test) ficaram de fora')

    def _guardian_partner(self, run, guardian):
        Partner = self.env['res.partner']
        guardian_id = run.ref('guardians', guardian['id'])
        if guardian_id:
            partner = self.env['edu.guardian'].browse(guardian_id).partner_id
        else:
            partner = Partner.create({'name': full_name(guardian), 'company_id': run.company.id})
        partner.write(
            {
                'name': full_name(guardian),
                'email': guardian.get('email') or False,
                'phone': guardian.get('phone') or False,
                'vat': guardian.get('taxNumber') or False,
                'street': guardian.get('address') or False,
            }
        )
        return partner

    # ------------------------------------------------------------------
    # 6. Matrículas
    # ------------------------------------------------------------------
    def _phase_enrollments(self, run):
        src = run.src
        subjects = defaultdict(list)
        for row in src.rows('enrollment_subjects'):
            subject_id = run.ref('subjects', row['subjectId'])
            if subject_id:
                subjects[row['enrollmentId']].append(subject_id)
        Class = self.env['edu.class']
        enrollments = [
            e for e in src.rows('enrollments') if e['userId'] in run.users and run.ref('students', e['userId'])
        ]
        years = {y['id']: y for y in src.rows('academic_years')}
        enrollments.sort(key=lambda e: (e['userId'], years[e['academicYearId']]['startDate'], e['createdAt']))
        previous = {}  # aluno → classe da matrícula anterior
        orders = set()
        by_year = defaultdict(list)
        for enrollment in enrollments:
            class_id = self._class_for(run, enrollment['classId'], enrollment['academicYearId'])
            if not class_id:
                run.issue('matrículas', f'Matrícula {enrollment["id"]}: turma sem oferta no ano')
                continue
            edu_class = Class.browse(class_id)
            before = previous.get(enrollment['userId'])
            kind = 'new' if before is None else ('repeat' if before == edu_class.class_number else 'renewal')
            previous[enrollment['userId']] = edu_class.class_number
            order = enrollment.get('orderNumber') or 0
            if order and (class_id, order) in orders:
                run.issue('matrículas', f'{edu_class.display_name}: n.º {order} repetido; ficou sem número')
                order = 0
            orders.add((class_id, order))
            state = ENROLLMENT_STATES.get(enrollment['status'], 'active')
            start = years[enrollment['academicYearId']]['startDate']
            vals = {
                'student_id': run.ref('students', enrollment['userId']),
                'class_id': class_id,
                'date': to_date(start),
                'state': state,
                'enrollment_type': kind,
                'order_number': order,
                'subject_ids': [fields.Command.set(subjects.get(enrollment['id'], []))],
                'drop_date': to_date(enrollment.get('droppedAt')) or False,
                'drop_reason': enrollment.get('transferNotes') or False,
            }
            if state in ('dropped', 'transferred') and not vals['drop_date']:
                vals['drop_date'] = to_date(enrollment.get('updatedAt')) or vals['date']
            # O estado de um ano fechado (concluída, retido) vem da decisão; uma nova passagem não o reabre.
            existing = run.ref('enrollments', enrollment['id'])
            if existing and state == 'active':
                current = self.env['edu.enrollment'].browse(existing).state
                if current in ('completed', 'retained'):
                    vals['state'] = current
            by_year[start].append((enrollment['id'], vals, enrollment['userId']))
        # Um ano de cada vez, por ordem, para ligar cada matrícula à anterior do mesmo aluno.
        last = {}
        for start in sorted(by_year):
            batch = []
            for sid, vals, user_id in by_year[start]:
                vals['previous_enrollment_id'] = last.get(user_id, False)
                batch.append((sid, vals))
            mapped = run.upsert('enrollments', 'edu.enrollment', batch)
            for sid, _vals, user_id in by_year[start]:
                last[user_id] = mapped[sid]

    # ------------------------------------------------------------------
    # 7. Docência: atribuições e horário
    # ------------------------------------------------------------------
    def _phase_teaching(self, run):
        src = run.src
        trimesters = {t['id']: t for t in src.rows('trimesters')}
        grouped = defaultdict(dict)
        for row in src.rows('subject_teachers'):
            trimester = trimesters.get(row.get('trimesterId'))
            year_id = trimester['academicYearId'] if trimester else self._current_year(run)
            class_id = self._class_for(run, row['classId'], year_id)
            teacher_id = run.ref('teachers', row['teacherId'])
            subject_id = run.ref('subjects', row['subjectId'])
            if not class_id or not teacher_id or not subject_id:
                if row['teacherId'] not in run.test_users:
                    run.issue('atribuições', f'Atribuição {row["id"]}: turma, professor ou disciplina em falta')
                continue
            if not self._in_plan(run, class_id, subject_id, 'atribuições'):
                continue
            grouped[(class_id, subject_id)][row.get('trimesterId')] = (row['id'], teacher_id)
        items = []
        for (class_id, subject_id), by_trimester in grouped.items():
            teachers = {teacher for _sid, teacher in by_trimester.values()}
            if len(teachers) == 1:
                # O mesmo professor em todos os trimestres: uma atribuição do ano inteiro.
                sid = min(sid for sid, _t in by_trimester.values())
                items.append(
                    (
                        sid,
                        {
                            'class_id': class_id,
                            'subject_id': subject_id,
                            'teacher_id': teachers.pop(),
                            'trimester_id': False,
                        },
                    )
                )
                continue
            for trimester_sid, (sid, teacher_id) in by_trimester.items():
                items.append(
                    (
                        sid,
                        {
                            'class_id': class_id,
                            'subject_id': subject_id,
                            'teacher_id': teacher_id,
                            'trimester_id': run.ref('trimesters', trimester_sid) or False,
                        },
                    )
                )
        run.upsert('subject_teachers', 'edu.teaching.assignment', items)
        for director in src.rows('class_directors'):
            class_id = self._class_for(run, director['classId'], director['academicYearId'])
            teacher_id = run.ref('teachers', director['teacherId'])
            if class_id and teacher_id:
                self.env['edu.class'].browse(class_id).director_id = teacher_id

        slots = {
            (slot.shift_id.id, slot.hour_from): slot.id
            for slot in self.env['edu.time.slot'].search(
                [('company_id', '=', run.company.id), ('is_break', '=', False)]
            )
        }
        Class = self.env['edu.class']
        current_year = self._current_year(run)
        schedules = []
        busy = defaultdict(list)
        for row in src.rows('schedules'):
            trimester = trimesters.get(row.get('trimesterId'))
            year_id = trimester['academicYearId'] if trimester else current_year
            class_id = self._class_for(run, row['classId'], year_id)
            subject_id = run.ref('subjects', row['subjectId'])
            if not class_id or not subject_id:
                run.issue('horário', f'Aula {row["id"]}: turma ou disciplina em falta')
                continue
            if not self._in_plan(run, class_id, subject_id, 'horário'):
                continue
            edu_class = Class.browse(class_id)
            hour_from, hour_to = minutes(row['startTime']), minutes(row['endTime'])
            weekday = str((row['dayOfWeek'] - 1) % 7)
            teacher_id = run.ref('teachers', row.get('teacherId')) or False
            if teacher_id:
                for other_from, other_to, other_class in busy[(teacher_id, weekday)]:
                    if hour_from < other_to and hour_to > other_from:
                        run.issue(
                            'horário',
                            f'Choque de professor: {self.env["hr.employee"].browse(teacher_id).name}, '
                            f'dia {int(weekday) + 2}.ª às {int(hour_from)}:{round(hour_from % 1 * 60):02d} '
                            f'({other_class} e {edu_class.display_name})',
                        )
                busy[(teacher_id, weekday)].append((hour_from, hour_to, edu_class.display_name))
            schedules.append(
                (
                    row['id'],
                    {
                        'class_id': class_id,
                        'subject_id': subject_id,
                        'teacher_id': teacher_id,
                        'room_id': run.ref('rooms', row.get('roomId')) or False,
                        'trimester_id': run.ref('trimesters', row.get('trimesterId')) or False,
                        'weekday': weekday,
                        'time_slot_id': slots.get((edu_class.shift_id.id, hour_from), False),
                        'hour_from': hour_from,
                        'hour_to': hour_to,
                    },
                )
            )
        run.upsert('schedules', 'edu.schedule', schedules)

    def _in_plan(self, run, class_id, subject_id, kind):
        """A disciplina está no plano da turma? O secPed aceita atribuições e aulas fora do plano; o Odoo não."""
        if not hasattr(run, 'plan_subjects'):
            run.plan_subjects = {}
            run.outside_plan = set()
        if class_id not in run.plan_subjects:
            edu_class = self.env['edu.class'].browse(class_id)
            run.plan_subjects[class_id] = set(edu_class.subject_line_ids.subject_id.ids)
        if subject_id in run.plan_subjects[class_id]:
            return True
        if (kind, class_id, subject_id) not in run.outside_plan:
            run.outside_plan.add((kind, class_id, subject_id))
            edu_class = self.env['edu.class'].browse(class_id)
            subject = self.env['edu.subject'].browse(subject_id)
            run.issue(kind, f'{subject.name} na {edu_class.display_name}: fora do plano da turma, ficou de fora')
        return False

    def _current_year(self, run):
        current = [y['id'] for y in run.src.rows('academic_years') if y.get('current')]
        return current[0] if current else None

    # ------------------------------------------------------------------
    # 8. Notas dos anos fechados
    # ------------------------------------------------------------------
    def _phase_grades(self, run):
        src = run.src
        env = self.env
        enrollments = {e['id']: e for e in src.rows('enrollments')}
        terms, annual, global_exam = {}, {}, {}
        for grade in src.rows('grades'):
            enrollment_id = run.ref('enrollments', grade.get('enrollmentId'))
            subject_id = run.ref('subjects', grade['subjectId'])
            if not enrollment_id or not subject_id or grade.get('score') is None:
                continue
            pair = (enrollment_id, subject_id)
            if grade['type'] == 'TRIMESTRAL':
                trimester_id = run.ref('trimesters', grade.get('trimesterId'))
                if trimester_id:
                    terms[(*pair, trimester_id)] = float(grade['score'])
            elif grade['type'] == 'ANUAL':
                annual[pair] = float(grade['score'])
            elif grade['type'] == 'GLOBAL':
                global_exam[pair] = float(grade['score'])
            else:
                run.issue('notas', f'Tipo de nota {grade["type"]} sem correspondência')
        by_student_year = {
            (e['userId'], e['academicYearId']): run.ref('enrollments', e['id'])
            for e in enrollments.values()
            if e['status'] == 'ACTIVE' and run.ref('enrollments', e['id'])
        }
        points = {}
        for adjustment in src.rows('grade_council_adjustments'):
            enrollment_id = by_student_year.get((adjustment['studentId'], adjustment['academicYearId']))
            subject_id = run.ref('subjects', adjustment['subjectId'])
            if enrollment_id and subject_id:
                source = 'teacher' if adjustment.get('source') == 'TEACHER' else 'council'
                points[(enrollment_id, subject_id)] = (adjustment['points'], source)
        run.metrics['notas_trimestrais'] = len(terms)
        run.metrics['cf_assinadas'] = len(annual)
        run.metrics['provas_globais'] = len(global_exam)
        run.metrics['bonificacoes'] = len(points)

        # a) Médias trimestrais (CT1, CT2 e a CF no 3.º trimestre), importadas: não se recalculam das notas.
        Term = env['edu.term.result']
        existing = {
            (t.enrollment_id.id, t.subject_id.id, t.trimester_id.id): t
            for t in Term.search([('enrollment_id', 'in', list({k[0] for k in terms}))])
        }
        new_terms = []
        for key, score in terms.items():
            vals = {'mt': score, 'has_mt': True, 'imported': True}
            if key in existing:
                existing[key].write(vals)
            else:
                new_terms.append({'enrollment_id': key[0], 'subject_id': key[1], 'trimester_id': key[2], **vals})
        Term.create(new_terms)
        run.counts['term_results']['created'] += len(new_terms)
        run.counts['term_results']['updated'] += len(terms) - len(new_terms)

        # b) Resultado anual com a CF assinada e a bonificação do conselho.
        Result = env['edu.subject.result']
        pairs = set(annual) | set(global_exam) | set(points) | {key[:2] for key in terms}
        results = {
            (r.enrollment_id.id, r.subject_id.id): r
            for r in Result.search([('enrollment_id', 'in', list({p[0] for p in pairs}))])
        }
        new_results = []
        for pair in pairs:
            point, source = points.get(pair, (0, False))
            vals = {
                'has_imported_cf': pair in annual,
                'imported_cf': annual.get(pair, 0.0),
                'council_points': point,
                'council_source': source,
            }
            if pair in results:
                results[pair].write(vals)
            else:
                new_results.append({'enrollment_id': pair[0], 'subject_id': pair[1], **vals})
        for result in Result.create(new_results):
            results[(result.enrollment_id.id, result.subject_id.id)] = result
        run.counts['subject_results']['created'] += len(new_results)
        run.counts['subject_results']['updated'] += len(pairs) - len(new_results)

        # c) A escola faz prova global em disciplinas que a regra do plano não prevê: o plano fica como a escola o
        #    pratica, senão a PG lançada não entrava na CA (no secPed, uma PG lançada conta sempre).
        Enrollment = env['edu.enrollment']
        lines_marked = env['edu.curriculum.line']
        by_class = defaultdict(dict)
        for (enrollment_id, subject_id), score in global_exam.items():
            enrollment = Enrollment.browse(enrollment_id)
            line = enrollment.class_id.subject_line_ids.filtered(lambda line, s=subject_id: line.subject_id.id == s)[:1]
            if not line:
                run.issue('notas', f'PG de {enrollment.display_name}: a disciplina não está no plano da turma')
                continue
            if not line.has_global_exam:
                lines_marked |= line
            by_class[(enrollment.class_id.id, subject_id)][enrollment_id] = score
        lines_marked.write({'has_global_exam': True})
        run.metrics['linhas_com_pg_marcadas'] = len(lines_marked)

        # d) Prova global: uma avaliação por turma e disciplina no último trimestre, com as notas.
        Assessment = env['edu.assessment']
        Grade = env['edu.grade']
        Class = env['edu.class']
        for (class_id, subject_id), scores in by_class.items():
            edu_class = Class.browse(class_id)
            last = edu_class.academic_year_id.trimester_ids.sorted('number')[-1:]
            assessment = Assessment.search(
                [
                    ('class_id', '=', class_id),
                    ('subject_id', '=', subject_id),
                    ('trimester_id', '=', last.id),
                    ('assessment_type', '=', 'global_exam'),
                ],
                limit=1,
            ) or Assessment.create(
                {
                    'name': env._('Prova global'),
                    'class_id': class_id,
                    'subject_id': subject_id,
                    'trimester_id': last.id,
                    'assessment_type': 'global_exam',
                    'date': last.date_end,
                }
            )
            grades = {grade.enrollment_id.id: grade for grade in assessment.grade_ids}
            new_grades = []
            for enrollment_id, score in scores.items():
                grade = grades.get(enrollment_id)
                if grade:
                    if grade.score != score or not grade.graded:
                        grade.write({'score': score})
                else:
                    new_grades.append({'assessment_id': assessment.id, 'enrollment_id': enrollment_id, 'score': score})
            Grade.create(new_grades)
            run.counts['global_exam_grades']['created'] += len(new_grades)

        # e) Recalcula a pauta anual de tudo o que se importou.
        recompute = Result.browse([r.id for r in results.values()])
        for start in range(0, len(recompute), 500):
            recompute[start : start + 500]._recompute()
        run.migrated_pairs = {pair: results[pair].id for pair in pairs}
        run.expected = {
            pair: (annual.get(pair), global_exam.get(pair), points.get(pair, (0, None))[0]) for pair in pairs
        }

    # ------------------------------------------------------------------
    # 9. Decisões de transição dos anos fechados
    # ------------------------------------------------------------------
    def _phase_decisions(self, run):
        src = run.src
        env = self.env
        closed_years = {t['academicYearId'] for t in src.rows('trimesters') if t.get('closedAt')} - {
            y['id'] for y in src.rows('academic_years') if y.get('current')
        }
        signed = {}
        for record in src.rows('academic_records'):
            if record['academicYearId'] in closed_years:
                class_id = self._class_for(run, record['classId'], record['academicYearId'])
                signed[(record['userId'], class_id)] = record.get('promotionStatus')
        Enrollment = env['edu.enrollment']
        offering_ids = [
            run.ref('class_offerings', o['id'])
            for o in src.rows('class_offerings')
            if o['academicYearId'] in closed_years and run.ref('class_offerings', o['id'])
        ]
        classes = env['edu.class'].browse(offering_ids)
        enrolled = Enrollment.search(
            [('class_id', 'in', classes.ids), ('state', 'in', ('active', 'irregular', 'completed', 'retained'))]
        )
        classes = enrolled.class_id
        Result = env['edu.year.result']
        Result.search([('class_id', 'in', classes.ids), ('manual', '=', True), ('reason', '=', SIGNED_REASON)]).write(
            {'manual': False}
        )
        results = Result._compute_for_classes(classes)
        student_user = {v: k for k, v in run.ids['students'].items()}
        agree = 0
        overridden = defaultdict(int)
        for result in results:
            user_id = student_user.get(result.student_id.id)
            status = signed.get((user_id, result.class_id.id))
            if status is None:
                run.issue('decisões', f'{result.enrollment_id.display_name}: sem decisão no secPed')
                continue
            if result.status in SIGNED_MATCHES.get(status, ()):
                agree += 1
                continue
            overridden[f'{status} ≠ {result.status}'] += 1
            if status == 'PENDING':
                run.issue(
                    'decisões', f'{result.enrollment_id.display_name}: pendente no secPed, {result.status} no Odoo'
                )
                continue
            terminal = result._policy()._rules(result.class_id).terminal
            new_status = 'retained' if status == 'RETAINED' else ('graduated' if terminal else 'promoted')
            result.requirement_ids.filtered(lambda r: r.state == 'pending').unlink()
            result.write({'status': new_status, 'manual': True, 'reason': SIGNED_REASON, 'requires_review': False})
        for result in results:
            state = {
                'promoted': 'completed',
                'graduated': 'completed',
                'conditional': 'completed',
                'retained': 'retained',
            }
            target = state.get(result.status)
            if target and result.enrollment_id.state != target:
                result.enrollment_id.state = target
        run.metrics['decisoes'] = len(results)
        run.metrics['decisoes_automaticas_iguais'] = agree
        run.metrics['decisoes_da_pauta_assinada'] = dict(overridden)

    # ------------------------------------------------------------------
    # 10. Épocas de provas
    # ------------------------------------------------------------------
    def _phase_exams(self, run):
        src = run.src
        cid = run.company.id
        run.upsert(
            'exam_periods',
            'edu.exam.period',
            [
                (
                    p['id'],
                    {
                        'name': p['name'],
                        'company_id': cid,
                        'academic_year_id': run.ref('academic_years', p['academicYearId']),
                        'trimester_id': run.ref('trimesters', p.get('trimesterId')) or False,
                        'date_start': to_date(p['startDate']),
                        'date_end': to_date(p['endDate']),
                        'kind': 'trimester_test',
                    },
                )
                for p in src.rows('exam_periods')
                if run.ref('academic_years', p['academicYearId'])
            ],
        )
        # O secPed tem uma sessão por turma; no Odoo, a mesma prova à mesma hora é uma sessão com várias turmas.
        grouped = defaultdict(list)
        for session in src.rows('exam_sessions'):
            period_id = run.ref('exam_periods', session.get('examPeriodId'))
            subject_id = run.ref('subjects', session.get('subjectId'))
            if not period_id or not subject_id:
                run.issue('exames', f'Sessão {session["name"]}: época ou disciplina em falta')
                continue
            key = (period_id, subject_id, to_date(session['date']), session['startTime'], session['endTime'])
            grouped[key].append(session)
        items = []
        session_of = {}
        for (period_id, subject_id, day, start, end), sessions in grouped.items():
            sid = min(s['id'] for s in sessions)
            classes = [self._class_for(run, s['classId'], s['academicYearId']) for s in sessions if s.get('classId')]
            items.append(
                (
                    sid,
                    {
                        'period_id': period_id,
                        'subject_id': subject_id,
                        'date': day,
                        'hour_from': minutes(start),
                        'hour_to': minutes(end),
                        'class_ids': [fields.Command.set([c for c in classes if c])],
                        'note': '\n'.join(s['notes'] for s in sessions if s.get('notes')) or False,
                    },
                )
            )
            for session in sessions:
                session_of[session['id']] = sid
        run.upsert('exam_sessions', 'edu.exam.session', items)
        supervisors = defaultdict(list)
        for row in src.rows('exam_supervisors'):
            employee = run.ref('teachers', row['supervisorId']) or run.ref('staff', row['supervisorId'])
            if employee:
                supervisors[row.get('examRoomId')].append(employee)
        rooms = []
        for row in src.rows('exam_rooms'):
            session_id = run.ref('exam_sessions', session_of.get(row['examSessionId']))
            room_id = run.ref('rooms', row['roomId'])
            if not session_id or not room_id:
                continue
            rooms.append(
                (
                    row['id'],
                    {
                        'session_id': session_id,
                        'room_id': room_id,
                        'capacity': row.get('capacity') or 0,
                        'supervisor_ids': [fields.Command.set(supervisors.get(row['id'], []))],
                    },
                )
            )
        run.upsert('exam_rooms', 'edu.exam.room', rooms)

    # ------------------------------------------------------------------
    # 11. Propinas: planos, taxas e multas (a facturação de teste do secPed não migra)
    # ------------------------------------------------------------------
    def _phase_fees(self, run):
        src = run.src
        cid = run.company.id
        Template = self.env['account.chart.template'].with_company(run.company)
        vat14 = Template.ref('ao_iva_sale_14', raise_if_not_found=False)
        plans = []
        for plan in src.rows('tuition_plans'):
            year_id = run.ref('academic_years', plan['academicYearId'])
            if not year_id:
                continue
            plans.append(
                (
                    plan['id'],
                    {
                        'name': plan['name'],
                        'company_id': cid,
                        'academic_year_id': year_id,
                        'course_id': run.ref('courses', plan.get('courseId')) or False,
                        'class_id': self._class_for(run, plan.get('classId'), plan['academicYearId']) or False,
                        'class_number': plan.get('classNumber') or 0,
                        'active': bool(plan.get('isActive', True)),
                    },
                )
            )
        run.upsert('tuition_plans', 'edu.fee.plan', plans)
        lines = []
        for fee in src.rows('tuition_fees'):
            plan_id = run.ref('tuition_plans', fee['tuitionPlanId'])
            if not plan_id or not fee.get('amount'):
                continue
            vals = {
                'plan_id': plan_id,
                'name': fee['name'],
                'amount': float(fee['amount']),
                'due_day': min(max(fee.get('dueDay') or 8, 1), 28),
                'category': FEE_CATEGORIES.get(fee.get('category'), 'other'),
                'recurrence': RECURRENCES.get(fee.get('recurrence'), 'one_off'),
                'occurrences': fee.get('occurrences') or 0,
                'mandatory': bool(fee.get('mandatory')),
            }
            if number(fee.get('taxRate')) == 14 and vat14:
                vals['tax_id'] = vat14.id
            lines.append((fee['id'], vals))
        run.upsert('tuition_fees', 'edu.fee.plan.line', lines)
        rules = []
        for rule in src.rows('late_fee_configs'):
            fixed = rule.get('feeType') == 'FIXED'
            rules.append(
                (
                    rule['id'],
                    {
                        'name': rule['name'],
                        'company_id': cid,
                        'fee_line_id': run.ref('tuition_fees', rule.get('tuitionFeeId')) or False,
                        'fee_type': 'fixed' if fixed else 'percent',
                        'amount': number(rule.get('feeValue')) if fixed else 0.0,
                        'percent': 0.0 if fixed else number(rule.get('feeValue')),
                        'grace_days': rule.get('graceDays') or 0,
                        'max_amount': number(rule.get('maxLateFee')) or 0.0,
                        'active': bool(rule.get('isActive', True)),
                    },
                )
            )
        run.upsert('late_fee_configs', 'edu.late.fee.rule', rules)
        invoices = len(src.rows('tuition_invoices'))
        if invoices:
            run.issue(
                'propinas',
                f'{invoices} facturas de propinas do secPed não migraram: a facturação certificada recomeça no Odoo',
            )

    # ------------------------------------------------------------------
    # Reconciliação
    # ------------------------------------------------------------------
    def _verify(self, run):
        """Contagens face ao secPed e, nota a nota, a classificação do ano do Odoo face ao cálculo do secPed."""
        env = self.env
        src = run.src
        company = run.company
        students = len([p for p in src.rows('student_profiles') if p['userId'] in run.users])
        enrollments = len([e for e in src.rows('enrollments') if e['userId'] in run.users])
        run.metrics['conferencia'] = {
            'alunos': (students, env['edu.student'].search_count([('company_id', '=', company.id)])),
            'matriculas': (enrollments, env['edu.enrollment'].search_count([('company_id', '=', company.id)])),
            'professores': (
                len([p for p in src.rows('teacher_profiles') if p['userId'] in run.users]),
                env['hr.employee'].search_count([('company_id', '=', company.id), ('edu_is_teacher', '=', True)]),
            ),
            'aulas_do_horario': (
                len(src.rows('schedules')),
                env['edu.schedule'].search_count([('company_id', '=', company.id)]),
            ),
        }
        expected = getattr(run, 'expected', None)
        if expected is None:
            return
        Result = env['edu.subject.result']
        mismatches = []
        matched = incomplete = 0
        for pair, result_id in run.migrated_pairs.items():
            cf, pg, points = expected[pair]
            want = secped_final(cf, pg, points)
            result = Result.browse(result_id)
            if want is None:
                incomplete += 1
                continue
            if result.complete and round(result.final, 4) == want:
                matched += 1
            else:
                mismatches.append(
                    {
                        'matricula': result.enrollment_id.display_name,
                        'disciplina': result.subject_id.name,
                        'cf': cf,
                        'pg': pg,
                        'bonificacao': points,
                        'secped': want,
                        'odoo': result.final if result.complete else None,
                    }
                )
        run.metrics['pauta'] = {
            'disciplinas_aluno': len(run.migrated_pairs),
            'iguais': matched,
            'diferentes': len(mismatches),
            'sem_cf': incomplete,
        }
        run.mismatches = mismatches
