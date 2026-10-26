from odoo import SUPERUSER_ID, api

# As taxas do ensino vão para a AGT como «serviços de educação» (SE), não como prestação de serviço geral (SG). Os
# produtos são noupdate: nas bases já instaladas acerta-se aqui.
EDUCATION_PRODUCTS = [
    'product_tuition',
    'product_enrollment',
    'product_confirmation',
    'product_application',
    'product_transfer',
    'product_exam',
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in EDUCATION_PRODUCTS:
        product = env.ref(f'edu_fees.{xmlid}', raise_if_not_found=False)
        if product:
            product.l10n_ao_operation_type = 'SE'
