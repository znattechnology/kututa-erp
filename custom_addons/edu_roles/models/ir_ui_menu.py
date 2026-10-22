from odoo import api, models

# Menus que só fazem sentido com certos níveis de ensino na escola.
PRESCHOOL_MENUS = ('edu_evaluation.menu_edu_rdec', 'edu_roles.menu_teacher_rdec')


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _load_menus_blacklist(self):
        """O RDEC é da iniciação (DE 424/25, art. 20.º): numa escola sem turmas de iniciação (uma escola técnica, por
        exemplo) o menu não aparece."""
        hidden = super()._load_menus_blacklist()
        company = self.env.company
        preschool = (
            self.env['edu.class']
            .sudo()
            .search_count([('company_id', '=', company.id), ('level_id.code', '=', 'INICIACAO')], limit=1)
        )
        if not preschool:
            for xmlid in PRESCHOOL_MENUS:
                menu = self.env.ref(xmlid, raise_if_not_found=False)
                if menu:
                    hidden.append(menu.id)
        return hidden
