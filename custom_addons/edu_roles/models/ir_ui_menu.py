from odoo import api, models

# Menus que só fazem sentido com certos níveis de ensino na escola. (No menu do professor, o RDEC e a MAC abrem-se
# dentro da turma, em «Turmas e notas», só nas turmas da iniciação e do ensino geral.)
PRESCHOOL_MENUS = ('edu_evaluation.menu_edu_rdec',)
# Os estágios e as PAP são do ensino técnico.
TECHNICAL_MENUS = ('edu_roles.menu_teacher_training',)
# O professor tem só o seu painel, como no secPed: as mensagens abrem-se em «Comunicação» e o calendário da escola em
# «Calendário académico». As aplicações do Odoo com o mesmo papel ficam escondidas.
TEACHER_HIDDEN_APPS = ('mail.menu_root_discuss', 'calendar.mail_menu_calendar')
# Quem tem um destes papéis usa as Discussões e o Calendário do Odoo no seu trabalho: não se escondem.
OTHER_ROLES = (
    'edu_core.group_edu_user',
    'base.group_system',
    'hr.group_hr_user',
    'account.group_account_invoice',
    'hr_holidays.group_hr_holidays_user',
)
PAYSLIPS_MENU = 'edu_roles.menu_teacher_payslips'


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _load_menus_blacklist(self):
        """O RDEC é da iniciação (DE 424/25, art. 20.º) e os estágios e as PAP do técnico: numa escola sem esses níveis
        os menus não aparecem. O professor (sem outro papel) não vê as Discussões nem o Calendário do Odoo.

        O menu fica em cache por utilizador (não por empresa): conta o que o utilizador tem em TODAS as suas escolas,
        para não mudar conforme a escola aberta quando a cache se preenche."""
        hidden = super()._load_menus_blacklist()
        user = self.env.user
        companies = user.company_ids
        Class = self.env['edu.class'].sudo()
        preschool = Class.search_count(
            [('company_id', 'in', companies.ids), ('level_id.code', '=', 'INICIACAO')], limit=1
        )
        technical = Class.search_count(
            [('company_id', 'in', companies.ids), ('level_id.subsystem', '=', 'technical')], limit=1
        )
        xmlids = (PRESCHOOL_MENUS if not preschool else ()) + (TECHNICAL_MENUS if not technical else ())
        # «Recibos e férias» só com alguma coisa para mostrar: o processamento salarial ou o acesso às ausências.
        time_off = self.env.ref('hr_holidays.group_hr_holidays_employee', raise_if_not_found=False)
        if 'l10n_ao_payroll.payslip' not in self.env and not (time_off and time_off in user.all_group_ids):
            xmlids += (PAYSLIPS_MENU,)
        if user._edu_teacher_only():
            xmlids += TEACHER_HIDDEN_APPS
            # Numa escola com o geral e o técnico, a formação técnica só para quem dá aulas ou dirige turmas do técnico,
            # ou é tutor de estágio, orientador ou júri de uma PAP deste ano (como no secPed).
            if technical and not self._teacher_in_technical(user):
                xmlids += TECHNICAL_MENUS
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.append(menu.id)
        return hidden

    @api.model
    def _teacher_in_technical(self, user):
        """Dá aulas ou dirige turmas do técnico no ano corrente, ou é tutor, orientador ou júri deste ano, numa das
        escolas do utilizador (as fichas de funcionário dele em cada escola)."""
        employees = user.sudo().employee_ids
        if not employees:
            return False
        current = [('academic_year_id.is_current', '=', True), ('company_id', 'in', user.company_ids.ids)]
        if (
            self.env['edu.class']
            .sudo()
            .search_count(
                [
                    *current,
                    ('level_id.subsystem', '=', 'technical'),
                    '|',
                    ('director_id', 'in', employees.ids),
                    ('assignment_ids.teacher_id', 'in', employees.ids),
                ],
                limit=1,
            )
        ):
            return True
        return bool(
            self.env['edu.internship'].sudo().search_count([*current, ('tutor_id', 'in', employees.ids)], limit=1)
            or self.env['edu.final.project']
            .sudo()
            .search_count(
                [*current, '|', ('advisor_id', 'in', employees.ids), ('jury_ids', 'in', employees.ids)], limit=1
            )
        )


class EduClass(models.Model):
    _inherit = 'edu.class'

    # Os menus que dependem dos níveis de ensino da escola (RDEC, formação técnica) e de quem dirige turmas do técnico
    # ficam em cache: uma turma nova, apagada ou que muda o que conta refaz a lista.
    @api.model_create_multi
    def create(self, vals_list):
        classes = super().create(vals_list)
        self.env.transaction.invalidate_ormcache()
        return classes

    def write(self, vals):
        result = super().write(vals)
        fields_that_count = {
            'level_id', 'company_id', 'curriculum_year_id', 'course_id', 'director_id', 'academic_year_id', 'active',
        }  # fmt: skip
        if fields_that_count & set(vals):
            self.env.transaction.invalidate_ormcache()
        return result

    def unlink(self):
        result = super().unlink()
        self.env.transaction.invalidate_ormcache()
        return result


class EduAcademicYear(models.Model):
    _inherit = 'edu.academic.year'

    # A formação técnica olha para o ano corrente: passar de ano refaz os menus.
    def write(self, vals):
        result = super().write(vals)
        if 'is_current' in vals:
            self.env.transaction.invalidate_ormcache()
        return result


class EduTeachingAssignment(models.Model):
    _inherit = 'edu.teaching.assignment'

    # Quem dá aulas no técnico vê a formação técnica no menu: as colocações refazem a lista.
    @api.model_create_multi
    def create(self, vals_list):
        assignments = super().create(vals_list)
        self.env.transaction.invalidate_ormcache()
        return assignments

    def write(self, vals):
        result = super().write(vals)
        if {'teacher_id', 'class_id'} & set(vals):
            self.env.transaction.invalidate_ormcache()
        return result

    def unlink(self):
        result = super().unlink()
        self.env.transaction.invalidate_ormcache()
        return result


class EduTrainingMixin(models.AbstractModel):
    _inherit = 'edu.training.mixin'

    # O mesmo para os tutores de estágio e os orientadores e júris das PAP.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env.transaction.invalidate_ormcache()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'tutor_id', 'advisor_id', 'jury_ids', 'academic_year_id'} & set(vals):
            self.env.transaction.invalidate_ormcache()
        return result

    def unlink(self):
        result = super().unlink()
        self.env.transaction.invalidate_ormcache()
        return result
