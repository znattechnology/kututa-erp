# Auditoria da Fase 3 (`l10n_ao_reports`, `l10n_ao_asset`, `l10n_ao_saft`, `l10n_ao_stock`)

**Data:** 2026-10-21.

**Método:**
- quatro revisões de código independentes, uma por módulo, confrontadas com as fontes legais (PGC, DP 207/15 e CII, DE 317/20 e XSD SAF-T, Circular 05/2026), com reprodução dos achados em bases de teste;
- teste de todos os ecrãs no browser (base `kututa_demo`).

**Resultado:** cerca de 90 achados. Os críticos, altos e médios foram corrigidos, com testes; o que depende da AGT ou de uma decisão está na última secção. Nada do que foi corrigido altera a Fase 2.

## Corrigido

### Demonstrações financeiras e encerramento (`l10n_ao_reports`)
| # | Problema | Correcção |
|---|---|---|
| 1 | **Fuga entre empresas:** um utilizador podia pedir, por RPC, o Balanço de uma empresa a que não tem acesso (os assistentes usam `sudo`) | Empresa restrita às acessíveis e verificada antes de calcular |
| 2 | **Apuramento com data de bloqueio:** o Odoo mudava a data do lançamento para o exercício seguinte e o exercício ficava por apurar, sem possibilidade de repetir | Verificação das datas de bloqueio antes do lançamento e da data depois |
| 3 | **Balancete:** a conta 88 era reposta a zero no início do exercício; com uma transferência feita, ficava com saldo trocado | A 88 transita com o saldo real; só as classes 6 e 7 e as 82 a 87 começam a zero |
| 4 | **Balancete:** as classes saíam todas no topo, antes das contas | Ordenação hierárquica (3, 31, 31.1…, 4…) |
| 5 | **Lançamento feito depois do apuramento:** impasse («já foi apurado» / «por apurar») | Apuramento complementar, que só leva o que foi lançado depois |
| 6 | **Descobertos bancários** abatiam às Disponibilidades | Saldos credores da classe 4 vão para Empréstimos de curto prazo (nota 20; não compensação, PGC 3.5.3) |
| 7 | **Estado (34)** classificado conta a conta: as retenções sofridas iam para Contas a receber | Líquido por imposto (34.1, 34.2…), como na nota 19 a) |
| 8 | Exercício a terminar a 29/02 rebentava o assistente; o comparativo N-1 perdia o 29/02 | Datas calculadas pelo dia 1 do mês; fim de mês corresponde a fim de mês |
| 9 | Data do apuramento editável para qualquer dia do exercício, com saldos do ano inteiro | Fixa no último dia do exercício |
| 10 | Transferência 88 → 81 aceite no próprio exercício e com o saldo acumulado de outros anos | Exige o exercício seguinte e usa só o resultado dos apuramentos desse exercício |
| 11 | Grupo 74 na DR sem regra de apuramento; prefixos como «18.1» apanhavam «18.10»; apuramento estornado não reconhecido; diário APR sem tipo; sucursais | Corrigidos |
| 12 | Ano com separador de milhares («2.025») nos assistentes | Corrigido |
| 13 | Grupo Facturação com acesso aos mapas pelo `sudo` | Mapas só para «Contabilidade» (leitura) e administradores |

### Imobilizado (`l10n_ao_asset`)
| # | Problema | Correcção |
|---|---|---|
| 14 | **Datas bloqueadas:** as quotas de exercícios bloqueados eram lançadas todas no primeiro dia livre, e o mapa divergia do razão (art. 25.º/3) | A confirmação e o lançamento recusam quotas em períodos bloqueados: registam-se em «Amortizações anteriores» |
| 15 | **Alienação retroactiva** mantinha as quotas já lançadas depois do mês da alienação (art. 29.º/4) | Recusada enquanto houver quotas lançadas a partir desse mês; a data não pode ser futura |
| 16 | **Lançamentos em rascunho ou cancelados:** amortização duplicada ou 18.x negativa; uma quota cancelada nunca voltava a ser lançada | Os rascunhos bloqueiam a alienação e o reset; os cancelados contam como por lançar |
| 17 | **Factura de fornecedor com desconto** (linha negativa na conta 11/12) não podia ser lançada | As linhas negativas abatem às positivas; o IVA não dedutível entra no valor da ficha |
| 18 | **Contas partilhadas** (11.4 e 11.5): o mobiliário entrava como equipamento informático a 33,33% e os camiões como viaturas ligeiras | Categoria de imobilizado no artigo; quando a conta é ambígua, a ficha avisa |
| 19 | **Mapa:** as amortizações anteriores com arranque a meio do exercício contavam todas como do exercício; a taxa acima da legal não era «não aceite»; abates sem as amortizações anuladas | Campo «das quais de exercícios anteriores»; excesso de taxa não aceite (art. 40.º); coluna «Abates: amortizações» |
| 20 | **Factura reaberta ou cancelada:** fichas órfãs ou duplicadas, valores desactualizados | As fichas em rascunho são apagadas e recriadas ao relançar; fichas confirmadas bloqueiam a reabertura |
| 21 | Cron tudo-ou-nada; ficha totalmente amortizada no arranque ficava «em uso»; taxa 0 (terrenos) não confirmava; reduzido valor por ficha e não por unidade (art. 36.º); 37.ª quota de 36 Kz | Cron por ficha com registo do erro; estado «amortizado»; bens não amortizáveis; quantidade na ficha; quotas pela vida útil (36 × 10 000) |
| 22 | Alienação sem retorno | «Anular alienação» repõe o plano |
| 23 | Qualquer facturador podia editar quotas e fichas confirmadas por RPC | Quotas só de leitura; os dados do plano só se alteram em rascunho; eliminação só para administradores |
| 24 | Menu invisível na app Facturação; etiqueta «Asset»; botões sem grupos; sem resposta ao «Lançar quotas» | Corrigidos |

### SAF-T (`l10n_ao_saft`)
| # | Problema | Correcção |
|---|---|---|
| 25 | **Facturas em moeda estrangeira:** linhas e totais saíam na moeda do documento e o `CurrencyAmount` em Kz (o DE 317/20 pede o inverso) | Convertidas para AOA pelo câmbio do documento; `CurrencyAmount` na moeda original |
| 26 | **Empresa diferente da activa:** contas sem código e erro de keyref sem explicação | Todo o ficheiro corre na empresa escolhida, restrita às acessíveis |
| 27 | **Sucursais:** o razão incluía-as mas as facturas não; diários com o mesmo código duplicavam o JournalID | Facturas, recibos e compras também das sucursais; JournalID com sufixo na sucursal |
| 28 | **Documentos antigos sem payload:** eram todos carregados (de todos os anos), voltavam a ser assinados e rebentavam sem chave | Filtro por data na pesquisa e reconstrução sem assinatura |
| 29 | Cliente com o contacto em vez da entidade; TransactionID em falta no ficheiro F; IEC como TaxType; IS sem código; PaymentAmount na moeda do pagamento; conta órfã como GR; caracteres de controlo; ordenação dos números | Corrigidos |
| 30 | Plano de contas ou tabela de impostos vazios davam um erro de XSD sem explicação; o erro de XSD não mostrava o conteúdo da linha | Mensagens próprias; a linha do XML é mostrada |

### Inventário (`l10n_ao_stock`)
| # | Problema | Correcção |
|---|---|---|
| 31 | **Quantidade e valor contavam stock diferente:** a quantidade incluía consignação e todas as localizações; o valor só as valorizadas | Quantidade com o mesmo âmbito da valorização do Odoo (localizações valorizadas, stock próprio, sem kits) |
| 32 | **ProductCode repetido** (códigos iguais, código igual ao id de outro artigo, cortes a 60 caracteres) | Erro com a lista de repetidos |
| 33 | **Fuso horário:** 31/12 às 23:59 UTC já é 1 de Janeiro em Luanda | Hora local de Luanda |
| 34 | Assinatura acima de 500 caracteres com chaves de 4096 bits; sem chave do contribuinte não havia ficheiro | Verificação do tamanho; a chave do produtor serve de alternativa |
| 35 | **Custo padrão por omissão** nas empresas AO, declarado como CMP; conta de existências vazia | O plano `l10n_ao` passa a ter a conta 26.1 e o custo médio por omissão (migração 20.0.1.3.0) |
| 36 | Stock negativo exportado; exercício sem validação; quantidade com formatação de `float`; descrição com «[código]» | Corrigidos |
| 37 | Contabilistas sem acesso ao assistente | Grupos de contabilidade adicionados |

### Segunda passagem (2026-10-21)
| # | Problema | Correcção |
|---|---|---|
| 38 | **Documento rejeitado pela AGT e corrigido:** o número original desaparecia do SAF-T, abrindo uma falha na sequência | Os documentos rejeitados ficam guardados (`l10n_ao_edi_rejected_payloads`, em facturas, recibos e talões) e saem no SAF-T como anulados (A), com o número original |
| 39 | Notas de crédito de fornecedor não ajustavam as fichas de imobilizado | Abatem o valor às fichas em rascunho; nas confirmadas criam uma actividade para regularizar |
| 40 | Balancete com «Omitir rubricas sem valor» desligado não mostrava as contas sem movimentos; valores «-0,0» | Corrigidos |
| 41 | Excel das demonstrações sem os avisos de rascunhos e de saldos fora do PGC; anexos de exportações anteriores acumulavam | Avisos no Excel; os anexos antigos do utilizador são apagados |
| 42 | Referência do bem repetida; categorias por omissão omitidas em silêncio quando falta uma conta | Referência única por empresa; aviso no registo |

## Testes
- `l10n_ao_reports`: 15 (eram 11); `l10n_ao_asset`: 15 (eram 8); `l10n_ao_saft`: 9 (eram 4); `l10n_ao_stock`: 7 (eram 6).
- Bateria dos oito módulos: 161 testes, 0 falhas.

## Por fazer ou a confirmar
| Tema | Porquê |
|---|---|
| IVA dedutível por tipo (`Deductible`) nas compras; `WorkingDocuments` e `MovementOfGoods` | Faltam os dados; ver fase-3c |
| Hash dos documentos no SAF-T | DE 74/19 por obter |
| Movimentos manuais nas contas 82 a 88 no exercício corrente | Saem em «Resultados transitados»; a prática é não lhes lançar à mão (o apuramento faz-se pelo assistente) |
| Balanço em milhares: o Activo e o Capital próprio + Passivo podem diferir em 1 por arredondamento | O modelo do PGC não tem rubrica de diferença; em Kwanzas fecha sempre |
| Reduzido valor: a excepção dos conjuntos (art. 36.º/2) é manual (desmarcar) | — |
| Etiquetas do inventário em XML/JSON | A confirmar com a AGT |
