from odoo import SUPERUSER_ID, api
from odoo.addons.kututa_web import _kututa_login_terms


def migrate(cr, version):
    _kututa_login_terms(api.Environment(cr, SUPERUSER_ID, {}))
