from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

CONTRACT_TYPES = [
    ('indefinite', 'Por tempo indeterminado'),
    ('fixed', 'A termo certo'),
    ('fixed_uncertain', 'A termo incerto'),
    ('service_commission', 'Comissão de serviço'),
    ('apprenticeship', 'Aprendizagem'),
    ('internship', 'Estágio'),
]
FIXED_TERM_TYPES = ('fixed', 'fixed_uncertain')
# Causas do contrato a termo (LGT, art. 15.º) e duração máxima em meses (art. 16.º); None = sem limite expresso.
FIXED_TERM_REASONS = [
    ('a', 'a) Substituição de trabalhador ausente'),
    ('b', 'b) Acréscimo temporário ou excepcional da actividade'),
    ('c', 'c) Tarefa ocasional ou serviço determinado'),
    ('d', 'd) Actividade sazonal'),
    ('e', 'e) Actividade de duração limitada'),
    ('f', 'f) Trabalho urgente para prevenir acidentes ou reparar avarias'),
    ('g', 'g) Lançamento de nova actividade ou estabelecimento'),
    ('h', 'h) Inserção de trabalhadores à procura do primeiro emprego'),
    ('i', 'i) Trabalhador reformado ou pensionista'),
    ('j', 'j) Actividade de carácter periódico'),
    ('k', 'k) Aprendizagem ou formação profissional'),
]
FIXED_TERM_MAX_MONTHS = {
    'a': 36,
    'b': 12,
    'c': 12,
    'd': 6,
    'e': 12,
    'f': 6,
    'g': 60,
    'h': None,
    'i': None,
    'j': 36,
    'k': 36,
}
TRIAL_MAX_DAYS = {'fixed': 30, 'indefinite': 60, 'indefinite_written': 120, 'director': 180}
NON_RENEWAL_NOTICE_DAYS = 30


class HrVersion(models.Model):
    _inherit = 'hr.version'

    l10n_ao_contract_type = fields.Selection(
        CONTRACT_TYPES,
        string='Tipo de contrato (LGT)',
        default='indefinite',
        tracking=1,
        groups='hr.group_hr_user',
        help='Por defeito o contrato é por tempo indeterminado (LGT, art. 12.º).',
    )
    l10n_ao_fixed_term_reason = fields.Selection(
        FIXED_TERM_REASONS,
        string='Causa do termo (art. 15.º)',
        tracking=1,
        groups='hr.group_hr_user',
    )
    l10n_ao_fixed_term_max_months = fields.Integer(
        string='Duração máxima (meses)', compute='_compute_l10n_ao_fixed_term_max_months', groups='hr.group_hr_user'
    )
    l10n_ao_is_director = fields.Boolean(
        string='Cargo de direcção ou quadro técnico',
        groups='hr.group_hr_user',
        help='Período experimental até 180 dias (LGT, art. 18.º).',
    )
    l10n_ao_trial_written = fields.Boolean(
        string='Período experimental alargado por escrito',
        groups='hr.group_hr_user',
        help='Contrato por tempo indeterminado: até 120 dias quando acordado por escrito (art. 18.º).',
    )
    l10n_ao_pay_basis = fields.Selection(
        [('month', 'Mensal'), ('lesson', 'Por tempo lectivo'), ('mixed', 'Misto (mensal e tempos lectivos)')],
        string='Base de pagamento',
        default='month',
        required=True,
        tracking=1,
        groups='hr.group_hr_user',
    )
    l10n_ao_lesson_rate = fields.Monetary(
        string='Valor por tempo lectivo', tracking=1, groups='hr.group_hr_user', currency_field='currency_id'
    )
    l10n_ao_weekly_hours = fields.Float(
        string='Horas semanais',
        compute='_compute_l10n_ao_weekly_hours',
        store=True,
        readonly=False,
        groups='hr.group_hr_user',
        help='Período normal de trabalho (LGT, art. 148.º: 44 h). Usado no salário-hora (art. 237.º, n.º 7).',
    )
    l10n_ao_renewal_count = fields.Integer(
        string='Renovações', compute='_compute_l10n_ao_renewals', groups='hr.group_hr_user'
    )
    l10n_ao_term_months = fields.Integer(
        string='Duração acumulada (meses)',
        compute='_compute_l10n_ao_renewals',
        groups='hr.group_hr_user',
        help='Duração do contrato a termo com as renovações sucessivas com a mesma causa (art. 16.º).',
    )

    @api.depends('l10n_ao_fixed_term_reason')
    def _compute_l10n_ao_fixed_term_max_months(self):
        for version in self:
            version.l10n_ao_fixed_term_max_months = FIXED_TERM_MAX_MONTHS.get(version.l10n_ao_fixed_term_reason) or 0

    @api.depends('resource_calendar_id.hours_per_week')
    def _compute_l10n_ao_weekly_hours(self):
        for version in self:
            version.l10n_ao_weekly_hours = version.resource_calendar_id.hours_per_week or 44.0

    @api.depends('employee_id', 'contract_date_start', 'contract_date_end', 'l10n_ao_fixed_term_reason')
    def _compute_l10n_ao_renewals(self):
        for version in self:
            chain = version._l10n_ao_term_chain()
            version.l10n_ao_renewal_count = max(len(chain) - 1, 0)
            if chain:
                start = min(chain.mapped('contract_date_start'))
                end = version.contract_date_end or fields.Date.context_today(self)
                delta = relativedelta(end + timedelta(days=1), start)
                version.l10n_ao_term_months = delta.years * 12 + delta.months + (1 if delta.days else 0)
            else:
                version.l10n_ao_term_months = 0

    def _l10n_ao_term_chain(self):
        """Contratos a termo anteriores do trabalhador com a mesma causa e sem interrupção (renovações)."""
        self.ensure_one()
        if self.l10n_ao_contract_type not in FIXED_TERM_TYPES or not self.contract_date_start:
            return self.env['hr.version']
        chain = self
        current = self
        while True:
            previous = self.env['hr.version'].search(
                [
                    ('employee_id', '=', self.employee_id.id),
                    ('id', '!=', current.id),
                    ('l10n_ao_contract_type', 'in', FIXED_TERM_TYPES),
                    ('l10n_ao_fixed_term_reason', '=', self.l10n_ao_fixed_term_reason),
                    ('contract_date_end', '>=', current.contract_date_start - timedelta(days=1)),
                    ('contract_date_end', '<', current.contract_date_start),
                ],
                order='contract_date_end desc',
                limit=1,
            )
            if not previous or previous in chain:
                return chain
            chain |= previous
            current = previous

    def _l10n_ao_trial_max_days(self):
        self.ensure_one()
        if self.l10n_ao_contract_type in FIXED_TERM_TYPES:
            return TRIAL_MAX_DAYS['fixed']
        if self.l10n_ao_is_director:
            return TRIAL_MAX_DAYS['director']
        if self.l10n_ao_trial_written:
            return TRIAL_MAX_DAYS['indefinite_written']
        return TRIAL_MAX_DAYS['indefinite']

    @api.constrains(
        'l10n_ao_contract_type',
        'l10n_ao_fixed_term_reason',
        'contract_date_start',
        'contract_date_end',
        'trial_date_end',
        'l10n_ao_is_director',
        'l10n_ao_trial_written',
    )
    def _check_l10n_ao_contract(self):
        for version in self:
            if not version.contract_date_start or version.company_id.country_id.code != 'AO':
                continue
            if version.l10n_ao_contract_type in FIXED_TERM_TYPES:
                if not version.l10n_ao_fixed_term_reason:
                    raise ValidationError(
                        self.env._(
                            'O contrato a termo tem de indicar a causa (LGT, art. 15.º); sem ela converte-se '
                            'em contrato por tempo indeterminado (art. 14.º).'
                        )
                    )
                if version.l10n_ao_contract_type == 'fixed' and not version.contract_date_end:
                    raise ValidationError(
                        self.env._('O contrato a termo certo tem de ter data de fim (LGT, art. 13.º).')
                    )
                limit = FIXED_TERM_MAX_MONTHS.get(version.l10n_ao_fixed_term_reason)
                if limit and version.l10n_ao_term_months > limit:
                    raise ValidationError(
                        self.env._(
                            'A duração do contrato a termo com a causa «%(reason)s», com as renovações, é de '
                            '%(months)s meses e o máximo é %(limit)s (LGT, art. 16.º). Acima do máximo, o contrato '
                            'converte-se em contrato por tempo indeterminado (art. 17.º).',
                            reason=dict(FIXED_TERM_REASONS)[version.l10n_ao_fixed_term_reason],
                            months=version.l10n_ao_term_months,
                            limit=limit,
                        )
                    )
            if version.trial_date_end:
                days = (version.trial_date_end - version.contract_date_start).days + 1
                maximum = version._l10n_ao_trial_max_days()
                if days > maximum:
                    raise ValidationError(
                        self.env._(
                            'O período experimental é de %(days)s dias e o máximo é %(max)s (LGT, art. 18.º).',
                            days=days,
                            max=maximum,
                        )
                    )

    def _l10n_ao_set_default_trial(self):
        """Primeiro contrato: período experimental por omissão (60 dias no indeterminado, 30 no termo), art. 18.º."""
        if self.env.context.get('l10n_ao_skip_trial'):
            return
        for version in self:
            if (
                version.contract_date_start
                and not version.trial_date_end
                and version.company_id.country_id.code == 'AO'
                and version.employee_id.version_ids.filtered('contract_date_start') == version
            ):
                version.trial_date_end = version.contract_date_start + timedelta(
                    days=version._l10n_ao_trial_max_days() - 1
                )

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions._l10n_ao_set_default_trial()
        return versions

    def write(self, vals):
        result = super().write(vals)
        if vals.get('contract_date_start') and not vals.get('trial_date_end'):
            self._l10n_ao_set_default_trial()
        return result

    @api.model
    def _cron_l10n_ao_hr_contract_alerts(self):
        """Aviso de não renovação (art. 17.º): 30 dias antes do fim do contrato a termo, uma actividade ao RH."""
        today = fields.Date.context_today(self)
        limit = today + timedelta(days=NON_RENEWAL_NOTICE_DAYS)
        versions = self.search(
            [
                ('l10n_ao_contract_type', 'in', FIXED_TERM_TYPES),
                ('contract_date_end', '>=', today),
                ('contract_date_end', '<=', limit),
                ('employee_id.active', '=', True),
            ]
        )
        for version in versions:
            employee = version.employee_id
            summary = self.env._('Fim do contrato a termo em %s', version.contract_date_end.strftime('%d/%m/%Y'))
            if employee.activity_ids.filtered(lambda a, s=summary: a.summary == s):
                continue
            employee.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=version.contract_date_end - timedelta(days=NON_RENEWAL_NOTICE_DAYS),
                summary=summary,
                note=self.env._(
                    'O aviso de não renovação tem de ser dado com 30 dias de antecedência (LGT, art. 17.º); '
                    'sem aviso, é devida uma compensação de 30 dias de salário. Renove ou comunique a cessação.'
                ),
                user_id=version.hr_responsible_id.id or self.env.uid,
            )
