# Auditoria da Fase 4 (`l10n_ao_hr`, `l10n_ao_payroll`)

**Data:** 2026-10-21.

**Método:**
- duas revisões de código independentes, uma por módulo, confrontadas com a LGT (Lei 12/23, OCR em `docs/referencias/salarios/fontes/ocr/`), o CIRT e a tabela da Lei 14/25, o DP 227/18 e a Lei dos feriados;
- teste de todos os ecrãs no browser (base `kututa_demo`).

**Resultado:** os achados críticos, altos e médios foram corrigidos, com testes (35 no `l10n_ao_hr` e no `l10n_ao_payroll` juntos: 9 e 26). A bateria dos 9 módulos tem 194 testes e 0 falhas. O que depende de uma decisão ou de legislação incerta está na última secção.

## Corrigido

### Recursos humanos (`l10n_ao_hr`)
| # | Problema | Correcção |
|---|---|---|
| 1 | **Limites das faltas justificadas bloqueavam a ausência.** Na LGT, o excesso continua justificado, só não é pago (arts. 223.º a 228.º) | A ausência é aceite; o excesso por evento, por mês e por ano fica em «Dias não remunerados» e a folha desconta-o |
| 2 | Proporção mensal das ausências por dias de segunda a sexta, errada no horário de 44 h com sábado | Proporção pelos dias de trabalho do horário do trabalhador |
| 3 | Abandono (art. 306.º) só detectado dentro de uma única ausência | Junta as faltas injustificadas contíguas |
| 4 | Causas dos contratos a termo trocadas (h, i, j, k) e sem o reformado (art. 15.º, n.º 2) | Causas e durações revistas; prorrogação pela IGT (al. a, h, j, até 24 meses); renovações com intervalo até 30 dias contam na mesma cadeia |
| 5 | Período experimental por omissão nos contratos a termo; não acompanhava a mudança da data de início | Só no indeterminado (60 dias), deslocado com a data de início se era o de omissão |
| 6 | Alerta de fim de contrato repetido todos os dias | Uma única vez, 45 dias antes |
| 7 | Antiguidade sem contar o último dia; data de admissão desactualizada | Conta o último dia; data recalculada a partir dos contratos |
| 8 | **Horas extra:** qualquer utilizador aprovava os seus registos e marcava «autorizado pela IGT» | Só o RH aprova; os outros criam em rascunho; registos aprovados bloqueados; limites mês/ano contam o descanso e o feriado; arredondamento dos minutos para baixo |
| 9 | **Suspensão disciplinar sem efeito na folha** e sem os limites de 30/60 dias (art. 87.º, n.º 3) | Aplicar a suspensão cria a ausência não paga validada (anular recusa-a); limites verificados; sanção aplicada bloqueada; tipos oral e despromoção |
| 10 | Feriados: datas das leis, pontes do ano vizinho, meios-dias que já eram feriado | Corrigidos; geração com verificação por sobreposição e cron com savepoint por empresa |
| 11 | Tipos em falta (paternidade complementar, eleições, casamento de familiar); casamento e maternidade em dias úteis | Criados; casamento e maternidade em dias de calendário |
| 12 | Sem formulário do trabalho extraordinário; registos sem nome | Formulário e `display_name` (horas extra, sanções, adiantamentos) |

### Salários (`l10n_ao_payroll`)
| # | Problema | Correcção |
|---|---|---|
| 1 | **«Calcular» apagava os recibos em rascunho:** perdiam-se os tempos lectivos, as outras linhas e as contas finais | Recalcula no sítio; só cria os recibos em falta e só remove os mensais de quem deixou de ter contrato |
| 2 | Quem saiu e foi arquivado a meio do mês ficava sem recibo | Trabalhadores arquivados incluídos |
| 3 | Aumento ou renovação a meio do mês: o mês todo pago ao último salário | Rateio por segmentos de versão (salário × dias úteis de cada um) |
| 4 | **Anular a folha** deixava os adiantamentos liquidados, o subsídio de férias dado como pago e o lançamento cancelado | Adiantamentos reabertos, ano do subsídio reposto, lançamento estornado (o original fica no diário) |
| 5 | **Contas finais:** subsídio de férias e Natal numa só linha com INSS; meses incompletos contados; aviso prévio só a favor do trabalhador | Linhas separadas (férias fora do INSS); só meses completos; na denúncia e no abandono o aviso prévio é descontado; subsídio das férias vencidas quando ainda não pago |
| 6 | Menu «Contas finais» rebentava (`active_id` no contexto) | Acção própria para o menu |
| 7 | Contas finais numa folha anulada | Recusadas |
| 8 | **Utilizador só de RH não fechava a folha** (sem direitos na contabilidade e na sequência) | Sequência, diário, contas e lançamento com `sudo` |
| 9 | O trabalhador não via a conta bancária do próprio recibo; via as linhas dos recibos em rascunho | `compute_sudo`; só linhas de recibos fechados |
| 10 | Mapa do IRT: «não sujeitos» incluíam as faltas; contabilista sem acesso ao BI | Colunas de faltas e sanções; `sudo` na leitura |
| 11 | **Professores pagos ao tempo:** salário-hora, subsídios e limite dos adiantamentos a zero | Salário de referência = média dos tempos dos últimos 12 recibos fechados (art. 237.º, n.º 8) ou os do mês; sem referência, o adiantamento é recusado |
| 12 | Subsídios desmarcados à mão voltavam no recálculo | Marca «definidos à mão» |
| 13 | Duas linhas de alimentação isentavam 30 000 Kz cada | Limite de isenção do IRT por tipo de componente |
| 14 | Natal proporcional contava o mês de admissão incompleto | Só meses completos |
| 15 | Sem tabela do IRT em vigor, aplicava-se em silêncio a mais antiga | IRT a zero com aviso no recibo |
| 16 | Linhas, linhas adicionais, amortizações e componentes sem regra multi-empresa | Regras criadas |
| 17 | **Feriado pago a 200%** quando o salário mensal já paga o dia | Só o acréscimo de um dia (art. 200.º, n.º 2) |
| 18 | Fecho com líquido negativo | Recusado, com aviso no recibo |
| 19 | Adiantamentos concedidos depois do mês descontados nesse mês | Só os concedidos até ao fim do mês |
| 20 | Compensações de antiguidade lançadas em 72.2 | Conta própria configurável (72.8.2 por omissão) |
| 21 | Ficheiro bancário com linhas sem IBAN e líquidos nulos | Recusa a lista de quem não tem IBAN; salta líquidos ≤ 0 |
| 22 | Folha colectiva: totais com os recibos anulados e sem sanções | Corrigida |
| 23 | Faltas não pagas sem o excesso das justificadas nem as suspensões | Somadas (`hr.leave._l10n_ao_unpaid_hours` e tipo AO_SUSPENSAO) |
| 24 | Fundamento do subsídio de férias fora do INSS | DP 227/18, art. 13.º, n.º 3, al. b) (não o art. 6.º) |

### Verificação no browser
- Recalcular a folha de Setembro mantém os 64 tempos do Pedro Docente (192 000 Kz).
- O menu «Contas finais» abre o assistente vazio.
- O trabalho extraordinário abre em formulário, com os botões de aprovação reservados ao RH.

## Por decidir ou só documentado
- **Maternidade:** a parte paga pelo INSS e o regime do DP 95/26 não estão confirmados; a folha trata a licença como não paga pelo empregador.
- **Semana da ponte:** a compensação de 1h30 por dia não é calculada.
- **Delegados sindicais:** o crédito de horas não é controlado.
- **Contrato indeterminado com data de fim:** aceite (pode ser uma saída já prevista); sem aviso.
- **Subsídio de férias no ano da admissão:** pago por inteiro; o proporcional fica configurável no motor (`vacation_months`), mas sem regra automática até haver interpretação firme.
