# Fase 2c: Kitanda, talões AGT no Ponto de Venda (`l10n_ao_edi_pos`)

> **Revisto na auditoria de 2026-10-20** (`auditoria-fase-2.md`): o fecho de sessão deixou de gerar uma FT AGT. Os caixas sem permissões de contabilidade já vendem. As linhas negativas são recusadas. O talão fica fixado e bloqueado depois de emitido, e a gorjeta depois do pagamento é proibida. Os talões rejeitados podem ser corrigidos. O talão mostra o motivo de isenção. A espera pela sincronização antes de imprimir é do próprio Odoo (o patch `waitForPushOrder` foi removido).

**Estado:** concluída a 2026-10-20. Testes: 86 nos três módulos (`make test m=l10n_ao,l10n_ao_edi,l10n_ao_edi_pos`), 0 falhas. Testado no browser em modo de demonstração (AGT simulada; ainda sem credenciais).

## Documentos emitidos no POS
| Venda | Documento AGT | Origem |
|---|---|---|
| Venda normal (consumidor final ou cliente com NIF) | **TV** Talão de Venda | `pos.order` |
| Devolução de uma venda com talão | **NC** Nota de Crédito ao talão | `pos.order` |
| Venda facturada, paga no acto | **FR** Factura/Recibo | `account.move` gerada pelo POS |
| Venda facturada a crédito («Conta do Cliente») | **FT** Factura (o recibo RC sai no pagamento) | `account.move` |
| Devolução de uma venda facturada | **NC** sobre a factura | `account.move` |

- **Numeração no servidor**, na série AGT da empresa, com o mesmo bloqueio de linha das facturas: não há falhas nem duplicados, mesmo com vários postos.
- **O talão só se imprime depois de o servidor atribuir o número**: o POS espera pela sincronização.
- **Envio à AGT:** os talões entram na fila das facturas e dos recibos (lotes de 30, polling, contingência, bloqueio aos 60 dias). Uma NC só segue depois de a AGT ter recebido o talão de origem.
- **Abertura de sessão:** não é possível abrir o POS sem séries TV e NC activas.

## Regras aplicadas na venda
- Todos os produtos têm de ter imposto com classificação AGT.
- Quantidades negativas só são aceites em devoluções, feitas com «Reembolsar» no talão original.
- **Devolução:**
  - pede o motivo (art. 8.º), com uma lista de motivos e texto livre até 60 caracteres;
  - não pode misturar vendas;
  - a devolução de um talão não pode ser facturada, e a devolução de uma factura tem de o ser.
- **Uma venda com talão não pode ser facturada mais tarde**, o que evitaria comunicar a mesma venda duas vezes. Por isso o convite à auto-facturação («Precisa de factura?») desaparece dos talões AGT.
- **Bloqueios:** uma venda com documento comunicado não se cancela nem se apaga.

## Talão impresso
- **Cabeçalho:**
  - tipo e número AGT, por exemplo «Talão de Venda TV TV26…/1»;
  - **«Original»** ou **«2.ª via»**;
  - referência interna;
  - «Consumidor final» quando não há cliente.
- **Rodapé:**
  - «Referente a TV …/1 (motivo)» nas NC;
  - QR Code AGT;
  - menção de contingência;
  - «Processado por programa validado n.º …/AGT»;
  - NIF do emitente, que já vinha do Odoo.
- **Contagem das impressões:** cada impressão do documento AGT fica registada no servidor (`l10n_ao_edi_print_count`). A primeira é o Original; as reimpressões, no POS ou no backend, saem como 2.ª via.
- **Sem ligação ao servidor:** o POS continua a vender e imprime **«DOCUMENTO PROVISÓRIO: NÃO SERVE DE FACTURA»**. O talão certificado é numerado quando a ligação volta e imprime-se nos Pedidos do POS, como Original.

## «Original» / «2.ª via» no backend (pendente da 2b)
As facturas, notas de crédito e de débito e os recibos RC passam a mostrar a menção junto ao título. Cada PDF gerado conta como uma impressão: o primeiro, normalmente o enviado ao cliente, é o Original e os seguintes são 2.ª via.

## Alterações ao `l10n_ao_edi`
- **Fila de envio genérica** (`l10n_ao_edi.document._queue_fields`). Cada modelo com documentos AGT (facturas, recibos, talões) regista-se na fila e implementa `_l10n_ao_edi_ready_to_send`. Na mesma operação foram generalizados o bloqueio aos 60 dias e o simulador.
- **Envio pelo cron:** a pesquisa da fila faz-se com privilégios de sistema. Um contabilista sem acesso ao POS consegue enviar as facturas mesmo havendo talões na fila.

## Teste no browser (base `kututa_demo`)
- **Loja:** «Kitanda Loja», com Numerário (Caixa 45.1.01) e Multicaixa (43.1.01). Séries TV26DEMOSEDEN, TV26DEMOSEDEC e NC26DEMOSEDEC.
- **Venda** de 2 × Sumo natural: 2.280 Kz com IVA 14%. Saiu o talão «TV TV26DEMOSEDEN/1», Original, com QR, programa validado e «Consumidor final», e ficou **válido** na AGT simulada.
- **Reembolso** de 1 unidade: o POS pediu o motivo e emitiu «NC NC26DEMOSEDE/2» «Referente a TV TV26DEMOSEDEN/1 (Sumo fora do prazo)». A NC partilha a série de NC das facturas.
- **Reimpressão:** passa a «2.ª via».
- **Talão sem ligação:** sai a menção de documento provisório.

## Observações
- **Valor de «Troco» sem formatação no talão da devolução** («Change: 1140»): o modelo do Odoo usa `amount_return` em bruto. Não é deste módulo; a rever se incomodar.
- **Uma só série TV por empresa e ano**, partilhada pelos postos, porque o número é atribuído no servidor. Séries por posto só serão precisas se a AGT o exigir, e isso fica para confirmar em homologação.
- **A confirmar em homologação AGT:**
  - se o TV aceita `customerTaxID` com NIF de cliente (hoje é enviado quando existe);
  - o formato de `unitPrice` com descontos.

## Fica para mais tarde
| Tema | Motivo |
|---|---|
| Talões de restaurante (consulta de mesa, pré-conta) | Exige regras próprias (documento de conferência); fora do âmbito da 2c |
| Envio do talão por email/SMS com o PDF AGT | O envio do Odoo funciona; falta um modelo de email próprio |
| `anularFactura` | A AGT ainda não publicou a especificação |
