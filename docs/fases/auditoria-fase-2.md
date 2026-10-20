# Auditoria da Fase 2 (`l10n_ao_edi`, `l10n_ao_edi_pos` e arredondamento do `l10n_ao`)

**Data:** 2026-10-20.

**Método:**
- três revisões de código independentes (2a numeração e facturas, 2b fila, recibos e séries, 2c POS), confrontadas com a especificação da AGT (`docs/referencias/agt-facturacao-electronica/`);
- teste de todos os ecrãs no browser (base `kututa_demo`).

**Resultado:** cerca de 60 achados, alguns repetidos entre revisões. Os críticos, altos e médios foram corrigidos, com testes. O que depende da AGT ou de uma decisão está na última secção.

**Testes:** 123 nos três módulos (eram 86), 0 falhas. Lint limpo.

## Corrigido

### Críticos
| # | Problema | Correcção |
|---|---|---|
| 1 | **O fecho de sessão do POS gerava uma Factura (FT) AGT** com todas as vendas já comunicadas nos talões (IVA em duplicado). Com devoluções, a sessão nem fechava. | Os movimentos de fecho e de correcção da sessão não são documentos AGT (`_l10n_ao_edi_is_internal_move`) |
| 2 | **Um caixa (só POS) não conseguia vender nem abrir a sessão** (sem acesso às séries) | Pesquisa e reserva das séries com privilégios de sistema |
| 3 | **Quem não é administrador não conseguia assinar**: «Enviar à AGT», «Pedir série», «Confirmar na AGT» davam erro de acesso | Assinatura com as chaves lidas com privilégios de sistema |
| 4 | **Preço com IVA incluído:** total 100,01 num artigo de 100 Kz; o payload enviava o IVA como desconto | Novo cálculo (Python e POS): imposto = base arredondada × taxa, por excesso, e o total nunca ultrapassa o preço de etiqueta. Payload com preços sem imposto |
| 5 | **Recibo de venda do Odoo (`out_receipt`):** ocupava um número da série AGT e bloqueava as facturas seguintes | Recibos de venda proibidos nas empresas AGT. Os movimentos não-AGT do diário já não continuam a numeração AGT |
| 6 | **Linhas de desconto no POS** (preço negativo) iam à AGT como valores positivos | Linhas negativas recusadas no POS e nas facturas (a AGT não aceita valores negativos); usar o desconto % |

### Altos
| # | Problema | Correcção |
|---|---|---|
| 7 | **Motivo da NC/ND nunca exigido de facto:** caía na referência do Odoo («Estorno de: …») | Só conta o «Motivo (AGT)» escrito pelo utilizador. O assistente de nota de débito também o preenche |
| 8 | **Recibos com o tipo errado:** RC é o recibo do regime de caixa do IVA; o recibo de facturas, com `paymentReceipt`, é o **RG (Recibo Geral)** | Recibos passam a RG (série RG) |
| 9 | **Totais Odoo e AGT divergiam com descontos** (8,15 contra 8,14) | Imposto sobre a base arredondada. O payload usa o imposto da própria linha |
| 10 | **Documentos presos em «Enviado» para sempre:** documento sem estado na resposta, erros definitivos, simulador com requestID repetido | Voltam à fila. Erros definitivos encerram o pedido. requestID único no simulador |
| 11 | **Reenvio após timeout:** o erro E09 («já existe») marcava como rejeitado, e a «correcção» criava uma venda em duplicado | E09 / `successRequestID` contam como recebido/válido. Linhas bloqueadas durante o envio (`FOR UPDATE SKIP LOCKED`). O cron pára quando o tempo acaba |
| 12 | **Um lote com erro parava a fila inteira** (todas as empresas) | Cada lote e cada consulta correm à parte (savepoint); o erro fica no documento |
| 13 | **Documento alterável depois de comunicado:** nome por ORM ou «Resequence», cliente, datas | Bloqueio no `write` dos campos que definem o documento |
| 14 | **Talão alterável depois de emitido:** gorjeta depois do pagamento, re-sincronização | Linhas bloqueadas. Gorjeta depois do pagamento proibida. A re-sincronização é ignorada |
| 15 | **O payload era calculado no envio**, com os dados do momento: se o cliente ou o artigo mudassem, a AGT recebia outra coisa | Documento fixado na emissão (`l10n_ao_edi_payload`) para facturas, recibos e talões |
| 16 | **Recibo inconsistente se o pagamento fosse desconciliado** | Facturas pagas fixadas na emissão. Desconciliação bloqueada depois de comunicado. Sem facturas pagas, o recibo não segue |
| 17 | **Recibo ou talão rejeitado sem saída** | Correcção com novo número, `documentStatus` C e `rejectedDocumentNo` |
| 18 | **Séries:** activação manual ignorava o 1.º número autorizado. `listarSeries` importava séries fechadas e do Portal e recomeçava no n.º 1 | Corrigido conforme a especificação (`establishmentNumber`, `seriesStatus`, `invoicingMethod`, `lastDocumentCreated`) |
| 19 | **Tipo de documento livre:** uma factura podia sair como NC ou RG | Validação do tipo AGT pelo tipo de movimento |
| 20 | **Devolução do POS feita no backend impossível** (sem campo para o motivo) | Campo «Motivo da devolução (AGT)» no formulário |

### Médios e baixos
- **Validações novas:**
  - notas de crédito acima do valor da factura;
  - datas fora de ordem cronológica na série;
  - cliente estrangeiro sem identificação fiscal;
  - devolução acima do vendido;
  - pagamento a crédito misturado com outros meios;
  - POS noutra moeda.
- **Retenções em numerário:** passaram a ser possíveis (contas de valores em trânsito também nos diários de caixa, sem mexer nas já configuradas). Migração `l10n_ao` 20.0.1.2.0.
- **Moeda estrangeira nas facturas:** câmbio do documento e arredondamento matemático.
- **Recibos parciais:** o último usa o remanescente, para a soma não exceder a factura.
- **Arredondamento por linha obrigatório** nas empresas AGT.
- **Abertura de sessão do POS:** verifica também as séries FR e FT, com o fuso de Luanda. O talão usa a série do ano da emissão.
- **«Original» / «2.ª via»:**
  - o talão sem preços (oferta) não conta nem leva o n.º AGT;
  - a impressão e o email do talão no backend contam;
  - o documento de correcção recomeça no Original.
- **Talão do POS:** passa a mostrar o **motivo de isenção** (exigido pelo DP 71/25).
- **Contingência:** a menção «Emitido em contingência» mantém-se depois da validação. «Enviar à AGT» em contingência avisa em vez de não fazer nada.
- **Modo de demonstração:** os documentos levam «DEMONSTRAÇÃO: documento sem validade fiscal» (protege contra activar o EDI numa empresa real sem mudar o ambiente). A «Última comunicação» passa a ser actualizada.
- **Respostas sem JSON** (proxy) não contam como comunicação com a AGT.
- **Comunicações AGT:**
  - passam a registar também pedidos de série, listagens e validações de fornecedores (Anexo III);
  - mostram os números AGT;
  - regras multi-empresa.
- **Recibo impresso:** documentos liquidados, totais, retenção e valor recebido.
- **Ecrãs:** ano «2026» sem separador; «Estado» traduzido; botão «Fatura» escondido nas vendas com talão.
- **POS:** o JS e o arredondamento AO também no quiosque (self-order). Migração `l10n_ao_edi_pos` 20.0.1.1.0 para os postos receberem os novos dados (o POS guarda os dados em cache).
- **Limpeza:** API `union()` actualizada; removido o patch `waitForPushOrder`, que não tinha efeito (o Odoo já espera pela sincronização antes de imprimir).

## Por fazer ou a confirmar
| Tema | Porquê |
|---|---|
| Recibo de factura em moeda estrangeira (objecto `currency`, proporção pelo valor na moeda da factura) | Precisa de exemplos da AGT; hoje só AOA está testado |
| Desconto de pronto pagamento no recibo | Como a AGT quer o desconto e o acerto de IVA no RG |
| `deductAllVAT` com dedução parcial (LD com linhas) | Hoje dá ND quando a dedução é mista |
| NC sobre facturas anteriores à adesão à facturação electrónica | Decisão: permitir referir documentos não electrónicos? |
| Impostos de valor fixo ou em cascata (verbas de IS, IEC + IVA): campo `taxAmount` | O template actual não os usa; a confirmar com casos reais |
| Linhas negativas | Hoje recusadas; confirmar se a AGT aceita algum caso |
| Talões de vendas offline: ordem cronológica e série do ano | Confirmar em homologação |
| RG nos recibos, série por posto do POS, campos assinados no `validarDocumento` | Confirmar em homologação |
| Recibo automático ao reconciliar pelo widget da factura | Hoje só pelo assistente «Pagar» ou pelo botão «Emitir recibo AGT» |
| Quiosque (self-order) | Assets incluídos mas não testados (módulo não instalado) |
