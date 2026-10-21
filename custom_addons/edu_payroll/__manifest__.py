{
    'name': 'Secretaria Express - Carga lectiva nos salários',
    'version': '20.0.1.0.0',
    'summary': 'Tempos lectivos dos professores pagos à aula calculados a partir do horário',
    'description': """
Liga o horário escolar (edu_timetable) ao processamento salarial (l10n_ao_payroll).

Nos recibos dos professores pagos ao tempo lectivo, o número de tempos do mês é:
previstos no horário (dentro do trimestre do tempo e das datas do contrato) − aulas sem realização
− aulas dadas por um substituto + substituições dadas + acerto manual.
Um valor escrito à mão no recibo prevalece.
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_timetable', 'l10n_ao_payroll'],
    'data': ['views/l10n_ao_payroll_payslip_views.xml'],
    'auto_install': True,
    'license': 'OPL-1',
}
