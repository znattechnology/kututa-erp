# Fase 2a: Kututa Mukanda (`l10n_ao_edi`), núcleo da facturação electrónica AGT

**Estado:** concluída a 2026-10-20. Testes: 27 (`make test m=l10n_ao_edi`) + 27 no `l10n_ao`, 0 falhas. Testado no browser em modo de demonstração.

## O que faz

**Configuração por empresa** (Empresa › separador «Facturação electrónica (AGT)»):
- activação;
- ambiente: **Demonstração** (respostas simuladas, nada é enviado), Homologação (`sifphml`) ou Produção (`sifp`);
- credenciais da API (Basic Auth);
- dados do software certificado (`productId`, `productVersion`, `softwareValidationNumber`);
- chave privada do **produtor** (assina `jwsSoftwareSignature`) e do **contribuinte** (assina `jwsDocumentSignature` e `jwsSignature`), guardadas como `certificate.key`;
- estabelecimento.

**Séries AGT** (Facturação › Configuração › Angola (AGT) › Séries AGT):
- uma série por tipo de documento, ano e estabelecimento;
- «Pedir série à AGT» (`solicitarSerie`), ou introdução manual do código obtido no Portal do Contribuinte;
- a reserva de números é feita com bloqueio da linha (`SELECT … FOR UPDATE`), por isso não há falhas nem duplicados.

**Numeração no formato AGT:** `FT FT26S1/1`, `NC NC26S1/1`, sem zeros à esquerda e sem reinício anual. O rascunho mostra o próximo número.

**Tipos de documento:**
- FT (por omissão);
- FR e FA (escolha no separador «Outra informação»);
- NC (notas de crédito);
- ND (notas de débito, módulo `account_debit_note`).

**Validações ao confirmar (DP n.º 71/25):**
- configuração AGT completa e série activa;
- NIF do cliente válido; sem NIF, o documento vai como consumidor final `999999999`;
- data de emissão não posterior a hoje (vazia = hoje, como no Odoo);
- todas as linhas com imposto classificado na AGT;
- NC: documento de origem já aceite pela AGT e **motivo obrigatório** (art. 8.º).

**Bloqueios:** um documento enviado ou válido não volta a rascunho, não se cancela e não se apaga: corrige-se com nota de crédito. Um documento **rejeitado** pode ser corrigido; ao confirmar recebe novo número e vai com `documentStatus = C` e `rejectedDocumentNo`.

**Envio e validação (assíncrono):**
- cron `registarFactura` em lotes de até 30, mais o botão «Enviar à AGT»;
- cron `obterEstado` com intervalos crescentes (1, 2, 5, 10, 30, 60 min);
- estados: A enviar → Enviado → Válido / Rejeitado (com os erros da AGT);
- cada pedido fica registado com o JSON enviado e a resposta (Comunicações AGT; auditoria exigida pelo Anexo III do DE 683/25).

**Assinaturas:** JWS compacto RS256 sobre JSON canónico, com as chaves do Odoo (`tools/jws.py`, verificação incluída nos testes).

**Documento impresso:**
- título com o tipo AGT («Factura FT …», «Nota de Crédito NC …»);
- «Data de emissão»;
- **QR Code** (`quiosqueagt…/consultar-fe?emissor=…&document=…`, nível M);
- «Processado por programa validado n.º …/AGT»;
- referência ao documento rejeitado que corrige.

**Arredondamento AGT** (no `l10n_ao`): imposto por linha arredondado por excesso, em Python e no ecrã. O total da factura coincide com o enviado.

## Problemas encontrados no teste visual e corrigidos
| Problema | Correcção |
|---|---|
| Sem data, a confirmação era recusada (o Odoo preenche-a com hoje) | Data vazia = hoje |
| QR code não aparecia: falta o backend de imagem do reportlab na instalação por pip (também na imagem Docker) | `rlPyCairo` + cairo (dev e Docker) |
| Título em inglês («Proforma Invoice»): o `pt.po` do `account_debit_note` do Odoo tem traduções vazias | Título próprio para documentos AGT |
| Motivo da NC cortado («Estorno de: FT…, …») | Campo próprio `l10n_ao_edi_reason` com o texto do utilizador |
| Ano mostrado como «2.026» | Sem separador de milhares no ano |
| «Mudar para Rascunho» visível em documentos comunicados | Escondido |
| Rascunho mostrava «RFT/2026/00001» | Mostra o próximo número AGT |
| OdooBot como autor das mudanças de estado | Mantém o utilizador |

## A confirmar em homologação AGT (precisa das credenciais)
1. A inclusão do `signatureVersion` em `softwareInfoDetail` (a tabela diz obrigatório, o exemplo não o tem). Hoje só é enviado se estiver configurado.
2. O cabeçalho JWS (`{"typ":"JOSE","alg":"RS256"}`, como nos exemplos da AGT).
3. Os campos assinados no `solicitarSerie` (o exemplo inclui `seriesContingencyIndicator`, a tabela não).
4. O URL do QR (a documentação v2 e o DE 683/25 diferem).
5. O código e a região da taxa de Cabinda.

## Fica para a Fase 2b / 2c
| Tema | Entrega |
|---|---|
| Recibos (RC) a partir dos pagamentos; retenções na fonte (`withholdingTaxList`) | 2b |
| `anularFactura`, `listarSeries`, `estenderSerie`, `consultarFactura` | 2b |
| Contingência (série C, menção «pendente de autorização») e bloqueio aos 60 dias sem comunicação | 2b |
| `validarDocumento` nas facturas de fornecedor | 2b |
| «Original» / «2.ª via» nas impressões; logótipo AGT no QR | 2b |
| Talões no POS (TV/FR) | 2c |
