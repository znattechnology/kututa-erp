# Fase 3a: Kututa Mbongo, demonstrações financeiras PGC (`l10n_ao_reports`)

> **Revisto na auditoria de 2026-10-21** (`auditoria-fase-3.md`): empresa restrita e verificada; apuramento com datas de bloqueio recusado, apuramento complementar, data fixa no fim do exercício e transferência só no exercício seguinte; Balancete com a 88 real e ordenação hierárquica; descobertos bancários em Empréstimos de curto prazo; Estado líquido por imposto; exercícios a terminar a 29/02.

**Estado:** concluída a 2026-10-20. Testes: 15 (`make test m=l10n_ao_reports`), 0 falhas. Testado no browser (base `kututa_demo`).

## O que faz
Menu **Contabilidade › Relatórios › Angola (PGC)**:

| Mapa | Modelo PGC | Notas |
|---|---|---|
| **Balanço** | 4.2.3 | Data de referência; comparativo N-1 à mesma data |
| **Demonstração de Resultados por natureza** | 4.3.3 | Período; comparativo N-1 no mesmo período do ano anterior |
| **Balancete geral** | — | Saldo inicial, débitos, créditos, saldo devedor e credor; por classe, conta, subconta ou todas |

- Saídas: **Ver** (pré-visualização HTML), **PDF** e **Excel**.
- Valores em Kwanzas ou **milhares de Kwanzas** (4.1.4). Os totais somam os valores já arredondados.
- As rubricas sem valor nos dois exercícios são omitidas (4.1.7), mantendo a ordem e as notas do modelo (4.1.6).

**Encerramento do exercício** (só para gestores de contabilidade):
- **Apuramento de resultados:** lançamento no diário APR (criado automaticamente) com as subcontas x.9 → 82 a 86 e estas → 88; o imposto 87 → 88.5 / 88.7. Exige que o exercício anterior esteja apurado e que não haja rascunhos no exercício.
- **Transferência para resultados transitados:** 88.9 → 81.1.1, normalmente no primeiro dia do exercício seguinte, depois da aprovação das contas.
- Não se pode repetir nenhum dos dois para o mesmo exercício (salvo cancelando o lançamento).

## Regras de cálculo
- **Resultado do exercício** = proveitos e custos (classes 6 e 7 e imposto 87) desde o início do exercício, **sem as subcontas de transferência** (x.9, 68.19, 78.19, 82.19). Por isso a DR e o Balanço dão o mesmo valor antes e depois do apuramento.
- **Resultados transitados** = conta 81 + 89 + todo o resultado acumulado de exercícios anteriores. Um exercício não apurado aparece no seguinte como resultados transitados, e o Balanço continua a fechar.
- **Não compensação de saldos:** nas contas de clientes e fornecedores, cada terceiro é classificado pelo sinal do saldo (um adiantamento de cliente vai para Contas a pagar). Nas restantes contas de terceiros (34, 35, 36, 37.1/37.2/37.7/37.9), conta a conta.
- **Correntes / não correntes:** as contas da classe 3 com o tipo «activo/passivo não corrente» vão para Outros activos/passivos não correntes; nos empréstimos (33), o tipo «passivo corrente» identifica os de curto prazo.
- **Mapeamento das rubricas do Balanço:** 11, 14 (sem 14.8/14.9) e 18.1 → Imobilizações corpóreas; 12, 14.8 e 18.2 → incorpóreas; 13.1/13.2 e 19.1/19.2 → subsidiárias e associadas; restantes 13, 19, 14.9 e 18.3 → Outros activos financeiros; classe 2 → Existências; 37.3/37.4 → Outros activos correntes; 37.5/37.6 → Outros passivos correntes; 39.1 → Provisões para pensões; restantes 39 → outros riscos; classe 4 (incluindo 48, valores em trânsito) → Disponibilidades; 51–54 → Capital; 55–58 → Reservas.
- **Balancete:** as contas de resultados começam no início do exercício; o que ficou por apurar de anos anteriores aparece na linha «Resultados de exercícios anteriores por apurar», para o balancete fechar.

## Teste no browser
- Balanço da demo a 20/10/2026: Activo 232 900,00 = Capital próprio e passivo 232 900,00, com Resultado do exercício 100 000,00.

## Fica para mais tarde
| Tema | Motivo |
|---|---|
| DR por funções | Exige classificar os custos por função (analítica); a DR por natureza é obrigatória e suficiente |
| Demonstração de fluxos de caixa | Temporariamente suspensa pelo PGC (1.4.1); recomendada. Exige classificar os movimentos de caixa por actividade |
| Notas às contas (mapas automáticos) | Os mapas do imobilizado (notas 4 e 5) vêm do `l10n_ao_asset` (3b) |
| Parte corrente dos empréstimos de m/l prazo, impostos diferidos | Sem informação no plano de contas; ficam a zero |
| Diferimento das diferenças de câmbio favoráveis (37.6.4) | Requer alterar o lançamento das diferenças de câmbio do Odoo |
