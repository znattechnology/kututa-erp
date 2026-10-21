from odoo import fields, models
from odoo.exceptions import ValidationError

UNJUSTIFIED_MONTH_LIMIT = 3
UNJUSTIFIED_YEAR_LIMIT = 12
ABANDONMENT_DAYS = 10


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _l10n_ao_days_in(self, date_from, date_to, exclude=None):
        """Dias de ausência validados do mesmo tipo e trabalhador no intervalo."""
        self.ensure_one()
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('work_entry_type_id', '=', self.work_entry_type_id.id),
            ('state', '=', 'validate'),
            (
                'date_from',
                '<=',
                fields.Datetime.to_string(fields.Datetime.end_of(fields.Datetime.to_datetime(date_to), 'day')),
            ),
            ('date_to', '>=', fields.Datetime.to_string(fields.Datetime.to_datetime(date_from))),
        ]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        return sum(self.search(domain).mapped('number_of_days'))

    def _l10n_ao_check_limits(self):
        for leave in self:
            kind = leave.work_entry_type_id
            if leave.employee_company_id.country_id.code != 'AO' or not leave.date_from:
                continue
            day = leave.date_from.date()
            if kind.l10n_ao_max_days_event and leave.number_of_days > kind.l10n_ao_max_days_event:
                raise ValidationError(
                    self.env._(
                        '«%(type)s»: o máximo por evento é %(max)s dias (LGT, art. 222.º).',
                        type=kind.name,
                        max=kind.l10n_ao_max_days_event,
                    )
                )
            month_start = day.replace(day=1)
            month_end = fields.Date.end_of(day, 'month')
            if kind.l10n_ao_max_days_month:
                used = leave._l10n_ao_days_in(month_start, month_end, exclude=leave) + leave.number_of_days
                if used > kind.l10n_ao_max_days_month:
                    raise ValidationError(
                        self.env._(
                            '«%(type)s»: o máximo por mês é %(max)s dias e com esta ausência ficam %(used)s '
                            '(LGT, art. 222.º).',
                            type=kind.name,
                            max=kind.l10n_ao_max_days_month,
                            used=used,
                        )
                    )
            if kind.l10n_ao_max_days_year:
                used = leave._l10n_ao_days_in(day.replace(month=1, day=1), day.replace(month=12, day=31), exclude=leave)
                used += leave.number_of_days
                if used > kind.l10n_ao_max_days_year:
                    raise ValidationError(
                        self.env._(
                            '«%(type)s»: o máximo por ano é %(max)s dias e com esta ausência ficam %(used)s '
                            '(LGT, art. 222.º).',
                            type=kind.name,
                            max=kind.l10n_ao_max_days_year,
                            used=used,
                        )
                    )

    def _l10n_ao_check_unjustified(self):
        """Faltas injustificadas: mais de 3 por mês ou 12 por ano são infracção disciplinar (art. 230.º);
        10 dias úteis seguidos presumem abandono do trabalho (art. 306.º). Avisa o RH, não bloqueia."""
        for leave in self:
            kind = leave.work_entry_type_id
            if kind.l10n_ao_justified or leave.employee_company_id.country_id.code != 'AO' or not leave.date_from:
                continue
            day = leave.date_from.date()
            month = leave._l10n_ao_days_in(day.replace(day=1), fields.Date.end_of(day, 'month'))
            year = leave._l10n_ao_days_in(day.replace(month=1, day=1), day.replace(month=12, day=31))
            notes = []
            if leave.number_of_days >= ABANDONMENT_DAYS:
                notes.append(
                    self.env._(
                        '%s dias úteis seguidos de faltas injustificadas presumem abandono do trabalho '
                        '(LGT, art. 306.º).',
                        ABANDONMENT_DAYS,
                    )
                )
            if month > UNJUSTIFIED_MONTH_LIMIT or year > UNJUSTIFIED_YEAR_LIMIT:
                notes.append(
                    self.env._(
                        'Faltas injustificadas: %(month)s no mês e %(year)s no ano; acima de 3 por mês ou 12 por ano '
                        'é infracção disciplinar (LGT, art. 230.º).',
                        month=month,
                        year=year,
                    )
                )
            if notes:
                leave.employee_id.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=self.env._('Faltas injustificadas'),
                    note=' '.join(notes),
                    user_id=leave.employee_id.leave_manager_id.id or self.env.uid,
                )

    def _action_validate(self, check_state=True):
        self._l10n_ao_check_limits()
        result = super()._action_validate(check_state=check_state)
        self._l10n_ao_check_unjustified()
        return result
