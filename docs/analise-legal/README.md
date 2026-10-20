# Adaptação do Odoo 20 Community à legislação angolana — síntese

Data: 2026-10-20 · Base: Odoo 20.0 Community (submódulo `odoo/`)

| Área | Diploma | Relatório detalhado |
|---|---|---|
| Facturação | Decreto Presidencial n.º 71/25, de 20 de Março (regime jurídico das facturas) | [01-faturacao-DP-71-25.md](01-faturacao-DP-71-25.md) |
| Contabilidade | Decreto n.º 82/01, de 16 de Novembro (Plano Geral de Contabilidade) | [02-contabilidade-PGC.md](02-contabilidade-PGC.md) |
| Recursos Humanos | Lei n.º 12/23, de 27 de Dezembro (Lei Geral do Trabalho) | [03-rh-LGT-12-23.md](03-rh-LGT-12-23.md) |

Legenda: ✅ já existe · 🟡 configuração/parcial · 🔴 desenvolvimento necessário

> Os textos da LGT e do DP 71/25 foram obtidos por OCR. Os artigos citados devem ser confirmados no PDF original antes de se implementar cada regra.

---

## 1. Constatações gerais

1. **O Odoo 20 não tem localização angolana (`l10n_ao`).** Só existem o país (`base.ao`), a moeda AOA (inactiva por omissão) e o idioma `pt_AO`. Uma empresa angolana fica hoje com o plano de contas genérico.
2. **Vários módulos-chave são exclusivos do Enterprise** e não estão nesta árvore:
   - `hr_payroll`, o processamento salarial;
   - `account_reports`, as demonstrações financeiras;
   - `account_asset`, o imobilizado;
   - a certificação do `l10n_pt` (hash RSA, ATCUD e SAF-T).
3. **Há boas bases técnicas na versão Community:**
   - `l10n_es_edi_verifactu` (cadeia de hash, QR, envio em tempo real);
   - `l10n_sa_edi` (cadeia por diário, certificados);
   - `certificate` (assinatura RSA);
   - o mecanismo `@template` de planos de contas;
   - `hr.version`, os contratos dentro do módulo `hr`;
   - `hr.time.rule`, os acréscimos por horário.

## 2. Principais lacunas por área

### Facturação (DP 71/25)
- 🔴 **Tipos de documento:** Factura-Recibo, Recibo como documento fiscal (art. 6.º), auto-facturação com série própria (arts. 11.º–12.º) e factura de adiantamento. A Nota de Débito não pode liquidar imposto (art. 3.º).
- 🔴 **Software certificado AGT:** assinatura e hash, n.º de certificação no documento, «Original»/«2.ª via» e séries comunicadas à AGT. Facturas em séries não comunicadas contam como não emitidas (art. 35.º).
- 🔴 **Rectificação e anulação:** só por Nota de Crédito, com motivo e referência ao documento de origem. A anulação directa é limitada (art. 8.º).
- 🔴 **Prazo de emissão:** a factura tem de ser emitida até ao 5.º dia útil após a operação (art. 8.º).
- 🔴 **Facturação electrónica e SAF-T (AO):** comunicação à AGT, modo de contingência, bloqueio ao fim de 60 dias sem comunicação, exportação SAF-T (arts. 16.º–25.º, 37.º).
- 🟡 **Já existe e falta ajustar:** numeração por diário e ano, bloqueio de edição e eliminação, total por extenso, quadro de impostos e notas de isenção. Só precisam de ser forçados ou ajustados para Angola.

### Contabilidade (PGC)
- 🔴 **Plano de contas PGC:** classes 1–8, códigos pontuados (ex. `31.1.2.1`). O plano de Moçambique **não serve**, porque tem outra ordem de classes e está em inglês. Tem de ser transcrito da §5.3 do decreto.
- 🔴 **Demonstrações financeiras:** Balanço, DR por natureza e por funções, Fluxos de Caixa e as 47 Notas, com comparativo N-1 em milhares de Kz.
- 🔴 **Apuramento de resultados** pela classe 8 e **gestão de imobilizado** (quotas constantes).
- 🟡 **Já existe:** exercício fiscal, datas de bloqueio, FIFO e custo médio, contas de ordem, analítica (classe 9) e o motor `account.report` para declarações de impostos.
- ⚠️ **O PGC de 2001 não prevê IVA.** As subcontas e taxas de IVA, Imposto de Selo e retenções têm de vir do Código do IVA e dos outros códigos fiscais.

### Recursos Humanos (LGT)
- 🔴 **Processamento salarial completo:** módulo próprio, ou licença Enterprise.
  - salário-hora, conforme o art. 237.º;
  - subsídios de férias e de Natal de pelo menos 50 %, conforme o art. 238.º;
  - recibo com os campos obrigatórios do art. 247.º;
  - limite de 25 % nos descontos voluntários, conforme o art. 248.º;
  - IRT e INSS.
- 🔴 **Contratos a termo:** causas taxativas, durações máximas, aviso de não renovação, conversão automática e período experimental (arts. 15.º–18.º).
- 🔴 **Horas extraordinárias:** limites de 2 h/dia, 40 h/mês e 200 h/ano, com acréscimos de +50 % e +75 % (arts. 185.º e 188.º).
- 🔴 **Cessação:** cálculo do aviso prévio e das compensações (arts. 307.º–311.º).
- 🔴 **Regras de férias e faltas:** férias no ano de admissão e limites das faltas justificadas.
- 🟡 **Configurável sem desenvolvimento:** 44 h por semana, acréscimos nocturno e de descanso semanal, feriados, 22 dias úteis de férias e os tipos de licença.
- ℹ️ **A LGT 2023 deixou de diferenciar por dimensão da empresa** (micro, pequena, média, grande).

## 3. Arquitectura de módulos proposta (`custom_addons/`)

| Módulo | Conteúdo | Depende de |
|---|---|---|
| `l10n_ao` | Plano PGC (cerca de 450 contas), impostos (IVA, Selo, retenções), posições fiscais, NIF, motivos de isenção, AOA activa, feriados | `account` |
| `l10n_ao_invoicing` | Tipos de documento AO, séries AGT, menções obrigatórias, impressão, regras de NC/anulação, prazos, assinatura RSA e cadeia de hash | `l10n_ao`, `certificate` |
| `l10n_ao_saft` | Exportação SAF-T (AO): facturação e contabilidade | `l10n_ao_invoicing` |
| `l10n_ao_reports` | Balanço, DR, DFC e Notas segundo o PGC (PDF/XLSX, N/N-1) | `l10n_ao` |
| `l10n_ao_hr` | Regras de contrato da LGT, tipos de ausência, horas extra, assistente de cessação, registos obrigatórios | `hr`, `hr_holidays`, `hr_work_entry` |
| `l10n_ao_payroll` | Recibos de salário, regras salariais, tabelas IRT/INSS, ficheiro bancário, lançamentos contabilísticos | `l10n_ao_hr`, `l10n_ao` |
| `l10n_ao_edi` *(fase 2)* | Comunicação electrónica à AGT (tempo real e contingência) | `l10n_ao_invoicing` |

## 4. Roadmap sugerido

1. **Fase 1, base (pré-requisito de tudo):** `l10n_ao`, com o plano PGC, os impostos e a moeda.
2. **Fase 2, conformidade fiscal:** `l10n_ao_invoicing` e depois `l10n_ao_saft`. Sem isto, o sistema não pode emitir facturas legalmente em Angola.
3. **Fase 3, RH:** `l10n_ao_hr` e depois `l10n_ao_payroll`.
4. **Fase 4, reporte:** `l10n_ao_reports` e o imobilizado.
5. **Fase 5:** `l10n_ao_edi`, quando a AGT publicar a especificação técnica.

## 5. Fontes externas necessárias (não estão nos documentos fornecidos)

**Bloqueantes:**
- Decreto Executivo previsto no art. 36.º do DP 71/25 (estrutura de dados e API da AGT);
- regulamento de certificação de software da AGT (algoritmo de hash e assinatura);
- esquema XSD do SAF-T (AO) e o DP 312/18, na parte não derrogada.

**Fiscais:**
- Código do IVA (taxas, IVA cativo, códigos de isenção);
- Código do Imposto de Selo;
- Código do Imposto Industrial (retenções);
- Código do IRT (tabelas de retenção);
- Código Geral Tributário (prazos de conservação).

**Laborais:**
- regime de contribuições do INSS (confirmar 3 % e 8 %);
- decreto do salário mínimo em vigor;
- lista oficial de feriados.
