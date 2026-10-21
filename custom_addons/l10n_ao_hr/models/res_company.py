from datetime import datetime, time

import pytz

from odoo import api, fields, models

from ..tools.holidays import HALF_DAY_START, HALF_DAYS, public_holidays


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ao_hr_holidays_generated_until = fields.Integer(
        string='Feriados gerados até ao ano', readonly=True, copy=False
    )

    def _l10n_ao_hr_is_angolan(self):
        self.ensure_one()
        return self.country_id.code == 'AO'

    def _l10n_ao_hr_generate_public_holidays(self, year=None):
        """Cria os feriados nacionais (e as pontes) do ano como dias de encerramento da empresa."""
        Leaves = self.env['resource.calendar.leaves'].sudo()
        tz = pytz.timezone('Africa/Luanda')
        for company in self.filtered(lambda c: c._l10n_ao_hr_is_angolan()):
            target = year or fields.Date.context_today(self).year
            years = range(max(company.l10n_ao_hr_holidays_generated_until + 1, target), target + 1)
            if year:
                years = [year]
            for current in years:
                start = tz.localize(datetime(current, 1, 1)).astimezone(pytz.utc).replace(tzinfo=None)
                end = tz.localize(datetime(current, 12, 31, 23, 59, 59)).astimezone(pytz.utc).replace(tzinfo=None)
                existing = Leaves.search(
                    [
                        ('company_id', '=', company.id),
                        ('resource_id', '=', False),
                        ('date_from', '<=', end),
                        ('date_to', '>=', start),
                    ]
                )
                existing_days = {
                    fields.Datetime.context_timestamp(self.with_context(tz='Africa/Luanda'), leave.date_from).date()
                    for leave in existing
                }
                vals = []
                for day, name, _bridge in public_holidays(current):
                    if day in existing_days:
                        continue
                    vals.append(company._l10n_ao_hr_holiday_vals(name, day, time.min, time.max))
                for month, day_of_month, name in HALF_DAYS:
                    day = fields.Date.to_date(f'{current}-{month:02d}-{day_of_month:02d}')
                    if day in existing_days:
                        continue
                    hour, minute = divmod(int(HALF_DAY_START * 60), 60)
                    vals.append(
                        company._l10n_ao_hr_holiday_vals(
                            f'{name} (a partir das 12h30)', day, time(hour, minute), time.max
                        )
                    )
                if vals:
                    Leaves.create(vals)
            company.l10n_ao_hr_holidays_generated_until = max(company.l10n_ao_hr_holidays_generated_until, target)

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
        companies._l10n_ao_hr_generate_public_holidays(today.year)
        if today.month >= 11:
            companies._l10n_ao_hr_generate_public_holidays(today.year + 1)
