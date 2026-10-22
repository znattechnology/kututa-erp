from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .edu_course import COMPONENTS

# Matriz do plano no estilo da pauta: linhas cinzentas, cabeçalhos a negrito, sem fundos de cor.
MATRIX_STYLE = 'width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; color: #000;'
CELL = 'border-right: 1px solid #c8c8c8; border-bottom: 1px solid #c8c8c8; padding: 5px 8px;'
HEAD = (
    'border-right: 1px solid #969696; border-bottom: 1px solid #969696; border-top: 1px solid #969696; '
    'padding: 6px 8px;'
)
FIRST = 'border-left: 1px solid #c8c8c8;'


class EduCurriculum(models.Model):
    _name = 'edu.curriculum'
    _description = 'Plano curricular'
    _inherit = ['mail.thread']
    _order = 'level_id, name'
    _check_company_auto = True

    name = fields.Char(string='Plano curricular', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    course_id = fields.Many2one(
        'edu.course', string='Curso', check_company=True, help='Vazio no plano do tronco comum de um nível.'
    )
    level_id = fields.Many2one('edu.level', string='Nível', required=True)
    template_id = fields.Many2one('edu.curriculum.template', string='Molde de origem', readonly=True)
    description = fields.Text(string='Descrição')
    is_national = fields.Boolean(string='Plano nacional', help='Criado a partir de um molde nacional.')
    class_from = fields.Integer(string='Da classe', compute='_compute_classes', store=True)
    class_to = fields.Integer(string='À classe', compute='_compute_classes', store=True)
    year_ids = fields.One2many('edu.curriculum.year', 'curriculum_id', string='Anos')
    line_ids = fields.One2many('edu.curriculum.line', 'curriculum_id', string='Disciplinas')
    plan_matrix = fields.Html(string='Plano', compute='_compute_plan_matrix', sanitize=False)
    active = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint('UNIQUE(company_id, name)', 'Já existe um plano com este nome.')

    @api.depends('year_ids.class_number')
    def _compute_classes(self):
        for curriculum in self:
            classes = curriculum.year_ids.mapped('class_number')
            curriculum.class_from = min(classes) if classes else 0
            curriculum.class_to = max(classes) if classes else 0

    @api.depends(
        'year_ids.class_number',
        'line_ids.subject_id',
        'line_ids.weekly_hours',
        'line_ids.component',
        'line_ids.year_id',
    )
    def _compute_plan_matrix(self):
        """O plano como no secPed e nos planos oficiais: as disciplinas agrupadas pela componente de formação, uma
        coluna por classe com os tempos semanais, os tempos de cada componente e o total da classe."""
        labels = dict(COMPONENTS)
        for curriculum in self:
            years = curriculum.year_ids.sorted('year')
            if not years:
                curriculum.plan_matrix = False
                continue
            hours, component_of = {}, {}
            for line in curriculum.line_ids:
                hours[line.subject_id, line.year_id] = line.weekly_hours
                component_of.setdefault(line.subject_id, line.component or False)
            groups = [(code, labels[code]) for code, _label in COMPONENTS]
            groups.append((False, self.env._('Sem componente')))
            html = Markup('<table class="o_edu_plan_matrix" style="%s"><thead><tr>') % Markup(MATRIX_STYLE)
            html += Markup('<th style="%s%s text-align: left;">%s</th>') % (
                Markup(FIRST.replace('#c8c8c8', '#969696')),
                Markup(HEAD),
                self.env._('Disciplina'),
            )
            for year in years:
                html += Markup('<th style="%s text-align: center; width: 5.5rem;">%s</th>') % (
                    Markup(HEAD),
                    self.env._('%sª', year.class_number),
                )
            html += Markup('</tr></thead><tbody>')
            for code, label in groups:
                subjects = sorted((s for s, c in component_of.items() if c == code), key=lambda s: s.name or '')
                if not subjects:
                    continue
                html += Markup('<tr><td style="%s%s font-weight: bold;">%s</td>') % (Markup(FIRST), Markup(CELL), label)
                for year in years:
                    total = sum(hours.get((subject, year), 0) for subject in subjects)
                    html += Markup('<td style="%s text-align: center; font-weight: bold;">%s</td>') % (
                        Markup(CELL),
                        total or '',
                    )
                html += Markup('</tr>')
                for subject in subjects:
                    html += Markup('<tr><td style="%s%s padding-left: 24px;">%s</td>') % (
                        Markup(FIRST),
                        Markup(CELL),
                        subject.name,
                    )
                    for year in years:
                        value = hours.get((subject, year))
                        html += Markup('<td style="%s text-align: center;">%s</td>') % (
                            Markup(CELL),
                            '' if value is None else value,
                        )
                    html += Markup('</tr>')
            html += Markup('<tr><td style="%s%s font-weight: bold;">%s</td>') % (
                Markup(FIRST),
                Markup(CELL),
                self.env._('Tempos por semana'),
            )
            for year in years:
                html += Markup('<td style="%s text-align: center; font-weight: bold;">%s</td>') % (
                    Markup(CELL),
                    year.weekly_hours,
                )
            curriculum.plan_matrix = html + Markup('</tr></tbody></table>')

    @api.model
    def _unique_name(self, company, base):
        """Nome único na escola: «Plano», «Plano (2)», «Plano (3)»…"""
        name, number = base, 2
        while self.with_context(active_test=False).search_count([('company_id', '=', company.id), ('name', '=', name)]):
            name = f'{base} ({number})'
            number += 1
        return name

    def _copy_version(self, name):
        """Nova versão do plano (anos e disciplinas), para as turmas de um ano lectivo em diante. As turmas antigas
        ficam na versão em que estudaram: as pautas e os históricos não mudam."""
        self.ensure_one()
        version = self.copy({'name': self._unique_name(self.company_id, name)})
        for year in self.year_ids:
            new_year = year.copy({'curriculum_id': version.id})
            for line in year.line_ids:
                line.copy({'year_id': new_year.id})
        return version

    def _action_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'edu.curriculum',
            'res_id': self.id,
            'view_mode': 'form',
        }


class EduCurriculumYear(models.Model):
    _name = 'edu.curriculum.year'
    _description = 'Ano (classe) do plano curricular'
    _order = 'curriculum_id, year'

    curriculum_id = fields.Many2one('edu.curriculum', string='Plano', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='curriculum_id.company_id', store=True, index=True)
    year = fields.Integer(string='Ano do curso', required=True)
    class_number = fields.Integer(string='Classe', required=True, help='Classe nacional correspondente (0 a 13).')
    name = fields.Char(string='Designação')
    line_ids = fields.One2many('edu.curriculum.line', 'year_id', string='Disciplinas')
    weekly_hours = fields.Integer(string='Tempos semanais', compute='_compute_weekly_hours')

    _curriculum_year_uniq = models.Constraint('UNIQUE(curriculum_id, year)', 'O plano já tem este ano.')

    @api.depends('line_ids.weekly_hours')
    def _compute_weekly_hours(self):
        for year in self:
            year.weekly_hours = sum(year.line_ids.mapped('weekly_hours'))

    @api.depends('curriculum_id', 'class_number', 'name')
    def _compute_display_name(self):
        for year in self:
            label = year.name or self.env._('%sª Classe', year.class_number)
            year.display_name = f'{label} · {year.curriculum_id.name}' if year.curriculum_id else label

    @api.constrains('class_number')
    def _check_class_number(self):
        for year in self:
            if not 0 <= year.class_number <= 13:
                raise ValidationError(self.env._('A classe vai de 0 (iniciação) a 13.'))


class EduCurriculumLine(models.Model):
    _name = 'edu.curriculum.line'
    _description = 'Disciplina do plano curricular'
    _order = 'year_id, sequence, id'
    _check_company_auto = True

    year_id = fields.Many2one('edu.curriculum.year', string='Ano', required=True, ondelete='cascade', index=True)
    curriculum_id = fields.Many2one(related='year_id.curriculum_id', store=True, index=True)
    company_id = fields.Many2one(related='year_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    subject_id = fields.Many2one('edu.subject', string='Disciplina', required=True, check_company=True)
    code = fields.Char(related='subject_id.code')
    weekly_hours = fields.Integer(string='Tempos semanais', default=3)
    component = fields.Selection(
        COMPONENTS, string='Componente', compute='_compute_component', store=True, readonly=False, precompute=True
    )
    is_compulsory = fields.Boolean(string='Obrigatória', default=True)
    is_national_exam = fields.Boolean(string='Exame nacional')

    _year_subject_uniq = models.Constraint('UNIQUE(year_id, subject_id)', 'A disciplina já está neste ano do plano.')

    @api.depends('subject_id')
    def _compute_component(self):
        for line in self:
            if not line.component:
                line.component = line.subject_id.component

    @api.constrains('weekly_hours')
    def _check_hours(self):
        for line in self:
            if line.weekly_hours < 0:
                raise ValidationError(self.env._('Os tempos semanais não podem ser negativos.'))
