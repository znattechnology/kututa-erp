import json
from datetime import date, timedelta
from pathlib import Path

from odoo import api, fields, models
from odoo.exceptions import UserError

EVENT_TYPES = [
    ('holiday', 'Feriado / pausa'),
    ('exam', 'Provas e exames'),
    ('meeting', 'Reunião'),
    ('activity', 'Actividade'),
    ('other', 'Outro'),
]
# Fases das matrículas no calendário: as candidaturas, a matrícula e a confirmação lêem-nas.
PHASES = [
    ('application', 'Inscrição de candidatos'),
    ('selection_test', 'Teste de selecção'),
    ('enrollment', 'Matrícula de novos alunos'),
    ('confirmation', 'Confirmação de matrículas'),
]
PHASE_TITLES = {
    'application': ('inscrição, selecção',),
    'selection_test': ('teste de selecção',),
    'enrollment': ('matrícula de novos alunos',),
    'confirmation': ('reconfirmação', 'confirmação de matrículas'),
}
SECPED_TYPES = {'HOLIDAY': 'holiday', 'EXAM': 'exam', 'MEETING': 'meeting', 'ACTIVITY': 'activity'}
NATIONAL_DIR = Path(__file__).resolve().parent.parent / 'data' / 'calendario'


class EduCalendarEvent(models.Model):
    """Calendário escolar: o Calendário Escolar Nacional (decreto executivo de cada ano) carregado em cada escola, que
    o pode editar e acrescentar os seus eventos. As fases das matrículas (inscrição, teste, matrícula, confirmação)
    alimentam as regras dos prazos."""

    _name = 'edu.calendar.event'
    _description = 'Evento do calendário escolar'
    _order = 'date_start, id'
    _check_company_auto = True

    name = fields.Char(string='Evento', required=True)
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    academic_year_id = fields.Many2one(
        'edu.academic.year', string='Ano lectivo', required=True, index=True, check_company=True, ondelete='cascade'
    )
    event_type = fields.Selection(EVENT_TYPES, string='Tipo', required=True, default='other')
    phase = fields.Selection(PHASES, string='Fase das matrículas', index=True)
    date_start = fields.Date(string='Início', required=True)
    date_end = fields.Date(string='Fim', help='Vazio: um só dia.')
    level_ids = fields.Many2many('edu.level', string='Níveis', help='Vazio: todos os níveis.')
    description = fields.Text(string='Descrição')
    national_key = fields.Char(string='Chave nacional', readonly=True, copy=False, index=True)
    is_national = fields.Boolean(string='Do calendário nacional', compute='_compute_is_national', store=True)
    edited = fields.Boolean(string='Alterado pela escola', readonly=True, copy=False)

    @api.depends('national_key')
    def _compute_is_national(self):
        for event in self:
            event.is_national = bool(event.national_key)

    def write(self, vals):
        if not self.env.context.get('edu_calendar_import') and {'name', 'date_start', 'date_end'} & set(vals):
            vals = {**vals, 'edited': True}
        return super().write(vals)

    @api.model
    def _phase_window(self, phase, level=None, company=None, around=None):
        """O período (início, fim) de uma fase das matrículas que abrange ``around`` (hoje) ou, sem isso, o mais
        próximo. Sem a fase no calendário, (False, False): não há prazo a aplicar."""
        company = company or self.env.company
        around = around or fields.Date.context_today(self)
        events = self.search([('company_id', '=', company.id), ('phase', '=', phase)])
        if level:
            events = events.filtered(lambda e: not e.level_ids or level in e.level_ids)
        if not events:
            return False, False
        windows = [(e.date_start, e.date_end or e.date_start) for e in events]
        current = [w for w in windows if w[0] <= around <= w[1]]
        if current:
            return current[0]
        return min(windows, key=lambda w: min(abs((w[0] - around).days), abs((w[1] - around).days)))

    @api.model
    def _days_without_lessons(self, company, level, date_from, date_to):
        """Os dias de feriado ou pausa do calendário escolar entre duas datas, para o nível: não há aulas."""
        events = self.search(
            [
                ('company_id', '=', company.id),
                ('event_type', '=', 'holiday'),
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '>=', date_from),
                ('date_start', '>=', date_from),
            ]
        )
        days = set()
        for event in events.filtered(lambda e: not e.level_ids or level in e.level_ids):
            day, end = max(event.date_start, date_from), min(event.date_end or event.date_start, date_to)
            while day <= end:
                days.add(day)
                day += timedelta(days=1)
        return days


class EduAcademicYear(models.Model):
    _inherit = 'edu.academic.year'

    calendar_event_ids = fields.One2many('edu.calendar.event', 'academic_year_id', string='Calendário escolar')

    def _national_calendar_file(self):
        self.ensure_one()
        return NATIONAL_DIR / f'calendario-nacional-{self.name.replace("/", "-")}.json'

    def action_load_national_calendar(self):
        """Carrega (ou actualiza) o Calendário Escolar Nacional deste ano lectivo. Os eventos que a escola alterou não
        se tocam; os que saíram do calendário nacional retiram-se, se a escola não os mudou."""
        Event = self.env['edu.calendar.event'].with_context(edu_calendar_import=True)
        Level = self.env['edu.level'].with_context(active_test=False)
        for year in self:
            path = year._national_calendar_file()
            if not path.exists():
                raise UserError(
                    self.env._('Não há calendário nacional para %s no sistema: introduza os eventos à mão.', year.name)
                )
            data = json.loads(path.read_text(encoding='utf-8'))
            existing = {e.national_key: e for e in year.calendar_event_ids if e.national_key}
            seen = set()
            for item in data['eventos']:
                key = f'{data["anoLectivo"]}|{item["titulo"]}|{item["inicio"]}'
                seen.add(key)
                title = item['titulo']
                phase = next((p for p, words in PHASE_TITLES.items() if any(w in title.lower() for w in words)), False)
                vals = {
                    'name': title,
                    'company_id': year.company_id.id,
                    'academic_year_id': year.id,
                    'event_type': SECPED_TYPES.get(item.get('tipo'), 'other'),
                    'phase': phase,
                    'date_start': date.fromisoformat(item['inicio']),
                    'date_end': date.fromisoformat(item['fim']) if item.get('fim') else False,
                    'description': item.get('descricao') or False,
                    'level_ids': [fields.Command.set(Level.search([('code', 'in', item.get('niveis') or [])]).ids)],
                    'national_key': key,
                }
                event = existing.get(key)
                if not event:
                    Event.create(vals)
                elif not event.edited:
                    event.write(vals)
            Event.browse([e.id for k, e in existing.items() if k not in seen and not e.edited]).unlink()
        return True

    def action_view_calendar(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('edu_core.action_edu_calendar_event')
        action['domain'] = [('academic_year_id', '=', self.id)]
        action['context'] = {'default_academic_year_id': self.id}
        return action
