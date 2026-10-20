# Fase 3b: imobilizado e amortizações (`l10n_ao_asset`)

> **Revisto na auditoria de 2026-10-21** (`auditoria-fase-3.md`): quotas pela vida útil (36 × 10 000 em vez de 37 quotas); períodos bloqueados recusados; alienação retroactiva e futura recusadas, com «Anular alienação»; rascunhos e cancelamentos tratados; descontos e IVA não dedutível nas facturas; categoria no artigo para contas partilhadas; quantidade e reduzido valor por unidade; bens não amortizáveis; «das quais de exercícios anteriores» no arranque; taxa acima da legal não aceite no mapa; permissões apertadas; menu na raiz da app.

**Estado:** concluída a 2026-10-20. Testes: 14 (`make test m=l10n_ao_asset`). Testado no browser (base `kututa_demo`).

**Fontes:** `docs/referencias/amortizacoes/TAXAS.md` e `taxas.csv`: Decreto Presidencial n.º 207/15 (477 taxas conferidas com o PDF oficial do DR) e arts. 24.º–44.º do Código do Imposto Industrial (Lei 19/14, alterada pela Lei 26/20). Os dados do módulo geram-se com `tools/gen_asset_rates.py`.

## O que faz
- **Taxas legais:** as 477 linhas da tabela do DP 207/15 (secções A a N), mais o incorpóreo do CII (5 anos sem período determinável; software 3 anos). Menu Configuração › Imobilizado › Taxas legais.
- **Categorias** (criadas automaticamente nas empresas AO, com o diário «Operações de imobilizado», IMO):

  | Categoria | Contas | Taxa |
  |---|---|---|
  | Edifícios comerciais e administrativos | 11.2.1.2 / 18.1.2 / 73.1.2 | G.1.3, 4% |
  | Edifícios industriais | 11.2.1.1 / 18.1.2 / 73.1.2 | G.1.1, 4% |
  | Construções ligeiras | 11.2.2 / 18.1.2 / 73.1.2 | G.1.6, 12,5% |
  | Instalações | 11.2.3 / 18.1.2 / 73.1.2 | G.2.1, 10% |
  | Máquinas e equipamentos | 11.3.1 / 18.1.3 / 73.1.3 | G.3.17, 12,5% |
  | Viaturas ligeiras (limite fiscal) | 11.4 / 18.1.4 / 73.1.4 | G.4.1.2, 25% |
  | Viaturas pesadas | 11.4 / 18.1.4 / 73.1.4 | G.4.1.1, 16,67% |
  | Equipamento informático | 11.5 / 18.1.5 / 73.1.5 | G.3.1, 33,33% |
  | Mobiliário de escritório | 11.5 / 18.1.5 / 73.1.5 | G.5.5.2, 12,5% |
  | Programas informáticos | 12.9 / 18.2.9 / 73.2.9 | CII art. 39.º/4, 33,33% |
  | Propriedade industrial e I&D | 12.3 / 18.2.3 / 73.2.3 | N.1, 20% |

- **Fichas de imobilizado** (Contabilidade › Imobilizado): quotas constantes, em **duodécimos** (a partir do mês de entrada em funcionamento, art. 29.º/2; por omissão) ou **anuais** (ano completo, art. 29.º/1); a última quota acerta o remanescente.
- **Criação automática a partir das facturas de fornecedor:** cada linha lançada na conta de uma categoria cria uma ficha em rascunho, ligada à factura (botão «Imobilizado» na factura).
- **Bens de reduzido valor** (até Kz 30 000, art. 36.º): uma só quota. O limite está na ficha da empresa.
- **Viaturas ligeiras:** a amortização da parte acima de Kz 20 000 000 aparece como «não aceite» no mapa (art. 40.º, al. e), Lei 26/20).
- **Arranque com bens já amortizados:** amortizações anteriores e a data até à qual foram praticadas; o plano continua daí.
- **Lançamento das quotas:** cron diário (e botão «Lançar quotas vencidas»): 73.x a débito, 18.x a crédito.
- **Alienação / abate:** quotas até ao mês (ou ano) anterior (art. 29.º/4); o lançamento anula o bruto (11/12) e as amortizações (18) e leva o valor líquido a 78.3.1/78.3.2 (venda) ou 78.3.3 (abate). O preço de venda factura-se à parte, com o proveito em 68.3.
- **Mapa de reintegrações e amortizações** (art. 43.º; Relatórios › Angola (PGC)): por categoria e por bem, com código da tabela, ano de aquisição, valor, taxa, amortizações acumuladas no início, do exercício e no fim, valor líquido, abates e amortização não aceite. PDF e Excel. Só entram as amortizações contabilizadas (art. 25.º/3).

## Teste no browser
- Ficha «Portátil Dell Latitude», 450 000 Kz, categoria Equipamento informático: taxa G.3.1 33,33% preenchida pela categoria; plano de 12 500 Kz por mês a partir de 31/10 (36 quotas).

## A confirmar com um consultor fiscal
- Ano de entrada no regime anual: lido à letra, leva uma quota completa (está assim implementado).
- Trespasses e despesas de constituição não constam da tabela (não há categoria por omissão).
- Limite de Kz 30 000: não foi encontrada actualização por Decreto Executivo (configurável na empresa).
- Três linhas da tabela oficial com taxa e vida útil incoerentes (B.4.1, J.1.19, M.3.5): prevalece a taxa.

## Fica para mais tarde
| Tema | Motivo |
|---|---|
| Notas 4 e 5 do PGC (mapas de movimentos por rubrica) | Os dados existem nas fichas; falta o relatório |
| Reavaliações (Decreto 6/96) e amortizações extraordinárias | Sem regime fiscal em vigor para reavaliações livres (OGE 2026) |
| Laboração intensiva (+25% / +50%) | Basta alterar a taxa da ficha |
| Bens usados (art. 34.º) | Basta alterar a taxa da ficha |
