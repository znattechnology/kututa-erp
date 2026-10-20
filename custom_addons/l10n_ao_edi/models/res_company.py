import logging
import uuid
from datetime import timedelta

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
AGT_COMMUNICATION_LOCK_DAYS = 60


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
    l10n_ao_edi_contingency = fields.Boolean(
        string='Modo de contingência',
        help='Art. 18.º do DP n.º 71/25: sem comunicação com a AGT, os documentos são emitidos numa série de '
        'contingência, com a menção «emitido em contingência, pendente de autorização», e enviados quando o '
        'modo for desligado. A AGT tem de ser informada de imediato.',
    )
    l10n_ao_edi_contingency_start = fields.Datetime(string='Contingência desde', readonly=True)

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
        if self.tax_calculation_rounding_method != 'round_per_line':
            # A AGT calcula o imposto linha a linha (taxContribution): com arredondamento global os totais divergem.
            missing.append(self.env._('Arredondamento do imposto «por linha» (Definições de Contabilidade)'))
        if missing:
            raise UserError(
                self.env._(
                    'Configuração AGT incompleta na empresa %(company)s: %(fields)s.',
                    company=self.name,
                    fields=', '.join(missing),
                )
            )

    def write(self, vals):
        if 'l10n_ao_edi_contingency' in vals:
            vals['l10n_ao_edi_contingency_start'] = fields.Datetime.now() if vals['l10n_ao_edi_contingency'] else False
        result = super().write(vals)
        if vals.get('l10n_ao_edi_contingency') is False:
            # Fim da contingência: os documentos emitidos entretanto seguem para a AGT.
            self.env.ref('l10n_ao_edi.ir_cron_l10n_ao_edi_send').sudo()._trigger()
        return result

    def _l10n_ao_edi_check_communication_lock(self):
        """Art. 17.º/5 do DP n.º 71/25: falha de comunicação superior a 60 dias bloqueia a emissão."""
        self.ensure_one()
        limit = fields.Datetime.now() - timedelta(days=AGT_COMMUNICATION_LOCK_DAYS)
        if self.l10n_ao_edi_last_communication and self.l10n_ao_edi_last_communication >= limit:
            return
        domain = [
            ('company_id', '=', self.id),
            ('l10n_ao_edi_state', '=', 'to_send'),
            ('l10n_ao_edi_system_entry_date', '<', limit),
        ]
        queue_models = self.env['l10n_ao_edi.document']._queue_fields()
        if any(self.env[model].sudo().search_count(domain, limit=1) for model in queue_models):
            raise UserError(
                self.env._(
                    'Emissão bloqueada: há documentos por comunicar à AGT há mais de %(days)s dias '
                    '(art. 17.º, n.º 5 do DP n.º 71/25). Restabeleça a comunicação e envie os documentos pendentes.',
                    days=AGT_COMMUNICATION_LOCK_DAYS,
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
            # As chaves só são legíveis por administradores: a assinatura é feita com privilégios de sistema
            # (qualquer utilizador que emite documentos tem de poder assinar).
            'jwsSoftwareSignature': jws_sign(detail, self.sudo().l10n_ao_edi_software_key_id),
        }

    def _l10n_ao_edi_sign(self, payload):
        """Assinatura com a chave do contribuinte (jwsDocumentSignature / jwsSignature)."""
        self.ensure_one()
        if self.env.context.get('l10n_ao_edi_skip_signature'):
            # Reconstrução do documento para fins internos (SAF-T): não se volta a assinar.
            return ''
        return jws_sign(payload, self.sudo().l10n_ao_edi_taxpayer_key_id)

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
            self.sudo().l10n_ao_edi_last_communication = fields.Datetime.now()
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
            # Resposta que não é da AGT (ex.: página de erro de um proxy): não conta como comunicação.
            body = {'errorList': [{'idError': str(response.status_code), 'descriptionError': response.text[:500]}]}
            return response.status_code, body
        if response.status_code == 200 and isinstance(body, dict):
            self.sudo().l10n_ao_edi_last_communication = fields.Datetime.now()
        return response.status_code, body

    def _l10n_ao_edi_simulate(self, service, payload):
        """Respostas simuladas da AGT (ambiente de demonstração): todos os documentos são aceites."""
        self.ensure_one()
        if service == 'registarFactura':
            return 200, {'requestID': f'DEMO{uuid.uuid4().hex[:11].upper()}', 'errorList': []}
        if service == 'obterEstado':
            document = (
                self.env['l10n_ao_edi.document']
                .sudo()
                .search([('request_id', '=', payload.get('requestID')), ('company_id', '=', self.id)], limit=1)
            )
            numbers = [record._l10n_ao_edi_number() for record in document._queued_records()] if document else []
            return 200, {
                'requestID': payload.get('requestID'),
                'resultCode': '0',
                'documentStatusList': [{'documentNo': number, 'documentStatus': 'V'} for number in numbers],
            }
        if service == 'solicitarSerie':
            year = str(payload['seriesYear'])[-2:]
            # Como nos exemplos da AGT («LD6325S2042N»): o código termina em N (normal) ou C (contingência).
            indicator = payload.get('seriesContingencyIndicator') or 'N'
            code = f'{payload["documentType"]}{year}DEMO{payload["establishmentNumber"][:4].upper()}{indicator}'
            return 200, {
                'resultCode': 1,
                'seriesFEResult': {'seriesCode': code, 'firstDocumentNo': '1', 'lastDocumentNo': '999999999999'},
            }
        if service == 'validarDocumento':
            action = payload.get('action')
            return 200, {
                'confirmRejectResult': {
                    'actionResultCode': f'{action}_OK',
                    'documentStatusCode': 'S_RG',
                    'errorList': [],
                }
            }
        if service == 'listarSeries':
            series = self.env['l10n_ao_edi.series'].search([('company_id', '=', self.id), ('code', '!=', False)])
            return 200, {
                'seriesResultCount': len(series),
                'seriesInfo': [
                    {
                        'seriesCode': s.code,
                        'seriesYear': s.year,
                        'documentType': s.document_type,
                        'establishmentNumber': s.establishment,
                    }
                    for s in series
                ],
            }
        return 200, {}
