import logging
from datetime import datetime, time

import pytz

from odoo import api, fields, models

from ..tools.holidays import HALF_DAY_START, half_days, public_holidays

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ao_hr_holidays_generated_until = fields.Integer(
        string='Feriados gerados até ao ano', readonly=True, copy=False
    )

    def _l10n_ao_hr_is_angolan(self):
        self.ensure_one()
        return self.country_id.code == 'AO'

    def _l10n_ao_hr_generate_public_holidays(self, year=None):
        """Cria os feriados nacionais, as pontes e as tardes de 24 e 31 de Dezembro do ano como dias de
        encerramento da empresa. Não duplica nem sobrepõe dias já existentes (criados à mão ou antes)."""
        Leaves = self.env['resource.calendar.leaves'].sudo()
        for company in self.filtered(lambda c: c._l10n_ao_hr_is_angolan()):
            target = year or fields.Date.context_today(self).year
            years = [year] if year else range(max(company.l10n_ao_hr_holidays_generated_until + 1, target), target + 1)
            for current in years:
                existing = Leaves.search(
                    [
                        ('company_id', '=', company.id),
                        ('resource_id', '=', False),
                        ('date_from', '<=', company._l10n_ao_hr_utc(datetime(current + 1, 1, 1, 23, 59, 59))),
                        ('date_to', '>=', company._l10n_ao_hr_utc(datetime(current - 1, 12, 31))),
                    ]
                )

                def overlaps(vals, existing=existing):
                    return any(
                        leave.date_from <= vals['date_to'] and leave.date_to >= vals['date_from'] for leave in existing
                    )

                candidates = [
                    company._l10n_ao_hr_holiday_vals(name, day, time.min, time.max)
                    for day, name, _bridge in public_holidays(current)
                ]
                hour, minute = divmod(int(HALF_DAY_START * 60), 60)
                candidates += [
                    company._l10n_ao_hr_holiday_vals(f'{name} (a partir das 12h30)', day, time(hour, minute), time.max)
                    for day, name in half_days(current)
                ]
                vals = [candidate for candidate in candidates if not overlaps(candidate)]
                if vals:
                    Leaves.create(vals)
            company.l10n_ao_hr_holidays_generated_until = max(company.l10n_ao_hr_holidays_generated_until, target)

    def _l10n_ao_hr_utc(self, local):
        return pytz.timezone('Africa/Luanda').localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    def _l10n_ao_hr_holiday_vals(self, name, day, start, end):
        tz = pytz.timezone('Africa/Luanda')
        return {
            'name': name,
            'company_id': self.id,
            'date_from': tz.localize(datetime.combine(day, start)).astimezone(pytz.utc).replace(tzinfo=None),
            'date_to': tz.localize(datetime.combine(day, end)).astimezone(pytz.utc).replace(tzinfo=None),
        }

    def action_l10n_ao_hr_generate_public_holidays(self):
        today = fields.Date.context_today(self)
        for year in (today.year, today.year + 1):
            self._l10n_ao_hr_generate_public_holidays(year)

    @api.model
    def _cron_l10n_ao_hr_public_holidays(self):
        """Em Novembro, gera os feriados do ano seguinte."""
        today = fields.Date.context_today(self)
        companies = self.search([('partner_id.country_id', '=', self.env.ref('base.ao').id)])
        for company in companies:
            # Uma empresa com dados que não deixam gerar os feriados não trava as outras.
            try:
                with self.env.cr.savepoint():
                    company._l10n_ao_hr_generate_public_holidays(today.year)
                    if today.month >= 11:
                        company._l10n_ao_hr_generate_public_holidays(today.year + 1)
            except Exception:  # noqa: BLE001
                _logger.exception('Feriados de Angola: falha na empresa %s', company.name)
