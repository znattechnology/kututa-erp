{
    'name': 'Secretaria Express - Propinas',
    'version': '20.0.1.1.0',
    'summary': 'Planos de propinas, facturas certificadas pela AGT, bolsas, multas, pagamentos e bloqueio de devedores',
    'description': """
Secretaria Express: a tesouraria da escola sobre a facturação do Odoo.

* Planos de propinas por ano lectivo e âmbito (turma, classe, curso ou geral), com matrícula, propina mensal,
  trimestral ou anual, exames, cartão e serviços a pedido; modo de cobrança da escola (sem propina, mensal,
  comparticipada)
* Cada cobrança é uma factura do Odoo (certificada pela AGT através do l10n_ao_edi), isenta de IVA pelo
  art. 12.º, n.º 1, al. l) do CIVA (código M21); o cartão e os bens levam IVA a 14%
* Geração mês a mês até ao mês corrente, sem duplicar; quem entra a meio do ano começa nesse mês
* Adquirente: o aluno com NIF, senão o encarregado principal com NIF, senão o aluno
* Bolsas (integral, parcial, mérito, carência, Estado, institucional) só na propina, a mais vantajosa, com
  aprovação por outro utilizador
* Multas por atraso (percentagem mensal ou valor fixo, tolerância e tecto) em factura própria
* Pagamentos ao balcão imputados às facturas mais antigas (o excedente fica como crédito); recibos pela AGT
* Situação financeira: dívida vencida com tolerância; avisar ou bloquear rematrícula, documentos e exames;
  isenção dos bolseiros do Estado e dos menores; matrícula «irregular» automática; lista de devedores
    """,
    'author': 'Kututa ERP',
    'countries': ['ao'],
    'category': 'Education',
    'depends': ['edu_documents', 'edu_exam', 'l10n_ao_edi'],
    'data': [
        'security/edu_fees_security.xml',
        'security/ir.access.csv',
        'data/product_data.xml',
        'data/ir_cron.xml',
        'wizard/edu_fee_wizards_views.xml',
        'views/edu_fee_plan_views.xml',
        'views/edu_scholarship_views.xml',
        'views/edu_fees_views.xml',
        'views/res_company_views.xml',
        'views/menus.xml',
        'report/edu_student_card_report.xml',
    ],
    'license': 'OPL-1',
}
