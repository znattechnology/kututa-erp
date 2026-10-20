import re
from collections import defaultdict
from datetime import timedelta

from odoo import api, models
from odoo.tools import float_round

# Subcontas de transferência para resultados (x.9 do PGC). Recebem o apuramento e não entram na DR.
# 68.9 e 78.9 (alterações de políticas contabilísticas) e 82.9 (outros custos operacionais) são rubricas.
TRANSFER_ACCOUNT_RE = re.compile(r'^(6[0-79]|7[0-79]|8[3-9])\.9(\.|$)|^(68|78|82)\.19(\.|$)')

# Grupos de proveitos e custos (2 dígitos) -> (subconta de transferência, conta de resultados da classe 8).
CLOSING_TRANSFERS = {
    '61': ('61.9', '82.1'),
    '62': ('62.9', '82.2'),
    '63': ('63.9', '82.3'),
    '64': ('64.9', '82.4'),
    '65': ('65.9', '82.5'),
    '71': ('71.9', '82.6'),
    '72': ('72.9', '82.7'),
    '73': ('73.9', '82.8'),
    '75': ('75.9', '82.9'),
    '66': ('66.9', '83.1'),
    '76': ('76.9', '83.2'),
    '67': ('67.9', '84.1'),
    '77': ('77.9', '84.2'),
    '68': ('68.19', '85.1'),
    '78': ('78.19', '85.2'),
    '69': ('69.9', '86.1'),
    '79': ('79.9', '86.2'),
}
# Contas de resultados (82 a 86) -> (subconta de transferência, conta do resultado líquido 88).
RESULT_TRANSFERS = {
    '82': ('82.19', '88.1'),
    '83': ('83.9', '88.2'),
    '84': ('84.9', '88.3'),
    '85': ('85.9', '88.4'),
    '86': ('86.9', '88.6'),
}
# Imposto sobre os lucros (87): corrente e extraordinário.
TAX_TRANSFER = '87.9'
TAX_RESULT_ACCOUNTS = {'87.2': '88.7'}
TAX_RESULT_DEFAULT = '88.5'
NET_RESULT_TRANSFER = '88.9'

CLASS_NAMES = {
    '1': 'Meios fixos e investimentos',
    '2': 'Existências',
    '3': 'Terceiros',
    '4': 'Meios monetários',
    '5': 'Capital e reservas',
    '6': 'Proveitos e ganhos por natureza',
    '7': 'Custos e perdas por natureza',
    '8': 'Resultados',
    '0': 'Contas de ordem',
}

# Modelo de Balanço (PGC, 4.2.3). Ordem, nomenclatura e notas não podem ser alteradas (4.1.6).
# sign=1: saldo devedor positivo (activo); sign=-1: saldo credor positivo (capital próprio e passivo).
BALANCE_SHEET = [
    {'key': 'h_activo', 'name': 'ACTIVO', 'style': 'title'},
    {'key': 'h_anc', 'name': 'Activo não corrente', 'style': 'header'},
    {'key': 'corporeo', 'name': 'Imobilizações corpóreas', 'note': '4', 'sign': 1},
    {'key': 'incorporeo', 'name': 'Imobilizações incorpóreas', 'note': '5', 'sign': 1},
    {'key': 'subsidiarias', 'name': 'Investimentos em subsidiárias e associadas', 'note': '6', 'sign': 1},
    {'key': 'outros_fin', 'name': 'Outros activos financeiros', 'note': '7', 'sign': 1},
    {'key': 'outros_anc', 'name': 'Outros activos não correntes', 'note': '9', 'sign': 1},
    {
        'key': 't_anc',
        'name': 'TOTAL DO ACTIVO NÃO CORRENTE',
        'style': 'total',
        'sum': ['corporeo', 'incorporeo', 'subsidiarias', 'outros_fin', 'outros_anc'],
    },
    {'key': 'h_ac', 'name': 'Activo corrente', 'style': 'header'},
    {'key': 'existencias', 'name': 'Existências', 'note': '8', 'sign': 1},
    {'key': 'contas_receber', 'name': 'Contas a receber', 'note': '9', 'sign': 1},
    {'key': 'disponibilidades', 'name': 'Disponibilidades', 'note': '10', 'sign': 1},
    {'key': 'outros_ac', 'name': 'Outros activos correntes', 'note': '11', 'sign': 1},
    {
        'key': 't_ac',
        'name': 'TOTAL DO ACTIVO CORRENTE',
        'style': 'total',
        'sum': ['existencias', 'contas_receber', 'disponibilidades', 'outros_ac'],
    },
    {'key': 't_activo', 'name': 'TOTAL DO ACTIVO', 'style': 'grand_total', 'sum': ['t_anc', 't_ac']},
    {'key': 'h_cpp', 'name': 'CAPITAL PRÓPRIO E PASSIVO', 'style': 'title'},
    {'key': 'h_cp', 'name': 'Capital próprio', 'style': 'header'},
    {'key': 'capital', 'name': 'Capital', 'note': '12', 'sign': -1},
    {'key': 'reservas', 'name': 'Reservas', 'note': '13', 'sign': -1},
    {'key': 'transitados', 'name': 'Resultados transitados', 'note': '14', 'sign': -1},
    {'key': 'resultado', 'name': 'Resultados do exercício', 'sign': -1},
    {
        'key': 't_cp',
        'name': 'TOTAL DO CAPITAL PRÓPRIO',
        'style': 'total',
        'sum': ['capital', 'reservas', 'transitados', 'resultado'],
    },
    {'key': 'h_pnc', 'name': 'Passivo não corrente', 'style': 'header'},
    {'key': 'emprestimos_mlp', 'name': 'Empréstimos de médio e longo prazo', 'note': '15', 'sign': -1},
    {'key': 'impostos_diferidos', 'name': 'Impostos diferidos', 'note': '16', 'sign': -1},
    {'key': 'prov_pensoes', 'name': 'Provisões para pensões', 'note': '17', 'sign': -1},
    {'key': 'prov_outros', 'name': 'Provisões para outros riscos e encargos', 'note': '18', 'sign': -1},
    {'key': 'outros_pnc', 'name': 'Outros passivos não correntes', 'note': '19', 'sign': -1},
    {
        'key': 't_pnc',
        'name': 'TOTAL DO PASSIVO NÃO CORRENTE',
        'style': 'total',
        'sum': ['emprestimos_mlp', 'impostos_diferidos', 'prov_pensoes', 'prov_outros', 'outros_pnc'],
    },
    {'key': 'h_pc', 'name': 'Passivo corrente', 'style': 'header'},
    {'key': 'contas_pagar', 'name': 'Contas a pagar', 'note': '19', 'sign': -1},
    {'key': 'emprestimos_cp', 'name': 'Empréstimos de curto prazo', 'note': '20', 'sign': -1},
    {
        'key': 'emprestimos_mlp_corrente',
        'name': 'Parte corrente dos empréstimos a médio e longo prazo',
        'note': '15',
        'sign': -1,
    },
    {'key': 'outros_pc', 'name': 'Outros passivos correntes', 'note': '21', 'sign': -1},
    {
        'key': 't_pc',
        'name': 'TOTAL DO PASSIVO CORRENTE',
        'style': 'total',
        'sum': ['contas_pagar', 'emprestimos_cp', 'emprestimos_mlp_corrente', 'outros_pc'],
    },
    {
        'key': 't_cpp',
        'name': 'TOTAL CAPITAL PRÓPRIO E PASSIVO',
        'style': 'grand_total',
        'sum': ['t_cp', 't_pnc', 't_pc'],
    },
]

# Modelo de Demonstração de Resultados por natureza (PGC, 4.3.3). Proveitos positivos, custos negativos.
INCOME_STATEMENT = [
    {'key': 'vendas', 'name': 'Vendas', 'note': '22', 'prefixes': ['61']},
    {'key': 'servicos', 'name': 'Prestações de serviço', 'note': '23', 'prefixes': ['62']},
    {'key': 'outros_proveitos', 'name': 'Outros proveitos operacionais', 'note': '24', 'prefixes': ['63']},
    {
        'key': 'variacao_produtos',
        'name': 'Variações nos produtos acabados e produtos em vias de fabrico',
        'note': '25',
        'prefixes': ['64'],
    },
    {'key': 'trabalhos_propria', 'name': 'Trabalhos para a própria empresa', 'note': '26', 'prefixes': ['65']},
    {
        'key': 'cmvmc',
        'name': 'Custo das mercadorias vendidas e das matérias-primas e subsidiárias consumidas',
        'note': '27',
        'prefixes': ['71'],
    },
    {'key': 'pessoal', 'name': 'Custos com o pessoal', 'note': '28', 'prefixes': ['72']},
    {'key': 'amortizacoes', 'name': 'Amortizações', 'note': '29', 'prefixes': ['73']},
    {'key': 'outros_custos', 'name': 'Outros custos e perdas operacionais', 'note': '30', 'prefixes': ['74', '75']},
    {
        'key': 'r_operacionais',
        'name': 'Resultados operacionais',
        'style': 'total',
        'sum': [
            'vendas',
            'servicos',
            'outros_proveitos',
            'variacao_produtos',
            'trabalhos_propria',
            'cmvmc',
            'pessoal',
            'amortizacoes',
            'outros_custos',
        ],
    },
    {'key': 'r_financeiros', 'name': 'Resultados financeiros', 'note': '31', 'prefixes': ['66', '76']},
    {'key': 'r_filiais', 'name': 'Resultados de filiais e associadas', 'note': '32', 'prefixes': ['67', '77']},
    {'key': 'r_nao_operacionais', 'name': 'Resultados não operacionais', 'note': '33', 'prefixes': ['68', '78']},
    {
        'key': 'r_antes_impostos',
        'name': 'Resultados antes de impostos',
        'style': 'total',
        'sum': ['r_operacionais', 'r_financeiros', 'r_filiais', 'r_nao_operacionais'],
    },
    {'key': 'imposto_corrente', 'name': 'Imposto sobre o rendimento', 'note': '35', 'prefixes': ['87']},
    {
        'key': 'r_correntes',
        'name': 'Resultados líquidos das actividades correntes',
        'style': 'total',
        'sum': ['r_antes_impostos', 'imposto_corrente'],
    },
    {'key': 'r_extraordinarios', 'name': 'Resultados extraordinários', 'note': '34', 'prefixes': ['69', '79']},
    {'key': 'imposto_extraordinario', 'name': 'Imposto sobre o rendimento', 'note': '35', 'prefixes': ['87.2']},
    {
        'key': 'r_liquido',
        'name': 'Resultados líquidos do exercício',
        'style': 'grand_total',
        'sum': ['r_correntes', 'r_extraordinarios', 'imposto_extraordinario'],
    },
]


def is_transfer_account(code):
    return bool(TRANSFER_ACCOUNT_RE.match(code or ''))


def is_result_account(code):
    """Contas cujo saldo forma o resultado: classes 6 e 7 e as contas 82 a 88 da classe 8."""
    return bool(code) and (code[0] in '67' or code[:2] in ('82', '83', '84', '85', '86', '87', '88'))


def is_pl_account(code):
    """Contas de proveitos e custos que entram na DR: classes 6 e 7 e o imposto (87), sem as transferências."""
    return bool(code) and (code[0] in '67' or code[:2] == '87') and not is_transfer_account(code)


def balance_sheet_rubric(code, account_type, balance):  # noqa: PLR0911
    """Rubrica do Balanço de uma conta (ou de um terceiro numa conta de terceiros), pelo código PGC.

    As contas de terceiros classificam-se pelo sinal do saldo (princípio da não compensação): um saldo
    devedor é uma conta a receber e um saldo credor uma conta a pagar. As contas marcadas como não correntes
    vão para «Outros activos/passivos não correntes»; nos empréstimos (33), o tipo «passivo corrente»
    identifica os de curto prazo.
    """
    c1, c2 = code[:1], code[:2]
    if c1 in ('0', '9') or is_result_account(code) or c2 in ('81', '89'):
        return None
    if c2 == '11' or (c2 == '14' and not code.startswith(('14.8', '14.9'))) or code.startswith('18.1'):
        return 'corporeo'
    if c2 == '12' or code.startswith(('14.8', '18.2')):
        return 'incorporeo'
    if code.startswith(('13.1', '13.2', '19.1', '19.2')):
        return 'subsidiarias'
    if c2 in ('13', '19') or code.startswith(('14.9', '18.3')):
        return 'outros_fin'
    if c1 == '1':
        return 'outros_anc'
    if c1 == '2':
        return 'existencias'
    if c2 == '33':
        return 'emprestimos_cp' if account_type == 'liability_current' else 'emprestimos_mlp'
    if code.startswith('39.1'):
        return 'prov_pensoes'
    if c2 == '39':
        return 'prov_outros'
    if code.startswith(('37.3', '37.4')):
        return 'outros_ac'
    if code.startswith(('37.5', '37.6')):
        return 'outros_pc'
    if c1 == '3':
        if c2 == '38':
            return 'contas_receber'
        if account_type == 'asset_non_current':
            return 'outros_anc'
        if account_type == 'liability_non_current':
            return 'outros_pnc'
        return 'contas_receber' if balance >= 0 else 'contas_pagar'
    if c1 == '4':
        return 'disponibilidades'
    if c2 in ('51', '52', '53', '54'):
        return 'capital'
    if c1 == '5':
        return 'reservas'
    return None


def income_statement_rubric(code):
    if not is_pl_account(code):
        return None
    best, best_len = None, 0
    for line in INCOME_STATEMENT:
        for prefix in line.get('prefixes', ()):
            if code.startswith(prefix) and len(prefix) > best_len:
                best, best_len = line['key'], len(prefix)
    return best


class L10nAoReportsEngine(models.AbstractModel):
    _name = 'l10n_ao_reports.engine'
    _description = 'Cálculo das demonstrações financeiras PGC'

    # ------------------------------------------------------------------
    # Saldos
    # ------------------------------------------------------------------
    @api.model
    def _domain(self, company, date_from=None, date_to=None, posted_only=True):
        domain = [('company_id', 'child_of', company.id), ('display_type', 'not in', ('line_section', 'line_note'))]
        domain.append(('parent_state', '=', 'posted') if posted_only else ('parent_state', '!=', 'cancel'))
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        return domain

    @api.model
    def _account_totals(self, company, date_from=None, date_to=None, posted_only=True, by_partner=False):
        """{(conta, parceiro|None): (débito, crédito, saldo)} dos movimentos lançados no intervalo."""
        groupby = ['account_id', 'partner_id'] if by_partner else ['account_id']
        result = {}
        # O código das contas depende da empresa do ambiente.
        for row in (
            self.env['account.move.line']
            .with_company(company)
            .sudo()
            ._read_group(
                self._domain(company, date_from, date_to, posted_only),
                groupby,
                ['debit:sum', 'credit:sum', 'balance:sum'],
            )
        ):
            account = row[0]
            partner = row[1] if by_partner else None
            debit, credit, balance = row[-3:]
            result[account, partner] = (debit, credit, balance)
        return result

    @api.model
    def _fiscal_year(self, company, date):
        dates = company.compute_fiscalyear_dates(date)
        return dates['date_from'], dates['date_to']

    # ------------------------------------------------------------------
    # Balanço
    # ------------------------------------------------------------------
    @api.model
    def _balance_sheet_values(self, company, date_to, posted_only=True):
        """Valores das rubricas do Balanço à data, com o saldo na convenção contabilística (devedor > 0)."""
        fy_start, _fy_end = self._fiscal_year(company, date_to)
        values = defaultdict(float)
        per_account = defaultdict(float)
        for (account, _partner), (_debit, _credit, balance) in self._account_totals(
            company, date_to=date_to, posted_only=posted_only, by_partner=True
        ).items():
            third_party = account.account_type in ('asset_receivable', 'liability_payable')
            if third_party and not is_result_account(account.code):
                # Clientes e fornecedores: a não compensação de saldos aplica-se terceiro a terceiro.
                rubric = balance_sheet_rubric(account.code, account.account_type, balance)
                values[rubric or 'unmapped'] += balance
            else:
                per_account[account] += balance
        for account, balance in per_account.items():
            code = account.code
            if is_result_account(code) or code[:2] in ('81', '89'):
                # Resultados acumulados; o do exercício é separado abaixo.
                values['transitados'] += balance
            elif code[:1] not in ('0', '9'):
                values[balance_sheet_rubric(code, account.account_type, balance) or 'unmapped'] += balance
        # Resultado do exercício: proveitos e custos desde o início do exercício, sem as transferências.
        current = sum(
            balance
            for (account, _partner), (_debit, _credit, balance) in self._account_totals(
                company, date_from=fy_start, date_to=date_to, posted_only=posted_only
            ).items()
            if is_pl_account(account.code)
        )
        values['resultado'] += current
        values['transitados'] -= current
        return dict(values)

    # ------------------------------------------------------------------
    # Demonstração de resultados
    # ------------------------------------------------------------------
    @api.model
    def _income_statement_values(self, company, date_from, date_to, posted_only=True):
        """Valores das rubricas da DR por natureza no período (proveitos positivos, custos negativos)."""
        values = defaultdict(float)
        for (account, _partner), (_debit, _credit, balance) in self._account_totals(
            company, date_from=date_from, date_to=date_to, posted_only=posted_only
        ).items():
            rubric = income_statement_rubric(account.code)
            if rubric:
                values[rubric] -= balance
        return dict(values)

    # ------------------------------------------------------------------
    # Apresentação
    # ------------------------------------------------------------------
    @api.model
    def _build_lines(self, layout, columns, *, unit=1, hide_empty=True):
        """Linhas do modelo com os valores das colunas (N, N-1...), arredondados à grandeza.

        Os totais somam os valores já arredondados, para o mapa somar à vista.
        """
        rounded = []
        for values in columns:
            col = {}
            for line in layout:
                key = line['key']
                if 'sum' in line:
                    col[key] = sum(col.get(k, 0.0) for k in line['sum'])
                elif 'sign' in line or 'prefixes' in line:
                    amount = values.get(key, 0.0) * line.get('sign', 1)
                    col[key] = float_round(amount / unit, precision_digits=0 if unit > 1 else 2) + 0.0
            rounded.append(col)
        lines = []
        for line in layout:
            key = line['key']
            amounts = [col.get(key) for col in rounded]
            style = line.get('style', 'line')
            if style == 'line' and hide_empty and not any(amounts):
                # PGC 4.1.7: rubricas sem valor no período e no comparativo podem ser omitidas.
                continue
            lines.append(
                {
                    'key': key,
                    'name': line['name'],
                    'note': line.get('note', ''),
                    'style': style,
                    'amounts': amounts if style not in ('title', 'header') else [],
                }
            )
        return lines

    @api.model
    def _balance_sheet(self, company, date_to, *, comparative=True, unit=1, posted_only=True, hide_empty=True):
        dates = [date_to]
        if comparative:
            dates.append(self._previous_year_date(date_to))
        columns = [self._balance_sheet_values(company, d, posted_only) for d in dates]
        return {
            'lines': self._build_lines(BALANCE_SHEET, columns, unit=unit, hide_empty=hide_empty),
            'dates': dates,
            'unmapped': [col.get('unmapped', 0.0) for col in columns],
        }

    @api.model
    def _income_statement(
        self, company, date_from, date_to, *, comparative=True, unit=1, posted_only=True, hide_empty=True
    ):
        periods = [(date_from, date_to)]
        if comparative:
            periods.append((self._previous_year_date(date_from), self._previous_year_date(date_to)))
        columns = [self._income_statement_values(company, df, dt, posted_only) for df, dt in periods]
        return {
            'lines': self._build_lines(INCOME_STATEMENT, columns, unit=unit, hide_empty=hide_empty),
            'periods': periods,
        }

    @api.model
    def _previous_year_date(self, date):
        try:
            return date.replace(year=date.year - 1)
        except ValueError:  # 29 de Fevereiro
            return date.replace(year=date.year - 1, day=28)

    # ------------------------------------------------------------------
    # Balancete
    # ------------------------------------------------------------------
    @api.model
    def _trial_balance(self, company, date_from, date_to, *, max_depth=None, posted_only=True, hide_empty=True):
        """Balancete geral: saldo inicial, movimentos do período e saldo final por conta e por agregação.

        As contas de resultados começam no início do exercício; o que ficou por apurar de exercícios
        anteriores aparece numa linha à parte, para o balancete fechar.
        """
        fy_start, _fy_end = self._fiscal_year(company, date_from)
        rows = defaultdict(lambda: [0.0, 0.0, 0.0])  # conta -> [inicial, débito, crédito]
        unclosed = 0.0
        for (account, _p), (_d, _c, balance) in self._account_totals(
            company, date_to=date_from - timedelta(days=1), posted_only=posted_only
        ).items():
            rows[account][0] += balance
        for (account, _p), (_d, _c, balance) in self._account_totals(
            company, date_to=fy_start - timedelta(days=1), posted_only=posted_only
        ).items():
            if is_result_account(account.code):
                rows[account][0] -= balance
                unclosed += balance
        for (account, _p), (debit, credit, _b) in self._account_totals(
            company, date_from=date_from, date_to=date_to, posted_only=posted_only
        ).items():
            rows[account][1] += debit
            rows[account][2] += credit

        aggregates = {}  # código -> linha; a classe (1 dígito) e as contas-mãe agregam as contas de movimento
        for account, (initial, debit, credit) in rows.items():
            chain = []
            node = account
            while node:
                chain.insert(0, (node.code, node.name))
                node = node.parent_id
            chain.insert(0, (account.code[:1], CLASS_NAMES.get(account.code[:1], '')))
            for depth, (code, name) in enumerate(chain):
                agg = aggregates.setdefault(code, {'code': code, 'name': name, 'depth': depth, 'values': [0.0] * 3})
                agg['values'][0] += initial
                agg['values'][1] += debit
                agg['values'][2] += credit
        lines = []
        totals = [0.0] * 5
        for code in sorted(aggregates, key=self._code_sort_key):
            agg = aggregates[code]
            if max_depth is not None and agg['depth'] > max_depth:
                continue
            initial, debit, credit = agg['values']
            final = initial + debit - credit
            amounts = [initial, debit, credit, max(final, 0.0), max(-final, 0.0)]
            if hide_empty and not any(company.currency_id.round(a) for a in amounts):
                continue
            lines.append({'code': agg['code'], 'name': agg['name'], 'depth': agg['depth'], 'amounts': amounts})
            if agg['depth'] == 0:
                for i, amount in enumerate(amounts):
                    totals[i] += amount
        if not company.currency_id.is_zero(unclosed):
            amounts = [unclosed, 0.0, 0.0, max(unclosed, 0.0), max(-unclosed, 0.0)]
            lines.append(
                {
                    'code': '',
                    'name': 'Resultados de exercícios anteriores por apurar',
                    'depth': 0,
                    'amounts': amounts,
                    'virtual': True,
                }
            )
            for i, amount in enumerate(amounts):
                totals[i] += amount
        return {'lines': lines, 'totals': totals}

    @api.model
    def _code_sort_key(self, code):
        # Códigos com letras (contas criadas à mão) ordenam-se depois dos numéricos do mesmo nível.
        return [(0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.split(r'[.]', code or '')]
