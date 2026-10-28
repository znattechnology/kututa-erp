# O mixin de protecção define-se antes dos modelos que o herdam (a ordem alfabética não serve).
from . import l10n_ao_edi_guard  # noqa: I001  isort: skip
from . import (
    account_move,
    account_move_line,
    account_partial_reconcile,
    account_payment,
    ir_actions_report,
    l10n_ao_edi_document,
    l10n_ao_edi_series,
    product_template,
    res_company,
    res_partner,
)
