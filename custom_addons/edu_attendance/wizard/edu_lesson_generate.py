from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

PERIODS = [('week', 'Esta semana'), ('next', 'Próxima semana'), ('custom', 'Outras datas')]
# Um período longo (o ano todo) torna a contagem lenta: as aulas geram-se por semanas ou por um trimestre.
MAX_DAYS = 100
# As turmas do ano em curso e as dos anos que ainda vão começar (em Setembro o ano novo já tem turmas e horários).
CLASS_DOMAIN = (
    "['|', ('academic_year_id.is_current', '=', True), "
    "('academic_year_id.date_start', '>', context_today().strftime('%Y-%m-%d'))]"
)


class EduLessonGenerate(models.TransientModel):
    """Gerar as aulas previstas a partir do horário: a semana (esta ou a próxima) ou outras datas, todas as turmas do
    ano em curso ou só algumas, e quantas aulas vão ser criadas antes de as criar."""

    _name = 'edu.lesson.generate'
    _description = 'Gerar as aulas previstas a partir do horário'

    period = fields.Selection(PERIODS, string='Período', required=True, default='week')
    all_classes = fields.Boolean(string='Todas as turmas', default=True)
    class_ids = fields.Many2many('edu.class', string='Turmas', domain=CLASS_DOMAIN)
    date_from = fields.Date(
        string='De', compute='_compute_dates', store=True, readonly=False, precompute=True, required=True
    )
    date_to = fields.Date(
        string='Até', compute='_compute_dates', store=True, readonly=False, precompute=True, required=True
    )
    preview = fields.Char(string='Resultado', compute='_compute_preview')

    @api.model
    def _week_start(self):
        """A segunda-feira desta semana (de segunda a domingo), como o filtro «Esta semana» das aulas."""
        today = fields.Date.context_today(self)
        return today - timedelta(days=today.weekday())

    @api.depends('period')
    def _compute_dates(self):
        for wizard in self:
            if wizard.period == 'custom' and wizard.date_from and wizard.date_to:
                continue
            monday = self._week_start() + timedelta(days=7 if wizard.period == 'next' else 0)
            wizard.date_from = monday
            wizard.date_to = monday + timedelta(days=6)

    def _classes(self):
        self.ensure_one()
        if self.all_classes:
            # Cada horário só gera aulas dentro do seu ano lectivo: com o ano novo já criado, as datas decidem.
            return self.env['edu.class'].search(
                [
                    '|',
                    ('academic_year_id.is_current', '=', True),
                    ('academic_year_id.date_start', '>', fields.Date.context_today(self)),
                    ('company_id', 'in', self.env.companies.ids),
                ]
            )
        return self.class_ids

    @api.depends('all_classes', 'class_ids', 'date_from', 'date_to')
    def _compute_preview(self):
        Lesson = self.env['edu.lesson']
        for wizard in self:
            classes = wizard._classes()
            if not classes or not wizard.date_from or not wizard.date_to or wizard.date_to < wizard.date_from:
                wizard.preview = False
                continue
            if (wizard.date_to - wizard.date_from).days >= MAX_DAYS:
                wizard.preview = self.env._('No máximo %s dias de cada vez (um trimestre).', MAX_DAYS)
                continue
            count = len(Lesson._generate_vals(classes, wizard.date_from, wizard.date_to))
            if not count:
                wizard.preview = self.env._('Não há aulas novas a criar: já existem ou o período não tem aulas.')
                continue
            lessons = self.env._('1 aula') if count == 1 else self.env._('%s aulas', count)
            where = self.env._('1 turma') if len(classes) == 1 else self.env._('%s turmas', len(classes))
            wizard.preview = self.env._('Vão ser criadas %(lessons)s em %(where)s.', lessons=lessons, where=where)

    def action_generate(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(self.env._('A data final é anterior à inicial.'))
        if (self.date_to - self.date_from).days >= MAX_DAYS:
            raise UserError(self.env._('No máximo %s dias de cada vez (um trimestre).', MAX_DAYS))
        classes = self._classes()
        if not classes:
            raise UserError(self.env._('Escolha as turmas.'))
        lessons = self.env['edu.lesson']._generate(classes, self.date_from, self.date_to)
        if not lessons:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'message': self.env._('Não havia aulas novas a criar: já existiam ou o período não tem aulas.'),
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        action = self.env['ir.actions.actions']._for_xml_id('edu_attendance.action_edu_lesson')
        action.update(
            {
                'name': self.env._('Aulas geradas'),
                'domain': [('id', 'in', lessons.ids)],
                'context': {},
            }
        )
        return action
