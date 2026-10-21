from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _compute_tour_enabled(self):
        # Os tours de boas-vindas do Odoo (em inglês, com a marca Odoo) não fazem parte do Kututa.
        self.tour_enabled = False

    def _init_odoobot(self):
        # Sem a conversa de boas-vindas do OdooBot (em inglês) no primeiro arranque.
        self.ensure_one()
        self.sudo().odoobot_state = 'disabled'
        return self.env['discuss.channel']
