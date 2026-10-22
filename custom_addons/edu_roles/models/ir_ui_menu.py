from odoo import api, models

# Menus que só fazem sentido com certos níveis de ensino na escola.
PRESCHOOL_MENUS = ('edu_evaluation.menu_edu_rdec', 'edu_roles.menu_teacher_rdec')
# A MAC é do ensino geral: sem turmas fora do técnico, o menu das avaliações contínuas não aparece.
GENERAL_MENUS = ('edu_roles.menu_my_assessments',)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _load_menus_blacklist(self):
        """O RDEC é da iniciação (DE 424/25, art. 20.º) e a MAC do ensino geral: numa escola sem turmas de iniciação ou
        só com o técnico (uma escola técnica, por exemplo) esses menus não aparecem."""
        hidden = super()._load_menus_blacklist()
        company = self.env.company
        preschool = (
            self.env['edu.class']
            .sudo()
            .search_count([('company_id', '=', company.id), ('level_id.code', '=', 'INICIACAO')], limit=1)
        )
        general = (
            self.env['edu.class']
            .sudo()
            .search_count([('company_id', '=', company.id), ('level_id.subsystem', '!=', 'technical')], limit=1)
        )
        xmlids = (PRESCHOOL_MENUS if not preschool else ()) + (GENERAL_MENUS if not general else ())
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.append(menu.id)
        return hidden
