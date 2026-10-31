# Homologação AGT: guia e perguntas em aberto

O pedido de registo como produtor (Vímeo, NIF 5003603490) foi enviado à AGT a 31/10/2026 (ver `email-pedido-registo-produtor.md`).

## 1. O que já está pronto no Kututa (`l10n_ao_edi`)

- Todos os serviços da API: solicitarSerie, listarSeries, registarFactura, obterEstado e validarDocumento.
- Assinaturas JWS RS256: do software, do documento e do pedido.
- Envio por lotes e consulta do estado.
- NC, ND, recibos, contingência, bloqueio ao fim de 60 dias, 2.ª via e QR.
- **Homologação sem número de certificação.** Fora da produção, o `softwareValidationNumber` não é obrigatório, porque só existe depois de o software ser certificado.
- **Botão «Testar ligação à AGT»** (Empresa › Facturação electrónica). Verifica a configuração e faz um `listarSeries`, que não altera nada na AGT.
- **Chave pública do produtor** visível na ficha da empresa, pronta a copiar para o Portal do Parceiro.
- Especificação revista contra a documentação publicada a 31/10/2026, guardada em `docs/referencias/agt-facturacao-electronica/2026-10-31/`.

## 2. Passos quando chegarem as credenciais

1. **Portal do Parceiro de testes** (https://portaldoparceiro.hml.minfin.gov.ao/): registar o software «Kututa ERP» e carregar a chave pública do produtor. É o ficheiro `~/.kututa/agt-produtor/homologacao/kututa-agt-hml-publica.pem`, que nunca vai para o git.
2. **Portal do Contribuinte de testes:** obter a chave do contribuinte da empresa de testes, que é emitida pela AGT.
3. **Numa base de homologação, nunca na de produção:**
   - carregar as duas chaves privadas em Definições › Técnico › Chaves;
   - na empresa, escolher o ambiente «Homologação (testes)» e preencher as credenciais da API;
   - deixar o n.º de certificação vazio;
   - carregar em **«Testar ligação à AGT»**.
4. Pedir as séries (FT, FR, NC, ND, RG e as de contingência) e correr os cenários da secção 3.

## 3. Cenários de teste (a confirmar com a lista oficial da AGT)

| # | Cenário | Serviços |
|---|---|---|
| 1 | Factura FT com IVA 14 %, para um cliente com NIF | solicitarSerie, registarFactura, obterEstado |
| 2 | Factura-recibo FR para consumidor final (999999999) | registarFactura |
| 3 | Factura isenta (M-code) e factura com IS/IEC | registarFactura |
| 4 | Factura em moeda estrangeira (USD), com contravalor | registarFactura |
| 5 | Nota de crédito NC com motivo e referência | registarFactura |
| 6 | Nota de débito ND | registarFactura |
| 7 | Recibo de um pagamento, incluindo um com retenção na fonte | registarFactura |
| 8 | Documento rejeitado, corrigido e reenviado | obterEstado, registarFactura |
| 9 | Contingência: emitir offline e enviar ao sair | registarFactura |
| 10 | Talão TV no POS | registarFactura |
| 11 | Confirmar e rejeitar uma factura de fornecedor | validarDocumento |
| 12 | Sincronizar as séries | listarSeries |

## 4. Perguntas para a AGT

1. **Recibos: RC ou RG?** A documentação actual define RC como «Recibo Emitido» e RG como «Outros Recibos Emitidos», e deixou de ter a nota do regime de caixa. O Kututa emite RG, e o SAF-T (AO) reserva o RC para o regime de IVA de caixa. Qual é o tipo correcto para os recibos normais?
2. **Assinatura do `validarDocumento`.** O texto diz que se assinam o `taxRegistrationNumber` e o `documentNo`, mas o exemplo «Payload assinatura» inclui também `action` e `deductibleVATPercentage`. O Kututa segue o exemplo. Qual dos dois está certo?
3. **Na homologação**, que valor se põe em `softwareValidationNumber` antes de haver certificação?
4. **`signatureVersion`:** é obrigatório? Com que valor se começa?
5. **URLs de homologação:** algumas páginas mostram `/sigt/fe/ws/v1/` e outras `/sigt/fe/v1/`. O Kututa usa `/sigt/fe/v1/`.
6. **Documentos e requisitos da certificação:** lista de testes, prazos e se é preciso o XSD do SAF-T (AO).

## 5. Alterações da especificação detectadas a 31/10/2026

- **`validarDocumento`:** os campos `deductAllVAT`, `deductVATLines` e `applyProRata` foram substituídos por `deductibleVATPercentage` (0–100) ou `nonDeductibleAmount`. **Já foi corrigido no Kututa:** envia a percentagem do IVA lançado na conta de IVA dedutível, e só nas confirmações de facturas.
- **`registarFactura`:** o tipo RC passou a «Recibo Emitido» e o RG a «Outros Recibos Emitidos». O `taxContribution` continua arredondado por excesso, e o Kututa já o faz.
- **`consultarFactura` / `listarFacturas`:** a resposta ficou reduzida (saíram `customerAcceptance`, `referenceList` e `paymentList`). O Kututa não usa estes serviços.
