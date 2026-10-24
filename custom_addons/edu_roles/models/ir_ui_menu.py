from odoo import api, models

# Menus que só fazem sentido com certos níveis de ensino na escola. (No menu do professor, o RDEC e a MAC abrem-se
# dentro da turma, em «Turmas e notas», só nas turmas da iniciação e do ensino geral.)
PRESCHOOL_MENUS = ('edu_evaluation.menu_edu_rdec',)
# Os estágios e as PAP são do ensino técnico.
TECHNICAL_MENUS = ('edu_roles.menu_teacher_training',)
# O professor tem só o seu painel, como no secPed: as mensagens abrem-se em «Comunicação» e o calendário da escola em
# «Calendário académico». As aplicações do Odoo com o mesmo papel ficam escondidas.
TEACHER_HIDDEN_APPS = ('mail.menu_root_discuss', 'calendar.mail_menu_calendar')
# A conta mostra «Recibos e férias» com o processamento salarial ou as ausências instalados.
OPTIONAL_MENUS = {'edu_roles.menu_teacher_payslips': ('l10n_ao_payroll.payslip', 'hr.leave')}


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _load_menus_blacklist(self):
        """O RDEC é da iniciação (DE 424/25, art. 20.º) e os estágios e as PAP do técnico: numa escola sem esses níveis
        os menus não aparecem. O professor (sem acesso à secretaria) não vê as Discussões nem o Calendário do Odoo."""
        hidden = super()._load_menus_blacklist()
        company = self.env.company
        preschool = (
            self.env['edu.class']
            .sudo()
            .search_count([('company_id', '=', company.id), ('level_id.code', '=', 'INICIACAO')], limit=1)
        )
        technical = (
            self.env['edu.class']
            .sudo()
            .search_count([('company_id', '=', company.id), ('level_id.subsystem', '=', 'technical')], limit=1)
        )
        xmlids = (
            (PRESCHOOL_MENUS if not preschool else ())
            + (TECHNICAL_MENUS if not technical else ())
            + tuple(xmlid for xmlid, models_ in OPTIONAL_MENUS.items() if not any(m in self.env for m in models_))
        )
        user = self.env.user
        if user.has_group('edu_core.group_edu_teacher') and not (
            user.has_group('edu_core.group_edu_user') or user.has_group('base.group_system')
        ):
            xmlids += TEACHER_HIDDEN_APPS
            # Numa escola com o geral e o técnico, a formação técnica só para quem dá aulas ou dirige turmas do técnico,
            # ou é tutor de estágio, orientador ou júri de uma PAP (como no secPed).
            if technical and not self._teacher_in_technical(user.employee_id):
                xmlids += TECHNICAL_MENUS
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.append(menu.id)
        return hidden

    @api.model
    def _teacher_in_technical(self, employee):
        if not employee:
            return False
        technical = [('level_id.subsystem', '=', 'technical'), ('academic_year_id.is_current', '=', True)]
        Class = self.env['edu.class'].sudo()
        if Class.search_count(
            [*technical, '|', ('director_id', '=', employee.id), ('assignment_ids.teacher_id', '=', employee.id)],
            limit=1,
        ):
            return True
        return bool(
            self.env['edu.internship'].sudo().search_count([('tutor_id', '=', employee.id)], limit=1)
            or self.env['edu.final.project']
            .sudo()
            .search_count(['|', ('advisor_id', '=', employee.id), ('jury_ids', 'in', employee.ids)], limit=1)
        )


class EduClass(models.Model):
    _inherit = 'edu.class'

    # Os menus que dependem dos níveis de ensino da escola (RDEC, MAC, formação técnica) ficam em cache: uma turma
    # nova (ou que muda de nível ou de escola) refaz a lista.
    @api.model_create_multi
    def create(self, vals_list):
        classes = super().create(vals_list)
        self.env.transaction.invalidate_ormcache()
        return classes

    def write(self, vals):
        result = super().write(vals)
        if {'level_id', 'company_id', 'curriculum_year_id', 'course_id'} & set(vals):
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
        if {'tutor_id', 'advisor_id', 'jury_ids'} & set(vals):
            self.env.transaction.invalidate_ormcache()
        return result
