# Fase 1: Kututa Kwanza (`l10n_ao`)

**Estado:** concluída e revista a 2026-10-20. Os testes (`make test m=l10n_ao`) passam: 23 testes, 0 falhas.

## O que o módulo instala

**Plano de contas: 743 contas, com o PGC (Decreto n.º 82/01, §5.3) completo**
- Extraído do PDF oficial por `tools/gen_pgc_chart.py` (`tools/data/pgc_decreto_82_01.csv`) e **conferido conta a conta contra as páginas 86–119 do decreto** por dois revisores independentes.
- **Lapsos de impressão do próprio decreto**, corrigidos em `tools/data/pgc_correcoes.csv` (cada correcção tem a justificação):
  - as subcontas de 18.1 vêm impressas como «18.1…18.9» e colidiam com os cabeçalhos 18.2 e 18.3: recodificadas para 18.1.1–18.1.9;
  - códigos repetidos no decreto: 38.1.3.1/38.1.3.2 (impressos como 38.1.2.x), 56.2.2 Realização (impresso 56.2.1), 76.6.1.4 Fundos (impresso 76.6.1.2);
  - gralhas: 68.1.2 «Cobranças Duvidosa», 88.1 «Resultado operacionais»;
  - nomes repetidos no decreto, distinguidos: 14.1/14.2 «Obra em curso», 75.2.14/75.2.26 «Conservação e reparação»;
  - contas-modelo não criadas: 56.1.1/56.1.2 «Decreto-lei nº ___», bloco 81.2 «Ano ___».
- Os separadores do decreto («Clientes – correntes») são preservados.
- As contas com subcontas são agregadoras (inactivas); as restantes são de movimento.
- Os códigos pontuados ficam intactos (`31.1.2.1`).
- **Não são criadas** as subcontas-modelo do decreto («Banco ___», «Caixa ___», «Entidade», «Ano ___»). As contas bancárias e de caixa são criadas pelos diários em `43.1.x` e `45.1.x`.

**Extensões ao PGC** (`tools/data/pgc_extensoes.csv`), porque o decreto de 2001 não as prevê:

| Contas | Uso |
|---|---|
| 34.2.1–34.2.8 | IVA: suportado, liquidado, dedutível, cativo, regularizações, apuramento, a pagar, a recuperar. Segue a convenção do secPed: o IVA substitui o Imposto de Produção e Consumo na 34.2. |
| 34.1.1, 34.1.2 | Imposto Industrial: estimativa e retenções sofridas (6,5%) |
| 34.3.1, 34.9.1–34.9.3, 34.9.9 | IRT, INSS, retenções a entregar, Imposto de Selo |
| 48.1–48.4 | Valores em trânsito, suspenso e transferências internas (contas técnicas do Odoo) |
| 43.1.xx / 43.2.xx / 45.1.xx | Criadas pelos diários: bancos em Kz, bancos em moeda estrangeira, caixas (até 99 de cada) |
| 31.1.2.9 | Clientes do POS |
| 68.11.9, 78.11.9 | Diferenças de caixa |
| 88.8 | Resultado do exercício em curso (conta *equity_unaffected* do Odoo) |

**Impostos (21)**

| Tipo | Impostos |
|---|---|
| Vendas | IVA 14% (NOR), 7% (INT), 5% (RED), 1% Cabinda; isentos com motivo AGT (M21 ensino, M22 saúde, M10, M11, M13, M14, M18, M30 exportação); não sujeitos (M00, M02, M04) |
| Compras | IVA dedutível 14/7/5%, não dedutível, autoliquidação (serviços do estrangeiro), isento |

Os campos AGT estão em `account.tax`: `l10n_ao_tax_type`, `l10n_ao_tax_code`, `l10n_ao_tax_region` e `l10n_ao_exemption_id`. Regras validadas ao gravar: um imposto de IVA tem código; ISE/NS exigem motivo e taxa 0; um imposto com taxa não pode ter motivo; o motivo tem de ser do mesmo imposto. Os impostos isentos levam a **menção legal** (`invoice_legal_notes`) impressa na factura.

**Posições fiscais:** Regime nacional (automática), Cabinda (manual), Exportação/Estrangeiro (automática). Os impostos são universais; só os substitutos (1% Cabinda, M30 exportação) estão restritos à sua posição, por isso uma posição fiscal nunca apaga um imposto de uma linha. A autoliquidação é de selecção manual (nas importações de bens o IVA liquida-se na alfândega).

**Declaração periódica de IVA:** operações activas, operações passivas e apuramento.

**Tabelas AGT** (geradas por `tools/gen_agt_tables.py` a partir dos anexos oficiais):
- 57 motivos de isenção (38 de IVA, 3 de IS, 16 de IEC);
- 574 CAE;
- 108 verbas de Imposto de Selo;
- 117 taxas de IEC.

**Outros**
- Kwanza (AOA) activado.
- Regime de IVA e CAE principal na ficha da empresa.
- Validação do NIF ligada ao Odoo (`check_vat_ao` / `format_vat_ao`): 10 dígitos, BI ou 999999999 (consumidor final).

## Limitações conhecidas
- **A declaração de IVA não tem motor de cálculo na Community** (o motor dos `account.report` é do Enterprise). As etiquetas são aplicadas correctamente nas linhas; a listagem fica para o `l10n_ao_reports` (Fase 3), que lerá as etiquetas por período.
- **Actualizar o módulo num cliente já instalado** (`-u l10n_ao`) só acrescenta contas e impostos novos; não renomeia contas nem altera impostos ou predefinições da empresa já existentes (política do Odoo). Alterações a dados existentes exigem um script de migração.

## Revisão da Fase 1 (2026-10-20)
Três revisões independentes (plano de contas págs. 86–102, págs. 103–119, regras de negócio e infra-estrutura) mais testes funcionais na base de demonstração. Problemas encontrados e corrigidos:

| Gravidade | Problema | Correcção |
|---|---|---|
| Alta | Bloco 18 do plano errado (lapso do decreto) e 4 contas em falta | `pgc_correcoes.csv` |
| Alta | As posições fiscais Cabinda/Exportação apagavam os impostos não associados (isenções, compras) | Impostos universais; testes com produtos |
| Alta | Conta de custo por defeito 21.2 (activo): facturas de fornecedor iam para existências | 75.2.39 (custos) e vendas 62.1.1 |
| Média | Prefixo bancário permitia só 9 bancos; moeda estrangeira em 43.1 | `43.1.00` (99) e 43.2 para moeda estrangeira |
| Média | Modelo «Bank Fees» apontava para 72.1 (salários) | 76.7 Serviços bancários |
| Média | Validação do NIF não estava ligada ao Odoo | `check_vat_ao` |
| Média | Restrição das isenções com lacunas | Regras completas, limitadas a AO |
| Média | Produção: segredos na linha de comando, sem healthcheck, websocket sem porta | `PG*`, healthcheck, `gevent_port`, portas locais, `docs/producao.md` |
| Baixa | 42/44/45.2 como `asset_cash` (criaria diários automáticos) | `asset_current`; 45.2 reconciliável |
| Baixa | `currency_id` redundante no template; `non_trade` sem efeito | Removidos |

## ⚠️ A validar com um contabilista antes de produção
1. **As taxas de IVA de 7% e de 1% (Cabinda) e o código AGT da taxa de Cabinda** (usámos `OUT` + região `AO-CAB`). Só os 14% e os 5% foram confirmados em mais de uma fonte.
2. **A numeração das extensões ao PGC**, sobretudo as contas de IVA em 34.2.x.
2b. **As correcções aos lapsos do decreto** (`tools/data/pgc_correcoes.csv`), em especial a recodificação do bloco 18.
3. **A estrutura da declaração periódica de IVA** contra o modelo oficial da AGT.
4. **As contas por defeito:** vendas 62.1.1 (serviços), custos 75.2.39 (FST), clientes 31.1.2.1, fornecedores 32.1.2.1. As mercadorias (61/21/26) configuram-se nas categorias de produtos.
5. **M30 em serviços a não residentes** (hoje a posição Exportação aplica M30 a bens e serviços).
6. **A taxa de Cabinda** (código AGT `OUT` + região `AO-CAB`; aplicada a bens e serviços).

## Fica para fases seguintes
| Tema | Fase |
|---|---|
| Retenções na fonte (Imposto Industrial 6,5%, IVA cativo, Imposto de Selo do recibo): retenção no pagamento, a avaliar com `l10n_account_withholding_tax` | 2 |
| Câmbio automático do BNA | 2 ou 3 |
| Províncias de Angola (para aplicar Cabinda automaticamente) e feriados nacionais | 4 (RH) |
| Demonstrações financeiras PGC (`l10n_ao_reports`) | 3 |

## Regenerar os dados
```bash
.venv/bin/python -I tools/gen_pgc_chart.py "decretos/Dec-2001-82-PGC-PLANO GERAL CONTABILIDADE.pdf" tools/data/pgc_decreto_82_01.csv
.venv/bin/python -I tools/build_l10n_ao_chart.py
.venv/bin/python -I tools/gen_agt_tables.py
```
