# Regras de RH e folha do secPed-Express (fonte para a Fase 4)

Resumo extraído do código do secPed (`apps/api/src/modules/hr/`, `prisma/schema.prisma`) a 2026-10-21. Os casos de teste servem de «golden tests» ao `l10n_ao_payroll`.

## IRT (grupo A), Lei n.º 14/25 (OGE 2026), em vigor desde 2026-01-01
Fonte no secPed: `apps/api/src/modules/hr/domain/irt-table.ts` e migração `20260908000000_irt_national_table`.

| # | Limite inferior (excl.) | Limite superior (incl.) | Parcela fixa | Taxa % | Excesso sobre |
|---|---|---|---|---|---|
| 1 | 0 | 150 000 | 0 | 0 | 0 |
| 2 | 150 000 | 200 000 | 12 500 | 16 | 150 000 |
| 3 | 200 000 | 300 000 | 31 250 | 18 | 200 000 |
| 4 | 300 000 | 500 000 | 49 250 | 19 | 300 000 |
| 5 | 500 000 | 1 000 000 | 87 250 | 20 | 500 000 |
| 6 | 1 000 000 | 1 500 000 | 187 250 | 21 | 1 000 000 |
| 7 | 1 500 000 | 2 000 000 | 292 250 | 22 | 1 500 000 |
| 8 | 2 000 000 | 2 500 000 | 402 250 | 23 | 2 000 000 |
| 9 | 2 500 000 | 5 000 000 | 517 250 | 24 | 2 500 000 |
| 10 | 5 000 000 | 10 000 000 | 1 117 250 | 24,5 | 5 000 000 |
| 11 | 10 000 000 | — | 2 342 250 | 25 | 10 000 000 |

- IRT = parcela fixa + taxa × (base − excesso sobre), arredondado a 2 casas. Base ≤ 0 → 0.
- **Base do IRT** = rendimentos sujeitos − faltas − sanção − INSS do trabalhador (3%).
- Descontinuidades confirmadas contra a tabela publicada: 150 000 → 0; 150 001 → 12 500,16; 200 000 → 20 500; 200 001 → ~31 250.
- Isenções: subsídio de alimentação e de transporte até 30 000 Kz/mês cada (o excedente entra nas bases de IRT e INSS). Subsídios de férias e Natal, horas extra e tempos lectivos: sempre sujeitos.
- Só o grupo A está implementado.

## INSS
Trabalhador 3%, entidade patronal 8%, sobre a mesma base de incidência do IRT (sem tecto). Faltas e sanção reduzem a base.

## Motor da folha (`payroll-calc.service.ts`)
- **Salário-hora** (LGT art. 237.º/7): `(Sm × 12) / (52 × Hs)`; horas/dia = Hs/5.
- **Proporção do mês** (entrada ou saída a meio): dias úteis (seg–sex) com contrato ÷ dias úteis do mês; base e componentes fixos × f; o salário-hora é o do mês inteiro.
- **Tempos lectivos:** `count × rate`; `count = planeados − excepções − substituições dadas + recebidas + ajuste`.
- **Horas extra** (art. 188.º), arredondamento sobre o total mensal por tipo: <15 min = 0; 15–44 = 0,5 h; ≥45 = 1 h. Primeiras 30 h × 1,50; acima × 1,75. Nocturno (20h–6h): +0,20 só o adicional. Dia de descanso × 1,75. Feriado × 2. Limites ao registar: 2 h/dia, 40 h/mês, 200 h/ano (só extraordinário).
- **Subsídio de férias:** 50% da base, no mês em que começam as férias, uma vez por direito. **Natal:** em Dezembro, 50% × meses/12 (meses desde a admissão no ano).
- **Faltas** (art. 240.º): `min(horas × salário-hora, base do mês)`; só faltas aprovadas não pagas; dias úteis sem feriados; faltas parciais em horas; dias de suspensão disciplinar contam.
- **Sanção** (art. 87.º/2): redução de salário até 20%, 1 a 6 meses, do mês da decisão.
- **Ordem:** bruto → faltas → sanção → INSS → IRT → adiantamento.
- **Adiantamentos:** desconto mensal ≤ 25% de (bruto − faltas − sanção − INSS − IRT) (art. 248.º/7); dívida total ≤ 3 × salário-base (art. 248.º/6).
- Arredondamento a 2 casas por linha; bruto = soma das linhas.

## Lançamento contabilístico do fecho (último dia do mês)
| D/C | Conta | Valor |
|---|---|---|
| D | 72.2.1 Vencimentos e salários | bruto − faltas − sanções |
| D | 72.5 Encargos sobre remunerações | INSS patronal |
| C | 36.1 Pessoal — remunerações | líquido |
| C | 34.3 IRT retido | IRT |
| C | 34.9.1 INSS a entregar | INSS trabalhador + patronal |
| C | 36.3 Pessoal — adiantamentos | amortizações |
Pagamento: D 36.1 / C banco. Adiantamento concedido: D 36.3 / C caixa.

## Ausências (tipos e limites por omissão)
Doença (paga; sem tecto no código, a LGT dá 6 meses), casamento 8 dias, luto 8/3, obrigação legal 2/mês e 8/ano, provas escolares, formação, assistência familiar 8/ano, actividade cultural 8/ano, sindical, consulta pré-natal 1/mês, maternidade (não paga pela empresa), paternidade 1 dia, licença sem vencimento, injustificada (não paga), outra.

## Férias
22 dias úteis; no ano da admissão 2 dias por mês completo, mínimo 6, máximo 22.

## Cessação (`compensation.service.ts`)
- Antiguidade: fracção ≥ 3 meses conta como 1 ano (art. 311.º).
- 307.º e 309.º: 0,5 × base × anos. 308.º: base × anos até 5 + 0,5 × base × anos acima de 5. 310.º: max(base × anos, 3 × base).
- Férias na cessação: (vencidas + min(22, 2 × meses) − gozadas) × valor-dia, valor-dia = salário-hora × Hs/5.
- Subsídios proporcionais: base × (50% + 50%) × meses/12, excluindo os já pagos.
- Contas finais sem IRT/INSS nem lançamento (pendente no secPed).

## Contratos
Tipos: indeterminado, a termo certo, a termo incerto, comissão de serviço, aprendizagem, estágio. Causas do termo (art. 15.º) com tectos: substituição 36 meses, acréscimo 12, tarefa ocasional 12, sazonal 6, actividade limitada 12, urgente 6, actividade nova 60, aprendizagem/formação 36; sem tecto: inserção, periódica, reformado. Período experimental: ≤ 30 dias a termo; ≤ 180 no máximo. Horas semanais 44. Base de pagamento: mensal, por tempo lectivo ou misto.

## Casos dourados (dos testes do secPed)
- Salário-hora: 220 000 / 44 h → 1 153,85.
- IRT: 150 000 → 0; 160 000 → 14 100; 180 000 → 17 300; 200 000 → 20 500; 250 000 → 40 250; 300 000 → 49 250; 400 000 → 68 250; 12 000 000 → 2 842 250.
- Efectivo, base 200 000: INSS 6 000; patronal 16 000; base IRT 194 000; IRT 19 540; líquido 174 460.
- Alimentação isenta: base 100 000 + 30 000 → bruto 130 000, base INSS 100 000, base IRT 97 000, IRT 0, líquido 127 000.
- Alimentação 200 000 isenta: base INSS 370 000.
- Horas extra 35 h com base 200 000: salário-hora 1 048,95; 30 h × 1,5 = 47 202,80; 5 h × 1,75 = 9 178,32.
- Faltas: base 220 000, 2 dias → 17,6 h × 1 153,846 = 20 307,69.
- Adiantamento: base 100 000, pedido 90 000 → aplicado 24 250 (25% de 97 000); líquido 72 750.
- Sanção 20% em 200 000 → 40 000; base INSS 160 000; IRT 13 332; líquido 141 868.
- Natal: base 200 000, 6 meses → 50 000.
- Cessação: 200 000 × 4 anos (307.º) = 400 000; 308.º com 3 anos = 600 000, 8 anos = 1 300 000; 310.º 1 ano = 600 000.
- Saída a 15/06/2026 com base 100 000: «Salário base (11 de 22 dias úteis)» = 50 000.
