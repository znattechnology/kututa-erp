from odoo import SUPERUSER_ID, api
from odoo.addons.kututa_web import _kututa_muk_colors


def migrate(cr, version):
    _kututa_muk_colors(api.Environment(cr, SUPERUSER_ID, {}))
