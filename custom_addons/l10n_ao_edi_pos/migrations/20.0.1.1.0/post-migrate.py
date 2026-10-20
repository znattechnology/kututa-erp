"""20.0.1.1.0: menção legal dos impostos no talão.

O POS guarda os dados em cache e só volta a ler os registos alterados: marca-se os impostos como
alterados para que os postos recebam o novo campo.
"""


def migrate(cr, version):
    cr.execute('UPDATE account_tax SET write_date = now() AT TIME ZONE %s', ['UTC'])
