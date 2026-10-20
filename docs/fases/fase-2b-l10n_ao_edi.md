# Fase 2b: recibos, contingência, fornecedores e séries (`l10n_ao_edi`)

> **Revisto na auditoria de 2026-10-20** (`auditoria-fase-2.md`): os recibos passaram a **RG (Recibo Geral)**, porque na especificação o RC é o recibo do regime de caixa do IVA. Os recibos ficam fixados na emissão e a desconciliação é bloqueada. Os recibos rejeitados podem ser corrigidos. As retenções também são possíveis em numerário.

**Estado:** concluída a 2026-10-20. Testes: 64 nos dois módulos (`make test m=l10n_ao,l10n_ao_edi`), 0 falhas. Testado no browser em modo de demonstração (AGT simulada; ainda sem credenciais).

## Recibos (RC): art. 6.º do DP n.º 71/25
- **Emissão:** cada recebimento de clientes que liquida facturas AGT (FT, FA, FG, GF, ND) emite um recibo `RC <série>/<n.º>`.
  - É automático ao registar o pagamento pelo assistente «Pagar».
  - Também há o botão «Emitir recibo AGT», para pagamentos reconciliados mais tarde.
- **Excepções:** a Factura/Recibo (FR) não gera recibo, porque já é o recibo. A NC não é paga.
- **Estrutura enviada** (`paymentReceipt.sourceDocuments`):
  - cada linha tem a factura de origem, a data e o valor sem imposto liquidado;
  - nos pagamentos parciais os valores são proporcionais;
  - os totais (`taxPayable`, `netTotal`, `grossTotal`) correspondem ao liquidado.
- **Retenções na fonte e cativações** (`withholdingTaxList`):
  - lidas das linhas do pagamento lançadas em contas com tipo de retenção AGT;
  - 34.1.2 → **II** (Imposto Industrial 6,5% sofrido);
  - 34.2.4 → **IVA** cativo.
  - No assistente «Pagar»: valor recebido líquido, depois «Marcar como Completamente Pago» com a conta 34.1.2.
- **Envio:** o recibo só segue para a AGT depois de a factura de origem ter sido recebida. Se seguisse antes, a AGT rejeitava-o por referência desconhecida (E14).
- **Bloqueio:** um pagamento com recibo comunicado não volta a rascunho, não se cancela e não se apaga.
- **Recibo impresso:** «Recibo RC …», QR code da AGT, programa validado, linha da retenção.

## Contingência: art. 18.º
- **Activação:** Empresa › Facturação electrónica (AGT) › «Modo de contingência». Fica registada a hora de início.
- **Durante a contingência:**
  - os documentos são numerados na **série de contingência** (pedida à AGT com o indicador C);
  - levam a menção **«Emitido em contingência, pendente de autorização»** no ecrã e no documento impresso;
  - **não são enviados**.
- **No fim:** ao desligar o modo, a fila é enviada de imediato.

## Bloqueio aos 60 dias: art. 17.º, n.º 5
A emissão de facturas e recibos é recusada quando há documentos por comunicar há mais de 60 dias e não houve comunicação bem-sucedida com a AGT nesse período.

## Facturas de fornecedor: `validarDocumento`
- **Campo** «N.º AGT do documento do fornecedor» (por omissão, a referência da factura).
- **Botões** «Confirmar na AGT» e «Rejeitar na AGT» (este com confirmação).
- **Dedutibilidade** (`deductAllVAT`, v2): **AD** se todo o IVA da factura foi para IVA dedutível (34.2.3), **ND** caso contrário.
- **Resultado:** o estado fica registado (Confirmado / Rejeitado). As recusas da AGT (`C_NOK` / `R_NOK`) mostram os erros.

## Séries
- «Sincronizar com a AGT» na lista de séries (`listarSeries`) importa as séries registadas na AGT que ainda não existem no Odoo.
- O simulador passou a gerar códigos distintos para séries normais e de contingência (sufixo N/C, como nos exemplos da AGT).

## Correcções encontradas no teste visual
| Problema | Correcção |
|---|---|
| O assistente «Pagar» não mostrava a «Diferença de Pagamento», onde se lança a retenção: o Odoo 20 só a mostra quando o método de pagamento tem conta de valores em trânsito, e por omissão não a liga | O `l10n_ao` liga 48.1/48.2 aos métodos de pagamento dos bancos (como o `l10n_ma`) |
| Séries normal e de contingência com o mesmo código no simulador | Sufixo N/C |
| Clientes já instalados não recebiam o tipo de retenção nas contas, nem as contas de trânsito nos bancos | Script de migração `l10n_ao` 20.0.1.1.0 |

## Fica para mais tarde
| Tema | Motivo / entrega |
|---|---|
| `anularFactura` | A AGT ainda não publicou a especificação do serviço |
| «Original» / «2.ª via» | Feito na 2c (`fase-2c-l10n_ao_edi_pos.md`) |
| `consultarFactura`, `listarFacturas`, `estenderSerie` | Consulta/auditoria; sem impacto na emissão |
| Recibos de NC compensadas com facturas (RE / regularizações) | A clarificar com a AGT |
