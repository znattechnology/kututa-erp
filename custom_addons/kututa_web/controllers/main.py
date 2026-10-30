import hashlib

from odoo import http
from odoo.http import request
from odoo.tools import file_open


class KututaFavicon(http.Controller):
    @http.route('/kututa_web/favicon', type='http', auth='public', readonly=True)
    def favicon(self):
        """Ícone do separador no cliente web: o favicon do site da empresa, ou o ícone do Kututa ERP.

        O favicon por omissão do website é o do Odoo; nesse caso (ou sem o módulo website) fica o do Kututa.
        """
        Website = request.env['website'].sudo()
        # O modelo «website» existe sempre (stub da base); o favicon só com o módulo website instalado.
        if 'favicon' in Website._fields:
            website = Website.search([('company_id', '=', request.env.company.id)], limit=1)
            website = website or Website.search([], limit=1)
            domain = [('res_model', '=', 'website'), ('res_field', '=', 'favicon'), ('res_id', '=', website.id)]
            attachment = request.env['ir.attachment'].sudo().search(domain, limit=1)
            if website and attachment and attachment.checksum != _odoo_favicon_checksum():
                return request.redirect(website.image_url(website, 'favicon'), local=True)
        return request.redirect('/kututa_web/static/img/favicon.png', local=True)


def _odoo_favicon_checksum():
    with file_open('web/static/img/favicon.ico', 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()
