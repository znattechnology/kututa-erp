from contextlib import contextmanager

from odoo import models
from odoo.exceptions import AccessError

# Campos técnicos da comunicação com a AGT (estado, documento assinado, série, rejeições, impressões): só o
# próprio módulo os grava. O «readonly» das vistas não protege o RPC (o ORM só verifica «groups»), e mudar o
# estado AGT de um documento comunicado permitiria repô-lo em rascunho e alterá-lo depois de validado.
TECHNICAL_FIELDS = frozenset(
    {
        'l10n_ao_edi_series_id',
        'l10n_ao_edi_document_no',
        'l10n_ao_edi_state',
        'l10n_ao_edi_error',
        'l10n_ao_edi_system_entry_date',
        'l10n_ao_edi_contingency',
        'l10n_ao_edi_rejected_payloads',
        'l10n_ao_edi_rejected_document_no',
        'l10n_ao_edi_payload',
        'l10n_ao_edi_print_count',
        'l10n_ao_edi_document_ids',
        'l10n_ao_edi_vendor_state',
        'l10n_ao_edi_source_move_ids',
    }
)
TRUSTED = '_l10n_ao_edi_trusted'


@contextmanager
def trusted(env):
    """Marca, no cursor do servidor, as escritas feitas pelo próprio módulo. Ao contrário do contexto, o cliente
    (RPC) não consegue pôr esta marca."""
    previous = getattr(env.cr, TRUSTED, 0)
    setattr(env.cr, TRUSTED, previous + 1)
    try:
        yield
    finally:
        setattr(env.cr, TRUSTED, previous)


def is_trusted(env):
    return env.su or getattr(env.cr, TRUSTED, 0) > 0


class L10nAoEdiGuardMixin(models.AbstractModel):
    _name = 'l10n_ao_edi.guard.mixin'
    _description = 'Protecção dos campos técnicos AGT'

    def _l10n_ao_edi_technical_in(self, vals):
        return TECHNICAL_FIELDS.intersection(vals).intersection(self._fields)

    def _l10n_ao_edi_check_technical(self, vals):
        """Recusa a escrita dos campos técnicos AGT vinda do cliente."""
        if not is_trusted(self.env) and (blocked := self._l10n_ao_edi_technical_in(vals)):
            raise AccessError(
                self.env._(
                    'Os dados da comunicação com a AGT só são alterados pelo sistema (%s).',
                    ', '.join(sorted(self._fields[name].string for name in blocked)),
                )
            )

    def _l10n_ao_edi_strip_technical(self, vals):
        """Ignora os campos técnicos AGT vindos do cliente (o POS reenvia as vendas sincronizadas)."""
        if is_trusted(self.env) or not self._l10n_ao_edi_technical_in(vals):
            return vals
        return {key: value for key, value in vals.items() if key not in TECHNICAL_FIELDS}

    def _l10n_ao_edi_check_can_communicate(self, group='account.group_account_invoice'):
        """Antes de qualquer pedido à AGT (irreversível): quem o faz tem de poder alterar o documento."""
        if not self.env.su and not self.env.user.has_group(group):
            raise AccessError(self.env._('Não tem permissão para comunicar este documento à AGT.'))
        self.check_access('write')

    def _l10n_ao_edi_set(self, vals):
        """Escrita interna dos campos técnicos AGT."""
        with trusted(self.env):
            return self.write(vals)
