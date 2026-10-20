# Análise de conformidade: Contabilidade (PGC Angola) e Odoo 20.0 Community

**Fonte legal:** Decreto n.º 82/01, de 16 de Novembro, que aprova o Plano Geral de Contabilidade (PGC). O texto foi extraído do PDF em `decretos/`.
**Código analisado:** `/Users/vadao/Projectos_Next/odoo/odoo/addons` (Odoo 20.0 Community).
**Legenda:** ✅ suportado nativamente · 🟡 suportado com configuração ou dados novos · 🔴 falta funcionalidade, é preciso desenvolver.

---

## 1. Estrutura do PGC

### 1.1 Classes

| Classe | Designação | Uso |
|---|---|---|
| 0 | Contas de Ordem | Facultativo (§5.2.1) |
| 1 | Meios Fixos e Investimentos | Obrigatório |
| 2 | Existências | Obrigatório |
| 3 | Terceiros | Obrigatório |
| 4 | Meios Monetários | Obrigatório |
| 5 | Capital e Reservas | Obrigatório |
| 6 | Proveitos e Ganhos por Natureza | Obrigatório |
| 7 | Custos e Perdas por Natureza | Obrigatório |
| 8 | Resultados | Obrigatório |
| 9 | Contabilidade Analítica | Facultativo (§5.2.3) |

Nota: o PGC de 2001 **inverteu a ordem das classes do plano antigo** (§1.2.7). No plano antigo, a classe 1 era Meios Monetários e a classe 4 Meios Fixos. O plano moçambicano (`l10n_mz`) segue essa ordem antiga, o que é relevante para a secção 3.

### 1.2 Codificação

- A codificação é hierárquica e pontuada: classe (1 dígito) → conta (2 dígitos, ex. `31`) → subconta (`31.1`) → `31.1.2` → `31.1.2.1`. Na prática há até 5 níveis.
- A disposição, a nomenclatura e os códigos das contas das classes 1 a 8 **não devem ser alterados**. São permitidos desenvolvimentos de subcontas e o preenchimento das "linhas em branco", isto é, das contas marcadas com `……` (§5.2.2).
- Cada conta de proveitos ou custos tem uma subconta `x.9 Transferência para resultados`. O apuramento faz-se por transferência para as contas 82 a 86 da classe 8.

### 1.3 Contas principais (2 dígitos)

| Classe | Contas |
|---|---|
| 1 | 11 Imobilizações corpóreas · 12 Imobilizações incorpóreas · 13 Investimentos financeiros · 14 Imobilizações em curso · 15–17 (livres) · 18 Amortizações acumuladas · 19 Provisões p/ investimentos financeiros |
| 2 | 21 Compras · 22 Matérias-primas, subsidiárias e de consumo · 23 Produtos e trabalhos em curso · 24 Produtos acabados e intermédios · 25 Subprodutos, desperdícios, resíduos e refugos · 26 Mercadorias · 27 Matérias-primas, mercadorias e outros materiais em trânsito · 28 Adiantamentos por conta de compras · 29 Provisão p/ depreciação de existências |
| 3 | 31 Clientes · 32 Fornecedores · 33 Empréstimos · 34 Estado · 35 Entidades participantes e participadas · 36 Pessoal · 37 Outros valores a receber e a pagar · 38 Provisões p/ cobranças duvidosas · 39 Provisões p/ outros riscos e encargos |
| 4 | 41 Títulos negociáveis · 42 Depósitos a prazo · 43 Depósitos à ordem · 44 Outros depósitos · 45 Caixa · 46–47 (livres) · 48 Conta transitória · 49 Provisões p/ aplicações de tesouraria |
| 5 | 51 Capital · 52 Acções/quotas próprias · 53 Prémios de emissão · 54 Prestações suplementares · 55 Reservas legais · 56 Reservas de reavaliação · 57 Reservas c/ fins especiais · 58 Reservas livres |
| 6 | 61 Vendas · 62 Prestações de serviço · 63 Outros proveitos operacionais · 64 Variação nos inventários de produtos acabados e em vias de fabrico · 65 Trabalhos para a própria empresa · 66 Proveitos e ganhos financeiros gerais · 67 … em filiais e associadas · 68 Outros proveitos não operacionais · 69 Proveitos e ganhos extraordinários |
| 7 | 71 Custo das mercadorias vendidas e matérias consumidas · 72 Custos com o pessoal · 73 Amortizações do exercício · 74 (livre) · 75 Outros custos e perdas operacionais (75.2 FST, 75.3 Impostos…) · 76 Custos e perdas financeiros gerais (76.2 Dif. câmbio) · 77 … em filiais e associadas · 78 Outros custos e perdas não operacionais · 79 Custos e perdas extraordinários |
| 8 | 81 Resultados transitados · 82 Resultados operacionais · 83 Resultados financeiros · 84 Resultados em filiais e associadas · 85 Resultados não operacionais · 86 Resultados extraordinários · 87 Imposto sobre os lucros · 88 Resultado líquido do exercício · 89 Dividendos antecipados |

Subcontas fiscais relevantes (conta 34 Estado): 34.1 Imposto sobre os lucros · 34.2 Imposto de produção e consumo · 34.3 Imposto de rendimento de trabalho · 34.4 Imposto de circulação · 34.8 Subsídios a preços · 34.9 Outros impostos. **O PGC de 2001 é anterior ao IVA angolano e não tem conta de IVA.** As subcontas de IVA (34.5.x) e de Imposto de Selo, bem como a sua estrutura, têm de vir de **fonte externa necessária** (Código do IVA, Lei 7/19, e orientações da AGT ou da OCPCA).

### 1.4 Demonstrações financeiras obrigatórias (§4.1.5)

| Demonstração | Obrigatoriedade | Estrutura |
|---|---|---|
| Balanço | Obrigatório | Activo não corrente / corrente; Capital próprio; Passivo não corrente / corrente. Cada linha tem uma referência a uma nota (4–21). |
| Demonstração de Resultados **por natureza** | Obrigatória, salvo se for substituída pela DR por funções | Vendas (22) … Resultados operacionais; Resultados financeiros (31), de filiais (32), não operacionais (33); Resultados antes de impostos; Imposto (35); Resultados líquidos das actividades correntes; Resultados extraordinários (34); Imposto; Resultado líquido |
| DR **por funções** | Alternativa. É recomendada a quem use contabilidade analítica | Vendas, Custo das vendas, Margem bruta, Custos de distribuição e administrativos… e ainda operações em descontinuação e efeito de alterações de políticas |
| Demonstração de Fluxos de Caixa | Obrigatória, pelo método directo ou indirecto. **Ficou temporariamente suspensa** (§1.4.1), mas é recomendada | Actividades operacionais / de investimento / de financiamento |
| Notas às contas | Obrigatórias | Modelo fixo com 47 notas numeradas. A numeração mantém-se mesmo quando há omissões (§4.1.7–4.1.8). Materialidade: 10% do Activo e 5% dos proveitos operacionais. |
| Demonstração de alterações nos capitais próprios | Pode ser incluída nas Notas | — |

Regras de apresentação com impacto no software:
- Identificação da entidade, com a sigla da forma jurídica, do período e da **moeda e grandeza**. O mínimo é o **milhar de Kwanzas** (§4.1.4).
- É obrigatório apresentar os comparativos do exercício N-1.
- **Não é permitido alterar a disposição, a nomenclatura nem o número de ordem** das rubricas (§4.1.6). As linhas sem valor podem ser omitidas se também não tiverem valor em N-1.

### 1.5 Princípios e critérios relevantes para o software

- **Exercício:** 12 meses, normalmente terminando a 31/12. Pode excepcionalmente terminar noutra data ou ser mais curto (§4.1.3).
- **Moeda:** o relato obrigatório é em Kwanza (AOA). É permitido um relato paralelo noutra moeda, por exemplo USD.
- **Câmbio:** as diferenças favoráveis não realizadas são diferidas (conta 37.6.4). Isto difere do comportamento do Odoo, que lança as diferenças de câmbio realizadas e não realizadas directamente em resultados.
- **Existências:** custo específico; FIFO ou custo médio como preferenciais; LIFO como alternativa (§3.7). Mensuração ao menor entre o custo e o valor realizável líquido (provisão 29).
- **Amortizações:** sistemáticas pela vida útil, por **quotas constantes** salvo justificação. Trespasses e incorpóreos até 5 anos. As amortizações extraordinárias não são revertidas.
- **Princípios gerais:** acréscimo, consistência, materialidade, não compensação de saldos e comparabilidade.
- **Temas excluídos temporariamente** (§1.4.2): locações, impostos diferidos, benefícios de reforma, consolidação e conversão de operações estrangeiras.

---

## 2. Mapeamento para o Odoo 20 Community

### 2.1 Mecanismo de plano de contas

- **Não existe `l10n_ao`** nos addons. O país `base.ao` e a moeda `AOA` existem, com símbolo "Kz" e arredondamento 0,01, mas **a moeda está inactiva por omissão** (`odoo/addons/base/data/res_currency_data.xml:544`). Sem localização, o Odoo atribui o `generic_coa`.
- O plano de contas é definido em Python com o decorador `@template` (`addons/account/models/chart_template.py`). Os ficheiros CSV ficam em `data/template/<modelo>-<código>.csv`. Exemplo: `addons/l10n_mz/models/template_mz.py`, que define `code_digits` e os parâmetros `res.company`: prefixos de banco, caixa e transferências, contas de câmbio, impostos por omissão e contas a receber, a pagar, de receita e de gasto.
- **No Odoo 20, `account.account` é hierárquico** (`parent_id`, `addons/account/models/account_account.py:133`). Deixou de existir `account.group`. Nos CSV, as contas agregadoras são inseridas como contas `active=False`; veja-se `l10n_mz_account_group_*` em `account.account-mz.csv`, com as colunas `id,parent_id,active,name,code,account_type,reconcile,non_trade`.
- **Códigos pontuados** como `31.1.2.1` são aceites pela validação dos códigos (`ACCOUNT_CODE_REGEX = ^[A-Za-z0-9.-]+$`). A normalização faz `f'{code:<0{code_digits}}'`, ou seja, acrescenta zeros à direita. Com `code_digits='1'` os códigos ficam intactos (testado). Com 6, a conta `43` passaria a `430000`.

### 2.2 Tipos de conta (`account_type`) por classe PGC

| PGC | `account_type` proposto |
|---|---|
| 11, 12, 14 | `asset_fixed` (11, 14.1–14.2) / `asset_non_current` (12, 14.7–14.9) |
| 13, 19 | `asset_non_current` |
| 18 | `asset_fixed` (18.1) / `asset_non_current` (18.2–18.3), como contrapartida credora |
| 21–29 | `asset_current` (28: `asset_prepayments`) |
| 31.1/31.2 | `asset_receivable` (reconcile) · 31.8 `asset_receivable` · 31.9 `liability_current` |
| 32.1/32.2 | `liability_payable` · 32.9 `asset_prepayments` / `asset_current` |
| 33 | `liability_non_current` / `liability_current` (curto prazo) |
| 34 | `liability_current` (IVA dedutível: `asset_current`) |
| 35, 37 | `asset_receivable`/`liability_payable` com `non_trade=True`; 37.3/37.4 `asset_current`; 37.5/37.6 `liability_current` |
| 36 | `liability_payable` (non_trade) / `asset_receivable` |
| 38 | `asset_receivable` (contrapartida credora) / 39 `liability_non_current` |
| 41, 42, 49 | `asset_current` |
| 43, 44, 45 | `asset_cash` |
| 48 | `asset_current` (transferências internas) |
| 51–58 | `equity` |
| 61, 62 | `income` · 63–65 `income_other` · 66–69 `income_other` |
| 71 | `expense_direct_cost` · 72, 75 `expense` · 73 `expense_depreciation` · 76–79 `expense_other` |
| 81, 89 | `equity` · 82–86, 88 `equity_unaffected` (só uma conta pode ter este tipo, por exemplo a 88) · 87 `expense` |
| 0 | `off_balance` |
| 9 | Não criar contas. Usar a contabilidade analítica do Odoo (`account.analytic.*`). |

### 2.3 Lacunas

| Necessidade PGC | Estado | Onde / observação |
|---|---|---|
| Plano de contas PGC | 🟡 | Novo `l10n_ao`, só com dados (mecanismo em `account/models/chart_template.py`) |
| Hierarquia de 5 níveis e códigos pontuados | ✅ | `account_account.py:17,133`. Usar `code_digits='1'` |
| Moeda AOA | 🟡 | Activar `base.AOA`. O `l10n_ao` pode definir `currency_id` na empresa |
| Exercício fiscal 31/12 ou outra data | ✅ | `res.company.fiscalyear_last_day/month` (`account/models/company.py:77`) |
| Bloqueio de períodos | ✅ | `fiscalyear_lock_date`, `hard_lock_date` (`company.py:79-100`) |
| Grupos de imposto, impostos e posições fiscais | 🟡 | CSV `account.tax.group-ao.csv`, `account.tax-ao.csv`, `account.fiscal.position-ao.csv`. **Taxas: fonte externa necessária** |
| Declaração periódica de IVA | 🟡 | O modelo `account.report` com `root_report_id=account.generic_tax_report` existe em Community (`account/data/account_reports_data.xml`; exemplo em `l10n_mz/data/tax_report.xml`). **A visualização interactiva é Enterprise** (`account_reports`) |
| Retenções na fonte (II, IRT, Imposto Predial…) | 🟡 | O módulo Community `addons/l10n_account_withholding_tax` existe e trata retenções em facturas e pagamentos. Taxas: fonte externa |
| Balanço PGC | 🔴 | Community **só traz relatórios de impostos genéricos**. Não há Balanço/P&L e o motor de cálculo e apresentação está em `account_reports` (Enterprise). É preciso um módulo próprio |
| DR por natureza / por funções | 🔴 | Idem. A DR por funções exige uma dimensão analítica de funções (custo das vendas, distribuição, administrativos) |
| Demonstração de Fluxos de Caixa (directo/indirecto) | 🔴 | Não existe em Community. O método directo exige classificar os movimentos de caixa por actividade (tags de conta ou de movimento) |
| Notas às contas (47 notas) | 🔴 | Não existe. Mapas de movimentos do imobilizado (notas 4–5) dependem de um módulo de activos |
| Valores em milhares de Kz + comparativo N-1 | 🔴 | Tem de ser implementado no módulo de relatórios |
| Encerramento do exercício (transferência x.9 → 82–86 → 88 → 81) | 🔴 | Em Community, o resultado é calculado virtualmente pela conta `equity_unaffected`. Não há lançamentos de apuramento. É preciso um assistente de apuramento PGC |
| Gestão de imobilizado e amortizações (quotas constantes) | 🔴 | `account_asset` é Enterprise. Não existe em Community |
| Existências FIFO / custo médio | ✅ | `stock_account` (`cost_method`: standard, average, fifo; `stock_account/models/product.py:21`) |
| Existências LIFO | 🔴 | Não suportado. É método alternativo, por isso é aceitável não o implementar |
| Diferimento das diferenças de câmbio favoráveis não realizadas (37.6.4) | 🔴 | O Odoo reconhece as diferenças directamente em resultados. Pode configurar-se a conta de ganhos de câmbio para 37.6.4, mas isso também afecta as diferenças realizadas. Requer desenvolvimento |
| Contas de ordem (classe 0) | ✅ | `account_type=off_balance` |
| Contabilidade analítica (classe 9) | ✅ | Planos analíticos nativos |
| SAF-T (AO) | 🔴 | Não faz parte do PGC, mas é exigido pela AGT. Avaliar à parte (o `l10n_pt` não traz SAF-T em Community) |

---

## 3. Proposta de módulos

### 3.1 `l10n_ao`: Angola, Contabilidade (só dados, LGPL)

```
l10n_ao/
├── __manifest__.py        # depends: account (+ l10n_account_withholding_tax opcional); countries: ['ao']; auto_install: ['account']
├── models/template_ao.py  # @template('ao') e @template('ao','res.company')
├── data/template/
│   ├── account.account-ao.csv          # id,parent_id,active,name,code,account_type,reconcile,non_trade,name@pt_AO
│   ├── account.tax.group-ao.csv
│   ├── account.tax-ao.csv
│   └── account.fiscal.position-ao.csv
├── data/tax_report.xml     # account.report filho de generic_tax_report (modelo de declaração de IVA da AGT)
├── demo/demo_company.xml
└── i18n/pt_AO.po
```

Parâmetros de `template_ao.py`:
- `code_digits: '1'`, para manter os códigos pontuados.
- `cash_account_code_prefix: '45.1'`, `bank_account_code_prefix: '43.1'` (depósitos à ordem em moeda nacional), `transfer_account_code_prefix: '48'`.
- `receivable_account_id` → 31.1.2.1 (clientes correntes, não grupo, nacionais). `payable_account_id` → 32.1.2.1.
- `income_account_id` → 61.3 (mercadorias) ou 62.1. `expense_account_id` → 71.x. `account_stock_valuation_id` → 26.
- `income_currency_exchange_account_id` → 66.2. `expense_currency_exchange_account_id` → 76.2.
- Descontos de pronto pagamento: ganho 66.3, perda 76.3.
- `account_default_pos_receivable_account_id` → subconta de 31.1.
- `currency_id: 'base.AOA'`. É preciso activar a moeda.

Conteúdo do `account.account-ao.csv`:
- As contas de classe e de 2 dígitos ficam como agregadoras (`active=False`).
- As subcontas de 3 a 5 níveis transcrevem a lista §5.3 do PGC (cerca de 400 a 500 linhas).
- Contas fiscais 34.x a acrescentar com base em fonte externa: 34.5 IVA (suportado, dedutível, liquidado, regularizações, apuramento, a pagar, a recuperar), Imposto de Selo e retenções de Imposto Industrial e IRT. **Fonte externa necessária.**

Impostos (`account.tax-ao.csv`). **Todas as taxas e regimes são fonte externa necessária.**
- IVA à taxa normal, à taxa reduzida, isento e não sujeito, com variantes de liquidação e de dedução (bens, imobilizado, serviços, importação). Incluir o regime simplificado e o de caixa, se aplicáveis.
- Imposto de Selo, com as verbas aplicáveis a recibos e operações (`amount_type` percent ou fixed).
- Retenções: Imposto Industrial sobre serviços, IRT e Imposto Predial. Implementar com valores negativos ou com `l10n_account_withholding_tax`.
- As tags de cada linha de repartição ligam-se às linhas do `tax_report.xml`.

Posições fiscais: regime geral, regime simplificado ou isento, exportação/importação e entidades isentas. **A confirmar externamente.**

### 3.2 `l10n_ao_reports`: demonstrações financeiras PGC (Community)

Como o motor `account_reports` é Enterprise, há duas opções:

- **A, recomendada para Community:** módulo próprio com:
  - modelo `l10n_ao.fs.line` (linha de demonstração com nº de ordem, nº de nota e lista de prefixos de conta com sinal), definido em XML;
  - assistente com período, comparativo N-1 e grandeza (unidades ou milhares) que calcula os saldos via `account.move.line._read_group`;
  - relatórios QWeb PDF e exportação XLSX para o Balanço, a DR por natureza, a DR por funções e a DFC (directa e indirecta).
  
  A DR por funções e a DFC directa precisam de etiquetas analíticas ou de `account.account.tag`, por exemplo "Função: Distribuição" ou "DFC: Recebimentos de clientes".
- **B, se houver licença Enterprise:** definir os registos `account.report` com o motor `account_codes`. Exemplo: `formula = -5 - 6`, prefixos de classes, à semelhança dos módulos `l10n_xx_reports`. O esforço é menor, mas cria dependência do Enterprise.

Componentes adicionais:
- **Assistente de apuramento de resultados:** lançamentos x.9 → 82–86 → 88 e transferência da 88 para a 81 no exercício seguinte.
- **Notas às contas:** modelo de 47 notas, com mapas automáticos onde possível (existências, terceiros, disponibilidades, capital) e texto livre nas restantes.
- **`l10n_ao_asset`:** módulo separado de imobilizado e amortizações por quotas constantes, para as notas 4 e 5. Em Community é preciso um desenvolvimento próprio ou um módulo OCA (`account_asset_management`).

Mapeamento base do Balanço (por prefixos):
- Imobilizado corpóreo: 11 + 14.1/14.2/14.7 − 18.1.
- Imobilizado incorpóreo: 12 + 14.8 − 18.2.
- Investimentos em subsidiárias e associadas: 13.1 + 13.2 − 19.1/19.2.
- Outros activos financeiros: 13.3–13.9 − 19.3+.
- Existências: 21–28 − 29.
- Contas a receber: 31 + saldos devedores de 32/34/35/36/37 − 38.
- Disponibilidades: 41–45 − 49.
- Capital: 51−52. Reservas: 53–58. Resultados transitados: 81. Resultado do exercício: 88 (ou o resultado virtual).
- Empréstimos: 33, separados entre médio/longo prazo e curto prazo.
- Provisões: 39.1 (pensões) e 39.2–39.9.
- Contas a pagar: 32 + saldos credores de 31/34/35/36/37.

Para os saldos de sinal variável, o módulo tem de calcular cada conta individualmente e só depois agregar. É o equivalente aos sufixos `C`/`D` do motor `account_codes` do Enterprise.

### 3.3 Reutilização do `l10n_mz`

| Elemento | Reutilizável? |
|---|---|
| Esqueleto do módulo (manifest, `template_mz.py`, formato dos CSV, demo, i18n `pt.po`) | ✅ Copiar e adaptar |
| Estrutura das contas de IVA (4431 suportado, 4432 dedutível, 4433 liquidado, 4434 regularizações) e estrutura das variantes de imposto (16% bens, imobilizado, serviços, importação; 45 linhas) | 🟡 Boa referência para o desenho dos 34.5.x e dos impostos AO. As taxas não servem |
| Estrutura do `tax_report.xml` (quadros e campos com o motor `tax_tags`) | 🟡 O padrão serve. O conteúdo tem de seguir o modelo de declaração da AGT |
| Códigos e plano de contas | 🔴 **Não reutilizável.** O `l10n_mz` segue o PGC-NIRF moçambicano: 1 Meios monetários, 2 Inventários, 3 Investimentos de capital, 4 Contas a receber/pagar, 6 Gastos, 7 Rendimentos. Ou seja, a ordem antiga (1/4 trocadas face ao PGC AO) e **6 e 7 invertidas** (no PGC AO a classe 6 são proveitos e a 7 custos). Os nomes estão em inglês. Apenas algumas designações de 2 dígitos são conceptualmente semelhantes |
| `l10n_pt` (SNC) | 🟡 Referência para `name@pt`, `round_globally` e para o override de diários de caixa e banco. O plano SNC não é compatível |
| `l10n_gw` / `l10n_syscohada` | 🔴 Não aplicável, por ser SYSCOHADA. Serve só como exemplo de vários templates num módulo (`gw` e `gw_syscebnl`), útil se se quiser um template para PME |

Em suma: aproveita-se do `l10n_mz` a mecânica e o desenho fiscal, não o plano de contas. O CSV do PGC AO tem de ser transcrito do zero a partir da §5.3 do Decreto 82/01.

---

## 4. Riscos e pontos a confirmar

1. O PGC de 2001 não tem IVA nem SAF-T. As subcontas 34.x actuais e as taxas de IVA, Imposto de Selo, II e IRT exigem **fonte externa** (legislação fiscal em vigor e orientações da AGT).
2. A DFC está suspensa pelo §1.4.1. Convém confirmar se essa suspensão continua em vigor. Pode ser implementada numa fase 2.
3. Verificar se existem actualizações posteriores ao PGC (por exemplo as normas da OCPCA e as alterações ao Decreto 82/01) antes de fixar o CSV.
4. Em Community, o resultado do exercício é virtual (`equity_unaffected`). O apuramento formal pela classe 8 é um requisito de prática angolana a validar com os contabilistas.
