from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Tipos de documento de facturação electrónica (Anexo I do DE n.º 683/25, documentType).
AGT_DOCUMENT_TYPES = [
    ('FT', 'FT - Factura'),
    ('FR', 'FR - Factura/Recibo'),
    ('FA', 'FA - Factura de Adiantamento'),
    ('FG', 'FG - Factura Global'),
    ('GF', 'GF - Factura Genérica'),
    ('AC', 'AC - Aviso de Cobrança'),
    ('AR', 'AR - Aviso de Cobrança/Recibo'),
    ('TV', 'TV - Talão de Venda'),
    ('RC', 'RC - Recibo'),
    ('RG', 'RG - Recibo Geral'),
    ('RE', 'RE - Estorno ou Recibo de Estorno'),
    ('ND', 'ND - Nota de Débito'),
    ('NC', 'NC - Nota de Crédito'),
    ('AF', 'AF - Factura/Recibo de Autofacturação'),
    ('RP', 'RP - Prémio ou Recibo de Prémio'),
    ('RA', 'RA - Resseguro Aceite'),
    ('CS', 'CS - Imputação a Co-seguradoras'),
    ('LD', 'LD - Imputação a Co-seguradora Líder'),
]


class L10nAoEdiSeries(models.Model):
    """Série de numeração de documentos electrónicos.

    As séries são geradas pela AGT (art. 4.º do DE n.º 683/25), por tipo de documento, ano e
    estabelecimento. Facturas em séries não comunicadas consideram-se não emitidas (art. 35.º/4 do DP 71/25).
    """

    _name = 'l10n_ao_edi.series'
    _description = 'Série AGT'
    _order = 'year desc, document_type, id'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    document_type = fields.Selection(AGT_DOCUMENT_TYPES, string='Tipo de documento', required=True)
    year = fields.Integer(string='Ano', required=True, default=lambda self: fields.Date.context_today(self).year)
    establishment = fields.Char(
        string='Estabelecimento',
        required=True,
        default=lambda self: self.env.company.l10n_ao_edi_establishment or 'SEDE',
    )
    contingency = fields.Boolean(string='Série de contingência')
    code = fields.Char(string='Código da série (AGT)', copy=False, index=True)
    first_number = fields.Integer(string='Primeiro n.º autorizado', default=1, copy=False)
    last_number = fields.Float(string='Último n.º autorizado', digits=(16, 0), copy=False)
    next_number = fields.Integer(string='Próximo n.º', default=1, copy=False)
    state = fields.Selection(
        selection=[('draft', 'Por pedir'), ('active', 'Activa'), ('closed', 'Encerrada')],
        default='draft',
        required=True,
        copy=False,
    )
    name = fields.Char(compute='_compute_name', store=True)

    _code_company_uniq = models.Constraint('UNIQUE(company_id, code)', 'O código da série tem de ser único.')

    @api.depends('document_type', 'code', 'year', 'establishment')
    def _compute_name(self):
        for series in self:
            series.name = (
                series.code or f'{series.document_type or "?"} {series.year} {series.establishment or ""} (por pedir)'
            )

    @api.constrains('state', 'code')
    def _check_code(self):
        for series in self:
            if series.state == 'active' and not series.code:
                raise ValidationError(self.env._('Uma série activa tem de ter o código atribuído pela AGT.'))

    def action_activate(self):
        """Activa uma série obtida no Portal do Contribuinte (código introduzido manualmente)."""
        for series in self:
            if not series.code:
                raise UserError(self.env._('Indique o código da série atribuído pela AGT.'))
            series.state = 'active'

    def action_close(self):
        self.state = 'closed'

    def action_request_series(self):
        """Pede a série à AGT (serviço solicitarSerie)."""
        for series in self:
            company = series.company_id
            if company.l10n_ao_edi_environment != 'demo':
                company._l10n_ao_edi_check_configuration()
            signed = {
                'taxRegistrationNumber': company.partner_id._l10n_ao_normalize_nif(company.vat),
                'seriesYear': series.year,
                'documentType': series.document_type,
                'establishmentNumber': series.establishment,
                'seriesContingencyIndicator': 'C' if series.contingency else 'N',
            }
            payload = {
                **company._l10n_ao_edi_request_envelope(),
                'seriesYear': series.year,
                'documentType': series.document_type,
                'establishmentNumber': series.establishment,
                'seriesContingencyIndicator': signed['seriesContingencyIndicator'],
                'jwsSignature': company._l10n_ao_edi_sign(signed),
            }
            status, body = company._l10n_ao_edi_call('solicitarSerie', payload)
            result = (body or {}).get('seriesFEResult') or {}
            if status != 200 or str(body.get('resultCode')) != '1' or not result.get('seriesCode'):
                errors = '; '.join(
                    f'{e.get("idError", "")} {e.get("descriptionError", "")}'.strip() if isinstance(e, dict) else str(e)
                    for e in (body or {}).get('errorList') or []
                    if e
                )
                raise UserError(self.env._('A AGT recusou o pedido de série: %s', errors or status))
            series.write(
                {
                    'code': result['seriesCode'],
                    'first_number': int(result.get('firstDocumentNo') or 1),
                    'next_number': int(result.get('firstDocumentNo') or 1),
                    'last_number': float(result.get('lastDocumentNo') or 0),
                    'state': 'active',
                }
            )

    @api.model
    def _l10n_ao_edi_find(self, company, document_type, year, contingency=False):
        return self.search(
            [
                ('company_id', '=', company.id),
                ('document_type', '=', document_type),
                ('year', '=', year),
                ('establishment', '=', company.l10n_ao_edi_establishment or 'SEDE'),
                ('contingency', '=', contingency),
                ('state', '=', 'active'),
            ],
            order='id',
            limit=1,
        )

    def _l10n_ao_edi_reserve_number(self):
        """Reserva o próximo número da série, sem falhas: a linha da série fica bloqueada até ao fim da transacção."""
        self.ensure_one()
        self.env.cr.execute('SELECT next_number FROM l10n_ao_edi_series WHERE id = %s FOR UPDATE', [self.id])
        number = self.env.cr.fetchone()[0]
        if self.last_number and number > self.last_number:
            raise UserError(self.env._('A série %s esgotou os números autorizados pela AGT.', self.code))
        self.env.cr.execute('UPDATE l10n_ao_edi_series SET next_number = %s WHERE id = %s', [number + 1, self.id])
        self.invalidate_recordset(['next_number'])
        return number
