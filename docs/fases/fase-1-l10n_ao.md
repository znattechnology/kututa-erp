# Fase 1: Kututa Kwanza (`l10n_ao`)

**Estado:** concluída a 2026-10-20. Os testes (`make test m=l10n_ao`) passam: 11 testes, 0 falhas.

## O que o módulo instala

**Plano de contas: 738 contas, com o PGC (Decreto n.º 82/01, §5.3) completo**
- Extraído do PDF oficial por `tools/gen_pgc_chart.py` e revisto: `tools/data/pgc_decreto_82_01.csv`.
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
| 31.1.2.9 | Clientes do POS |
| 68.11.9, 78.11.9 | Diferenças de caixa |
| 88.8 | Resultado do exercício em curso (conta *equity_unaffected* do Odoo) |

**Impostos (21)**

| Tipo | Impostos |
|---|---|
| Vendas | IVA 14% (NOR), 7% (INT), 5% (RED), 1% Cabinda; isentos com motivo AGT (M21 ensino, M22 saúde, M10, M11, M13, M14, M18, M30 exportação); não sujeitos (M00, M02, M04) |
| Compras | IVA dedutível 14/7/5%, não dedutível, autoliquidação (serviços do estrangeiro), isento |

Os campos AGT estão em `account.tax`: `l10n_ao_tax_type`, `l10n_ao_tax_code`, `l10n_ao_tax_region` e `l10n_ao_exemption_id`. Um motivo de isenção é obrigatório quando o imposto é ISE ou NS.

**Posições fiscais:** Regime nacional (automática), Cabinda (manual), Exportação/Estrangeiro (automática).

**Declaração periódica de IVA:** operações activas, operações passivas e apuramento.

**Tabelas AGT** (geradas por `tools/gen_agt_tables.py` a partir dos anexos oficiais):
- 57 motivos de isenção (38 de IVA, 3 de IS, 16 de IEC);
- 574 CAE;
- 108 verbas de Imposto de Selo;
- 117 taxas de IEC.

**Outros**
- Kwanza (AOA) activado.
- Regime de IVA e CAE principal na ficha da empresa.
- Validação do NIF (10 dígitos, BI ou 999999999).

## ⚠️ A validar com um contabilista antes de produção
1. **As taxas de IVA de 7% e de 1% (Cabinda) e o código AGT da taxa de Cabinda** (usámos `OUT` + região `AO-CAB`). Só os 14% e os 5% foram confirmados em mais de uma fonte.
2. **A numeração das extensões ao PGC**, sobretudo as contas de IVA em 34.2.x.
3. **A estrutura da declaração periódica de IVA** contra o modelo oficial da AGT.
4. **As contas por defeito:** vendas 61.3.1, compras 21.2, clientes 31.1.2.1, fornecedores 32.1.2.1.

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
