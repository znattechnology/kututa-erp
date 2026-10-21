from datetime import timedelta

from odoo import api, fields, models

UNJUSTIFIED_MONTH_LIMIT = 3
UNJUSTIFIED_YEAR_LIMIT = 12
ABANDONMENT_DAYS = 10


def business_days(date_from, date_to):
    """Dias úteis (segunda a sexta) entre duas datas, inclusive."""
    count = 0
    day = date_from
    while day <= date_to:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    l10n_ao_unpaid_days = fields.Float(
        string='Dias não remunerados (LGT)',
        readonly=True,
        copy=False,
        help='Dias para lá dos limites remunerados da LGT (arts. 222.º a 229.º): a falta é justificada, mas não paga.',
    )

    def _l10n_ao_local_dates(self):
        """(primeiro dia, último dia) da ausência na data local do trabalhador."""
        self.ensure_one()
        return self.request_date_from or self.date_from.date(), self.request_date_to or self.date_to.date()

    def _l10n_ao_days_within(self, date_from, date_to):
        """Dias desta ausência que caem no intervalo (proporcionais aos dias úteis, ou de calendário)."""
        self.ensure_one()
        start, end = self._l10n_ao_local_dates()
        clip_from, clip_to = max(start, date_from), min(end, date_to)
        if clip_from > clip_to:
            return 0.0
        if start >= date_from and end <= date_to:
            return self.number_of_days
        if self.work_entry_type_id.count_days_as == 'calendar':
            return float((clip_to - clip_from).days + 1)
        # Proporção pelos dias de trabalho do horário do trabalhador (inclui o sábado no horário de 44 h).
        total = self._l10n_ao_work_days(start, end)
        part = self._l10n_ao_work_days(clip_from, clip_to)
        return self.number_of_days * part / total if total else 0.0

    def _l10n_ao_work_days(self, date_from, date_to):
        """Dias com horário de trabalho no intervalo (cada dia conta um, seja inteiro ou meio dia, como no Odoo)."""
        self.ensure_one()
        calendar = self.resource_calendar_id or self.employee_id.resource_calendar_id
        weekdays = {int(day) for day in calendar.attendance_ids.mapped('dayofweek')} if calendar else set(range(5))
        count = 0
        day = date_from
        while day <= date_to:
            if day.weekday() in weekdays:
                count += 1
            day += timedelta(days=1)
        return count

    def _l10n_ao_days_in(self, date_from, date_to, exclude=None):
        """Dias de ausência validados do mesmo tipo e trabalhador no intervalo (só a parte dentro dele)."""
        self.ensure_one()
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('work_entry_type_id', '=', self.work_entry_type_id.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', date_to),
            ('request_date_to', '>=', date_from),
        ]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        return sum(leave._l10n_ao_days_within(date_from, date_to) for leave in self.search(domain))

    def _l10n_ao_compute_unpaid_days(self):
        """Parte da ausência acima dos limites remunerados: por evento, por mês e por ano.

        Na LGT, o excesso continua a ser falta justificada, mas não é pago (arts. 223.º/2, 224.º, 226.º/4,
        227.º, 228.º/4): por isso não se recusa a ausência, marca-se a parte não paga para a folha.
        """
        for leave in self:
            kind = leave.work_entry_type_id
            if leave.employee_company_id.country_id.code != 'AO' or not leave.date_from:
                leave.l10n_ao_unpaid_days = 0.0
                continue
            start, end = leave._l10n_ao_local_dates()
            excess = 0.0
            if kind.l10n_ao_max_days_event:
                excess = max(excess, leave.number_of_days - kind.l10n_ao_max_days_event)
            if kind.l10n_ao_max_days_month:
                # Cada mês que a ausência toca tem o seu limite.
                month_excess = 0.0
                month_start = start.replace(day=1)
                while month_start <= end:
                    month_end = fields.Date.end_of(month_start, 'month')
                    used = leave._l10n_ao_days_in(month_start, month_end, exclude=leave)
                    mine = leave._l10n_ao_days_within(month_start, month_end)
                    month_excess += max(0.0, min(mine, used + mine - kind.l10n_ao_max_days_month))
                    month_start = month_end + timedelta(days=1)
                excess = max(excess, month_excess)
            if kind.l10n_ao_max_days_year:
                year_start, year_end = start.replace(month=1, day=1), start.replace(month=12, day=31)
                used = leave._l10n_ao_days_in(year_start, year_end, exclude=leave)
                mine = leave._l10n_ao_days_within(year_start, year_end)
                excess = max(excess, min(mine, used + mine - kind.l10n_ao_max_days_year))
            leave.l10n_ao_unpaid_days = max(excess, 0.0)
            if leave.l10n_ao_unpaid_days:
                leave.message_post(
                    body=self.env._(
                        '%(days)s dia(s) acima do limite remunerado de «%(type)s»: falta justificada, não remunerada '
                        '(LGT, arts. 222.º a 229.º).',
                        days=round(leave.l10n_ao_unpaid_days, 2),
                        type=kind.name,
                    )
                )

    def _l10n_ao_unjustified_run(self):
        """Dias úteis seguidos de faltas injustificadas que incluem esta ausência (juntando as contíguas)."""
        self.ensure_one()
        start, end = self._l10n_ao_local_dates()
        leaves = self.search(
            [
                ('employee_id', '=', self.employee_id.id),
                ('work_entry_type_id.l10n_ao_justified', '=', False),
                ('state', '=', 'validate'),
                ('request_date_from', '<=', end + timedelta(days=30)),
                ('request_date_to', '>=', start - timedelta(days=30)),
            ]
        )
        days = set()
        for leave in leaves:
            first, last = leave._l10n_ao_local_dates()
            day = first
            while day <= last:
                if day.weekday() < 5:
                    days.add(day)
                day += timedelta(days=1)

        def step(day, direction):
            day += timedelta(days=direction)
            while day.weekday() >= 5:
                day += timedelta(days=direction)
            return day

        run_start, run_end = start, end
        while step(run_start, -1) in days:
            run_start = step(run_start, -1)
        while step(run_end, 1) in days:
            run_end = step(run_end, 1)
        return business_days(run_start, run_end)

    def _l10n_ao_check_unjustified(self):
        """Faltas injustificadas: mais de 3 por mês ou 12 por ano são infracção disciplinar (art. 230.º);
        10 dias úteis seguidos presumem abandono do trabalho (art. 306.º). Avisa o RH, não bloqueia."""
        for leave in self:
            kind = leave.work_entry_type_id
            if kind.l10n_ao_justified or leave.employee_company_id.country_id.code != 'AO' or not leave.date_from:
                continue
            start, _end = leave._l10n_ao_local_dates()
            month = leave._l10n_ao_days_in(start.replace(day=1), fields.Date.end_of(start, 'month'))
            year = leave._l10n_ao_days_in(start.replace(month=1, day=1), start.replace(month=12, day=31))
            notes = []
            if leave._l10n_ao_unjustified_run() >= ABANDONMENT_DAYS:
                notes.append(
                    self.env._(
                        '%s ou mais dias úteis seguidos de faltas injustificadas presumem abandono do trabalho '
                        '(LGT, art. 306.º).',
                        ABANDONMENT_DAYS,
                    )
                )
            if month > UNJUSTIFIED_MONTH_LIMIT or year > UNJUSTIFIED_YEAR_LIMIT:
                notes.append(
                    self.env._(
                        'Faltas injustificadas: %(month)s no mês e %(year)s no ano; acima de 3 por mês ou 12 por ano '
                        'é infracção disciplinar (LGT, art. 230.º).',
                        month=round(month, 1),
                        year=round(year, 1),
                    )
                )
            if notes:
                leave.employee_id._l10n_ao_hr_notify(self.env._('Faltas injustificadas'), ' '.join(notes))

    def _action_validate(self, check_state=True):
        result = super()._action_validate(check_state=check_state)
        self._l10n_ao_compute_unpaid_days()
        self._l10n_ao_check_unjustified()
        return result

    @api.model
    def _l10n_ao_unpaid_hours(self, employee, date_from, date_to, hours_per_day):
        """Horas não remuneradas das ausências pagas que excedem os limites da LGT, no intervalo.

        As ausências de tipos não pagos ficam de fora: a folha já as desconta por inteiro.
        """
        leaves = self.search(
            [
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('l10n_ao_unpaid_days', '>', 0),
                ('work_entry_type_id.unpaid', '=', False),
                ('work_entry_type_id.l10n_ao_payroll_code', 'not in', ('UNPAID', 'UNJUSTIFIED', 'MATERNITY')),
                ('request_date_from', '<=', date_to),
                ('request_date_to', '>=', date_from),
            ]
        )
        hours = 0.0
        for leave in leaves:
            share = leave._l10n_ao_days_within(date_from, date_to) / (leave.number_of_days or 1)
            hours += leave.l10n_ao_unpaid_days * share * hours_per_day
        return hours
