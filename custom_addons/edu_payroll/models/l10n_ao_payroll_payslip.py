from datetime import timedelta

from odoo import fields, models


class L10nAoPayrollPayslip(models.Model):
    _inherit = 'l10n_ao_payroll.payslip'

    edu_planned = fields.Integer(string='Tempos previstos no horário', readonly=True)
    edu_exceptions = fields.Integer(string='Aulas sem realização', readonly=True)
    edu_replacement_out = fields.Integer(string='Dadas por substitutos', readonly=True)
    edu_replacement_in = fields.Integer(string='Substituições dadas', readonly=True)
    edu_adjustment = fields.Integer(
        string='Acerto de tempos', help='Aulas de compensação, correcções (positivo ou negativo).'
    )
    edu_lesson_manual = fields.Boolean(
        string='Tempos escritos à mão', help='O recálculo não altera os tempos lectivos deste recibo.'
    )

    def write(self, vals):
        if 'lesson_count' in vals and not self.env.context.get('edu_payroll_auto'):
            vals = dict(vals, edu_lesson_manual=True)
        return super().write(vals)

    def _inputs(self):
        self.ensure_one()
        version = self.employee_id._l10n_ao_payroll_version_for(self.run_id.date_from, self.run_id.date_to)
        if version and version.l10n_ao_pay_basis != 'month' and not self.edu_lesson_manual:
            load = self._edu_teaching_load()
            self.with_context(edu_payroll_auto=True).write(
                {
                    'edu_planned': load['planned'],
                    'edu_exceptions': load['exceptions'],
                    'edu_replacement_out': load['out'],
                    'edu_replacement_in': load['in'],
                    'lesson_count': max(
                        0, load['planned'] - load['exceptions'] - load['out'] + load['in'] + self.edu_adjustment
                    ),
                }
            )
        return super()._inputs()

    def _edu_teaching_load(self):
        """Tempos do mês: os dias do horário de cada tempo do professor dentro do mês, do ano lectivo, do trimestre
        do tempo e dos períodos de contrato; menos as aulas sem realização desses dias; menos as aulas dadas por
        um substituto; mais as substituições que o professor deu, nos mesmos períodos."""
        self.ensure_one()
        employee = self.employee_id
        run = self.run_id
        windows = [
            (start, end) for _version, start, end in employee._l10n_ao_payroll_segments(run.date_from, run.date_to)
        ]

        def inside(day):
            return any(start <= day <= end for start, end in windows)

        Schedule = self.env['edu.schedule'].sudo()
        planned = exceptions = 0
        for schedule in Schedule.search([('teacher_id', '=', employee.id), ('company_id', '=', run.company_id.id)]):
            excepted = set(schedule.exception_ids.mapped('date'))
            day = run.date_from
            while day <= run.date_to:
                if inside(day) and self._edu_slot_on(schedule, day):
                    planned += 1
                    exceptions += day in excepted
                day += timedelta(days=1)
        Replacement = self.env['edu.schedule.replacement'].sudo()
        month = [('date', '>=', run.date_from), ('date', '<=', run.date_to)]
        out = len(
            Replacement.search([('original_teacher_id', '=', employee.id), *month]).filtered(
                lambda r: inside(r.date) and r.date not in r.schedule_id.exception_ids.mapped('date')
            )
        )
        given = len(
            Replacement.search([('replacement_teacher_id', '=', employee.id), *month]).filtered(
                lambda r: inside(r.date) and r.date not in r.schedule_id.exception_ids.mapped('date')
            )
        )
        return {'planned': planned, 'exceptions': exceptions, 'out': out, 'in': given}

    def _edu_slot_on(self, schedule, day):
        """O tempo existe nesse dia (dia da semana, ano lectivo e trimestre), com ou sem aula registada."""
        if str(day.weekday()) != schedule.weekday:
            return False
        year = schedule.academic_year_id
        if not year.date_start <= day <= year.date_end:
            return False
        trimester = schedule.trimester_id
        return not trimester or trimester.date_start <= day <= trimester.date_end
