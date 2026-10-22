from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

TRIMESTERS = 3  # Angola: três trimestres por ano lectivo


class EduAcademicYear(models.Model):
    _name = 'edu.academic.year'
    _description = 'Ano lectivo'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Ano lectivo', required=True, tracking=True, help='Por exemplo, 2026/2027.')
    company_id = fields.Many2one(
        'res.company', string='Escola', required=True, default=lambda self: self.env.company, index=True
    )
    date_start = fields.Date(string='Início', required=True, tracking=True)
    date_end = fields.Date(string='Fim', required=True, tracking=True)
    is_current = fields.Boolean(string='Em curso', tracking=True)
    trimester_ids = fields.One2many('edu.trimester', 'academic_year_id', string='Trimestres')
    class_ids = fields.One2many('edu.class', 'academic_year_id', string='Turmas')
    class_count = fields.Integer(string='N.º de turmas', compute='_compute_class_count')
    active = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint('UNIQUE(company_id, name)', 'Já existe um ano lectivo com este nome.')
    # Um só ano em curso por escola.
    _one_current = models.UniqueIndex('(company_id) WHERE is_current IS TRUE')

    @api.depends('class_ids')
    def _compute_class_count(self):
        for year in self:
            year.class_count = len(year.class_ids)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for year in self:
            if year.date_end <= year.date_start:
                raise ValidationError(self.env._('O ano lectivo termina antes de começar.'))
            overlap = self.search_count(
                [
                    ('company_id', '=', year.company_id.id),
                    ('id', '!=', year.id),
                    ('date_start', '<=', year.date_end),
                    ('date_end', '>=', year.date_start),
                ]
            )
            if overlap:
                raise ValidationError(self.env._('O ano lectivo %s sobrepõe-se a outro da mesma escola.', year.name))

    def write(self, vals):
        if vals.get('is_current'):
            self.search(
                [('company_id', 'in', self.company_id.ids), ('is_current', '=', True), ('id', 'not in', self.ids)]
            ).write({'is_current': False})
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_current'):
                company_id = vals.get('company_id') or self.env.company.id
                self.search([('company_id', '=', company_id), ('is_current', '=', True)]).write({'is_current': False})
        return super().create(vals_list)

    def action_set_current(self):
        self.ensure_one()
        self.is_current = True

    def action_generate_trimesters(self):
        """Divide o ano em três trimestres de duração igual (datas editáveis depois)."""
        for year in self:
            if year.trimester_ids:
                raise UserError(self.env._('O ano lectivo %s já tem trimestres.', year.name))
            days = (year.date_end - year.date_start).days + 1
            start = year.date_start
            vals = []
            for number in range(1, TRIMESTERS + 1):
                end = year.date_end if number == TRIMESTERS else start + timedelta(days=round(days / 3) - 1)
                vals.append(
                    {
                        'academic_year_id': year.id,
                        'number': number,
                        'date_start': start,
                        'date_end': end,
                    }
                )
                start = end + timedelta(days=1)
            self.env['edu.trimester'].create(vals)
        return True

    def action_view_classes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Turmas de %s', self.name),
            'res_model': 'edu.class',
            'view_mode': 'list,form',
            'domain': [('academic_year_id', '=', self.id)],
            'context': {'default_academic_year_id': self.id},
        }


class EduTrimester(models.Model):
    _name = 'edu.trimester'
    _description = 'Trimestre'
    _inherit = ['mail.thread']
    _order = 'academic_year_id, number'
    _check_company_auto = True

    academic_year_id = fields.Many2one(
        'edu.academic.year', string='Ano lectivo', required=True, ondelete='cascade', index=True
    )
    company_id = fields.Many2one(related='academic_year_id.company_id', store=True, index=True)
    number = fields.Integer(string='N.º', required=True)
    name = fields.Char(string='Trimestre', compute='_compute_name', store=True, readonly=False)
    date_start = fields.Date(string='Início', required=True)
    date_end = fields.Date(string='Fim', required=True)
    is_current = fields.Boolean(string='Em curso')
    state = fields.Selection(
        [('open', 'Aberto'), ('closed', 'Fechado')], string='Estado', default='open', required=True, tracking=True
    )
    closed_date = fields.Datetime(string='Fechado em', readonly=True, copy=False)
    closed_by_id = fields.Many2one('res.users', string='Fechado por', readonly=True, copy=False)

    _year_number_uniq = models.Constraint(
        'UNIQUE(academic_year_id, number)', 'O ano lectivo já tem um trimestre com este número.'
    )
    _one_current = models.UniqueIndex('(academic_year_id) WHERE is_current IS TRUE')

    @api.depends('number')
    def _compute_name(self):
        for trimester in self:
            if trimester.number and not trimester.name:
                trimester.name = self.env._('%sº Trimestre', trimester.number)

    @api.constrains('number', 'date_start', 'date_end')
    def _check_dates(self):
        for trimester in self:
            year = trimester.academic_year_id
            if not 1 <= trimester.number <= TRIMESTERS:
                raise ValidationError(self.env._('O ano lectivo tem três trimestres (1 a 3).'))
            if trimester.date_end < trimester.date_start:
                raise ValidationError(self.env._('O trimestre termina antes de começar.'))
            if trimester.date_start < year.date_start or trimester.date_end > year.date_end:
                raise ValidationError(
                    self.env._(
                        'O %(trimester)s sai das datas do ano lectivo %(year)s.',
                        trimester=trimester.name,
                        year=year.name,
                    )
                )
            overlap = self.search_count(
                [
                    ('academic_year_id', '=', year.id),
                    ('id', '!=', trimester.id),
                    ('date_start', '<=', trimester.date_end),
                    ('date_end', '>=', trimester.date_start),
                ]
            )
            if overlap:
                raise ValidationError(self.env._('Os trimestres de %s sobrepõem-se.', year.name))

    def write(self, vals):
        guarded = {'state', 'closed_date', 'closed_by_id', 'date_start', 'date_end'}
        if (
            guarded & set(vals)
            and not self.env.su
            and not self.env.user.has_group('edu_core.group_edu_manager')
            and self.filtered(lambda t: t.state == 'closed')
        ):
            raise UserError(self.env._('Só a direcção altera ou reabre um trimestre fechado.'))
        if vals.get('is_current'):
            self.search(
                [
                    ('academic_year_id', 'in', self.academic_year_id.ids),
                    ('is_current', '=', True),
                    ('id', 'not in', self.ids),
                ]
            ).write({'is_current': False})
        return super().write(vals)

    def action_close(self):
        """Fecho do trimestre (Decreto Executivo n.º 424/25, arts. 35.º a 38.º): a pauta afixada é documento
        oficial; depois do fecho as notas só se corrigem por reapreciação."""
        for trimester in self.filtered(lambda t: t.state == 'open').sorted('number'):
            earlier = trimester.academic_year_id.trimester_ids.filtered(
                lambda t, n=trimester.number: t.number < n and t.state == 'open'
            )
            if earlier:
                raise UserError(self.env._('Feche primeiro o %s.', earlier.sorted('number')[0].name))
            trimester.write({'state': 'closed', 'closed_date': fields.Datetime.now(), 'closed_by_id': self.env.uid})
        return True

    def action_reopen(self):
        if not self.env.user.has_group('edu_core.group_edu_manager'):
            raise UserError(self.env._('Só a direcção reabre um trimestre fechado.'))
        for trimester in self.sorted('number', reverse=True):
            later = trimester.academic_year_id.trimester_ids.filtered(
                lambda t, n=trimester.number: t.number > n and t.state == 'closed'
            )
            if later:
                raise UserError(self.env._('Reabra primeiro o %s.', later.sorted('number')[-1].name))
            trimester.write({'state': 'open', 'closed_date': False, 'closed_by_id': False})
        return True
