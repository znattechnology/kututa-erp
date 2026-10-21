from odoo import api, fields, models

from .edu_course import COMPONENTS


class EduCurriculumTemplate(models.Model):
    """Molde curricular nacional (catálogo global, sem escola). O plano de um curso compõe o tronco comum do
    nível com o perfil do curso: o perfil sobrepõe a carga e o exame e acrescenta as disciplinas específicas."""

    _name = 'edu.curriculum.template'
    _description = 'Molde curricular nacional'
    _order = 'level_id, is_profile, name'

    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Molde', required=True)
    description = fields.Text(string='Descrição')
    level_id = fields.Many2one('edu.level', string='Nível', required=True)
    is_profile = fields.Boolean(string='Perfil de curso', help='Desmarcado: tronco comum do nível.')
    version = fields.Integer(string='Versão', default=1)
    year_ids = fields.One2many('edu.curriculum.template.year', 'template_id', string='Anos')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE(code)', 'Já existe um molde com este código.')

    @api.model
    def _find(self, level, profile=False):
        """Tronco comum activo mais recente do nível."""
        return self.search(
            [('level_id', '=', level.id), ('is_profile', '=', profile)], order='version desc, id desc', limit=1
        )

    def _compose(self, *templates):
        """{classe: {código: linha do molde}}; os moldes seguintes sobrepõem os anteriores."""
        by_class = {}
        names = {}
        for template in templates:
            for year in template.year_ids.sorted('year'):
                bucket = by_class.setdefault(year.class_number, {})
                names.setdefault(year.class_number, year.name)
                for line in year.line_ids.sorted('sequence'):
                    bucket[line.subject_code] = line
        return by_class, names

    def _materialize(self, company, course=None, profile=None, name=None):
        """Cria na escola o plano curricular deste molde (com o perfil, se houver) e as disciplinas em falta.

        Idempotente por curso: se o curso já tem um plano nacional, devolve-o.
        """
        self.ensure_one()
        Curriculum = self.env['edu.curriculum'].with_company(company)
        if course:
            existing = Curriculum.search([('course_id', '=', course.id), ('is_national', '=', True)], limit=1)
            if existing:
                return existing
        templates = self | profile if profile else self
        by_class, year_names = self._compose(*templates)
        if not by_class:
            return Curriculum
        subjects = self._ensure_subjects(company, by_class)
        chosen = profile or self
        curriculum = Curriculum.create(
            {
                'name': Curriculum._unique_name(company, name or chosen.name),
                'company_id': company.id,
                'course_id': course.id if course else False,
                'level_id': self.level_id.id,
                'template_id': chosen.id,
                'description': chosen.description,
                'is_national': True,
            }
        )
        for index, class_number in enumerate(sorted(by_class), start=1):
            self.env['edu.curriculum.year'].create(
                {
                    'curriculum_id': curriculum.id,
                    'year': index,
                    'class_number': class_number,
                    'name': year_names.get(class_number) or self.env._('%sª Classe', class_number),
                    'line_ids': [
                        fields.Command.create(
                            {
                                'sequence': sequence,
                                'subject_id': subjects[code].id,
                                'weekly_hours': line.weekly_hours,
                                'component': line.component,
                                'is_compulsory': line.is_compulsory,
                                'is_national_exam': line.is_national_exam,
                            }
                        )
                        for sequence, (code, line) in enumerate(by_class[class_number].items(), start=1)
                    ],
                }
            )
        return curriculum

    def _ensure_subjects(self, company, by_class):
        """Catálogo de disciplinas da escola por código: reutiliza (e reactiva) ou cria."""
        Subject = self.env['edu.subject'].with_context(active_test=False)
        first = {}
        for bucket in by_class.values():
            for code, line in bucket.items():
                first.setdefault(code, line)
        existing = {s.code: s for s in Subject.search([('company_id', '=', company.id), ('code', 'in', list(first))])}
        result = {}
        for code, line in first.items():
            subject = existing.get(code)
            if subject:
                if not subject.active:
                    subject.active = True
            else:
                subject = Subject.create(
                    {
                        'name': line.name,
                        'code': code,
                        'company_id': company.id,
                        'component': line.component,
                        'duration_years': line.duration_years,
                        'start_year': line.start_year,
                        'is_national_exam': line.is_national_exam,
                    }
                )
            result[code] = subject
        return result


class EduCurriculumTemplateYear(models.Model):
    _name = 'edu.curriculum.template.year'
    _description = 'Ano do molde curricular'
    _order = 'template_id, year'

    template_id = fields.Many2one(
        'edu.curriculum.template', string='Molde', required=True, ondelete='cascade', index=True
    )
    year = fields.Integer(string='Ano', required=True)
    class_number = fields.Integer(string='Classe', required=True)
    name = fields.Char(string='Designação')
    line_ids = fields.One2many('edu.curriculum.template.line', 'year_id', string='Disciplinas')

    _template_year_uniq = models.Constraint('UNIQUE(template_id, year)', 'O molde já tem este ano.')


class EduCurriculumTemplateLine(models.Model):
    _name = 'edu.curriculum.template.line'
    _description = 'Disciplina do molde curricular'
    _order = 'year_id, sequence, id'

    year_id = fields.Many2one(
        'edu.curriculum.template.year', string='Ano', required=True, ondelete='cascade', index=True
    )
    template_id = fields.Many2one(related='year_id.template_id', store=True)
    sequence = fields.Integer(default=10)
    subject_code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Disciplina', required=True)
    weekly_hours = fields.Integer(string='Tempos semanais', default=3)
    component = fields.Selection(COMPONENTS, string='Componente')
    duration_years = fields.Integer(string='Duração (anos)', default=1)
    start_year = fields.Integer(string='Começa no ano', default=1)
    is_compulsory = fields.Boolean(string='Obrigatória', default=True)
    is_national_exam = fields.Boolean(string='Exame nacional')

    _year_code_uniq = models.Constraint('UNIQUE(year_id, subject_code)', 'A disciplina repete-se neste ano do molde.')
