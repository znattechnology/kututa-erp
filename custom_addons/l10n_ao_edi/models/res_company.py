import logging
import uuid

import requests

from odoo import fields, models
from odoo.exceptions import UserError

from ..tools import jws_sign

_logger = logging.getLogger(__name__)

AGT_ENDPOINTS = {
    'test': 'https://sifphml.minfin.gov.ao/sigt/fe/v1/',
    'production': 'https://sifp.minfin.gov.ao/sigt/fe/v1/',
}
AGT_SCHEMA_VERSION = '2.0'
AGT_TIMEOUT = 30


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ao_edi_enabled = fields.Boolean(
        string='Facturação electrónica AGT',
        help='Obrigatória para os Regimes Geral e Simplificado do IVA (art. 16.º do DP n.º 71/25).',
    )
    l10n_ao_edi_environment = fields.Selection(
        selection=[
            ('demo', 'Demonstração (sem envio à AGT)'),
            ('test', 'Homologação (testes)'),
            ('production', 'Produção'),
        ],
        string='Ambiente AGT',
        default='demo',
        help='Demonstração: as respostas da AGT são simuladas localmente e nada é enviado (formação e demos).',
    )
    l10n_ao_edi_username = fields.Char(string='Utilizador da API AGT', groups='base.group_system')
    l10n_ao_edi_password = fields.Char(string='Palavra-passe da API AGT', groups='base.group_system')
    l10n_ao_edi_product_id = fields.Char(string='Nome do software (productId)', default='Kututa ERP')
    l10n_ao_edi_product_version = fields.Char(string='Versão do software (productVersion)', default='1.0.0')
    l10n_ao_edi_software_validation_number = fields.Char(
        string='N.º de certificação do software',
        help='softwareValidationNumber atribuído pela AGT na certificação do software.',
    )
    l10n_ao_edi_signature_version = fields.Integer(
        string='Versão da assinatura',
        help='signatureVersion: só é enviada quando preenchida (a confirmar em homologação).',
    )
    l10n_ao_edi_software_key_id = fields.Many2one(
        'certificate.key',
        string='Chave privada do produtor de software',
        help='Assina jwsSoftwareSignature. A chave pública correspondente é registada no Portal do Parceiro.',
    )
    l10n_ao_edi_taxpayer_key_id = fields.Many2one(
        'certificate.key',
        string='Chave privada do contribuinte',
        help='Emitida pela AGT no Portal do Contribuinte. Assina jwsDocumentSignature e jwsSignature.',
    )
    l10n_ao_edi_establishment = fields.Char(
        string='Estabelecimento (AGT)',
        default='SEDE',
        help='Código do estabelecimento registado no Portal do Contribuinte («SEDE» se houver um só).',
    )
    l10n_ao_edi_last_communication = fields.Datetime(string='Última comunicação com a AGT', readonly=True)

    # -------------------------------------------------------------------------
    # Pedidos à API
    # -------------------------------------------------------------------------

    def _l10n_ao_edi_check_configuration(self):
        self.ensure_one()
        missing = [
            label
            for label, value in (
                (self.env._('NIF da empresa'), self.vat),
                (self.env._('N.º de certificação do software'), self.l10n_ao_edi_software_validation_number),
                (self.env._('Chave privada do produtor de software'), self.l10n_ao_edi_software_key_id),
                (self.env._('Chave privada do contribuinte'), self.l10n_ao_edi_taxpayer_key_id),
            )
            if not value
        ]
        if missing:
            raise UserError(
                self.env._(
                    'Configuração AGT incompleta na empresa %(company)s: %(fields)s.',
                    company=self.name,
                    fields=', '.join(missing),
                )
            )

    def _l10n_ao_edi_software_info(self):
        self.ensure_one()
        detail = {
            'productId': self.l10n_ao_edi_product_id or '',
            'productVersion': self.l10n_ao_edi_product_version or '',
            'softwareValidationNumber': self.l10n_ao_edi_software_validation_number or '',
        }
        if self.l10n_ao_edi_signature_version:
            detail['signatureVersion'] = self.l10n_ao_edi_signature_version
        return {
            'softwareInfoDetail': detail,
            'jwsSoftwareSignature': jws_sign(detail, self.l10n_ao_edi_software_key_id),
        }

    def _l10n_ao_edi_sign(self, payload):
        """Assinatura com a chave do contribuinte (jwsDocumentSignature / jwsSignature)."""
        self.ensure_one()
        return jws_sign(payload, self.l10n_ao_edi_taxpayer_key_id)

    def _l10n_ao_edi_request_envelope(self):
        self.ensure_one()
        return {
            'schemaVersion': AGT_SCHEMA_VERSION,
            'submissionUUID': str(uuid.uuid4()),
            'taxRegistrationNumber': self.partner_id._l10n_ao_normalize_nif(self.vat),
            'submissionTimeStamp': fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'softwareInfo': self._l10n_ao_edi_software_info(),
        }

    def _l10n_ao_edi_call(self, service, payload):
        """Chamada a um serviço REST da AGT. Devolve (código HTTP, corpo JSON).

        Ponto único de transporte: um integrador certificado pode substituir este método.
        """
        self.ensure_one()
        if (self.l10n_ao_edi_environment or 'demo') == 'demo':
            return self._l10n_ao_edi_simulate(service, payload)
        url = AGT_ENDPOINTS[self.l10n_ao_edi_environment] + service
        auth = (self.sudo().l10n_ao_edi_username or '', self.sudo().l10n_ao_edi_password or '')
        try:
            response = requests.post(url, json=payload, auth=auth, timeout=AGT_TIMEOUT)
        except requests.RequestException as error:
            _logger.warning('AGT %s: erro de comunicação: %s', service, error)
            return None, {'errorList': [{'idError': 'NET', 'descriptionError': str(error)}]}
        try:
            body = response.json()
        except ValueError:
            body = {'errorList': [{'idError': str(response.status_code), 'descriptionError': response.text[:500]}]}
        if response.status_code == 200:
            self.sudo().l10n_ao_edi_last_communication = fields.Datetime.now()
        return response.status_code, body

    def _l10n_ao_edi_simulate(self, service, payload):
        """Respostas simuladas da AGT (ambiente de demonstração): todos os documentos são aceites."""
        self.ensure_one()
        if service == 'registarFactura':
            return 200, {'requestID': fields.Datetime.now().strftime('DEMO%Y%m%d%H%M%S')[:15], 'errorList': []}
        if service == 'obterEstado':
            document = (
                self.env['l10n_ao_edi.document']
                .sudo()
                .search([('request_id', '=', payload.get('requestID')), ('company_id', '=', self.id)], limit=1)
            )
            return 200, {
                'requestID': payload.get('requestID'),
                'resultCode': '0',
                'documentStatusList': [
                    {'documentNo': name, 'documentStatus': 'V'} for name in document.move_ids.mapped('name')
                ],
            }
        if service == 'solicitarSerie':
            year = str(payload['seriesYear'])[-2:]
            code = f'{payload["documentType"]}{year}DEMO{payload["establishmentNumber"][:4].upper()}'
            return 200, {
                'resultCode': 1,
                'seriesFEResult': {'seriesCode': code, 'firstDocumentNo': '1', 'lastDocumentNo': '999999999999'},
            }
        return 200, {}
