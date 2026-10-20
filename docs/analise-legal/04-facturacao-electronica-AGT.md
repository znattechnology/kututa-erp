# Facturação Electrónica AGT: verificação e especificação técnica

Data: 2026-10-20 · Complementa [01-faturacao-DP-71-25.md](01-faturacao-DP-71-25.md)

## 1. O DP 71/25 já prevê a facturação electrónica? Sim

O DP 71/25 dedica-lhe um capítulo (arts. 16.º–21.º) e as disposições finais (arts. 36.º–38.º).

| Art. | Regra |
|---|---|
| 16.º | **Obrigatória** para os contribuintes dos Regimes **Geral e Simplificado do IVA**. O Regime de Exclusão pode aderir voluntariamente. |
| 17.º | Emissão por software **validado/certificado pela AGT**, com transmissão **em tempo real**. O software comunica a actividade a cada 2 meses e **bloqueia a emissão** se a comunicação falhar durante mais de 60 dias. |
| 18.º | **Contingência**: emissão offline com a menção «emitido em contingência, pendente de autorização», submissão posterior e aviso imediato à AGT. |
| 19.º | Autenticidade e integridade garantidas por **código digital definido pela AGT** (na prática, as assinaturas JWS). |
| 20.º | Mantêm-se as menções obrigatórias do art. 10.º. |
| 21.º | O adquirente **confirma electronicamente** as notas de crédito (serviço `validarDocumento`). |
| 36.º | Especificações técnicas remetidas para Decreto Executivo: o **Decreto Executivo n.º 683/25, de 22/08/2025** (DR I Série n.º 159). |
| 37.º | 1.º ano: só Grandes Contribuintes e fornecedores do Estado; depois, **todos**. Até lá, os restantes usam software certificado. |
| 38.º | Operações de **25 000 000 Kz ou mais** têm sempre de ter factura electrónica ou ser emitidas no Portal do Contribuinte. |

## 2. Calendário em vigor (fontes: AGT e imprensa, Maio de 2026)

| Data | Quem |
|---|---|
| 01/10/2025 – 31/12/2025 | Período transitório, sem penalizações |
| **01/01/2026** | Obrigatória e exclusiva para os **Grandes Contribuintes** e os **fornecedores do Estado** |
| **até 31/12/2026** | Empresas com facturação ≥ 25 M Kz |
| **01/01/2027** | **Todos os contribuintes dos Regimes Geral e Simplificado do IVA** |

Em 06/05/2026 o presidente da AGT, José Leiria, declarou que **«não haverá prorrogação do prazo»**. Na altura, mais de 46 mil empresas já emitiam factura electrónica.

> ⚠️ **Hoje (20/10/2026) faltam cerca de 2,5 meses para a obrigação geral.** A facturação electrónica deixa de ser "fase 2" e passa a ser o **caminho crítico** do projecto.

## 3. Especificação técnica (Quiosque AGT, documentação oficial)

Fonte: https://quiosqueagt.minfin.gov.ao/doc-agt/doc-agt/2/index.html (v2) e `.../doc-agt/faturacao-electronica/1/` (v1). Há uma cópia em texto em [`docs/referencias/agt-facturacao-electronica/`](../referencias/agt-facturacao-electronica/).

### 3.1 Arquitectura
- **REST e JSON**, `schemaVersion` "2.0". O processamento é **assíncrono**: o `registarFactura` devolve um `requestID` e o estado consulta-se depois com `obterEstado` (polling; o callback está anunciado para versões futuras).
- **Ambientes:**
  - homologação: `https://sifphml.minfin.gov.ao/sigt/fe/v1/…`
  - produção: `https://sifp.minfin.gov.ao/sigt/fe/v1/…`
- **Autenticação:** HTTP **Basic Auth**, com credenciais pedidas por email a `produtores.dfe.dcrr.agt@minfin.gov.ao` (indicar nome e NIF da empresa produtora).
- **Portal do Parceiro**, onde se regista o software e as chaves públicas:
  - testes: `portaldoparceiro.hml.minfin.gov.ao`
  - produção: `portaldoparceiro.minfin.gov.ao`

### 3.2 Serviços

| Serviço | Uso no Odoo |
|---|---|
| `registarFactura` | Envio de até **30 documentos** por chamada |
| `obterEstado` | Cron de polling até ao estado final (válido/inválido) |
| `solicitarSerie` / `listarSeries` / `estenderSerie` | Séries por tipo de documento, ano e estabelecimento (`SEDE` se houver um só) |
| `anularFactura` | Anulação de documento já aceite |
| `validarDocumento` | Confirmar ou rejeitar facturas recebidas (compras), com % de IVA dedutível |
| `consultarFactura` / `listarFacturas` | Reconciliação e auditoria |
| `comunicarInventario` / `submeterInventario` | Inventário anual de existências |
| `comunicarServicosEstrangeiro` | Serviços adquiridos no estrangeiro |

### 3.3 Assinaturas digitais (JWS **RS256**, RSA ≥ 2048 bits, Base64URL sem padding)

| Assinatura | Chave | Payload assinado |
|---|---|---|
| `jwsSoftwareSignature` | **Do produtor**, gerada localmente; a pública é registada no Portal do Parceiro | `{productId, productVersion, softwareValidationNumber}` |
| `jwsDocumentSignature` | **Do contribuinte**, emitida pela AGT no Portal do Contribuinte | `{documentNo, taxRegistrationNumber, documentType, documentDate, customerTaxID, customerCountry, companyName, documentTotals}` |
| `jwsSignature` | Do contribuinte | Campos-chave de cada pedido (ex. `{taxRegistrationNumber, requestID}`) |

Usa-se JSON canónico (sem espaços nem quebras de linha). O Odoo já traz RSA-SHA256 com PKCS#1 v1.5 em `odoo/addons/certificate/models/key.py` (`_sign`, `_sign_with_key`). Falta só montar o JWS compacto `base64url(header).base64url(payload).base64url(sig)`. **Não é preciso nenhuma biblioteca nova.**

### 3.4 Modelo de dados do documento (resumo)
- **`documentNo`:** formato SAF-T, `"<tipo> <série>/<n.º>"` (ex. `FT FT6325S2C/10006`), sem zeros à esquerda no n.º sequencial.
- **`documentType`:**

  | Grupo | Códigos |
  |---|---|
  | Facturas | FT, FR, FA (adiantamento), FG (global), GF (genérica) |
  | Avisos de cobrança | AC, AR |
  | Talão de venda | TV |
  | Recibos | RC, RG, RE |
  | Notas | ND, NC |
  | Autofacturação | AF |
  | Seguros | RP, RA, CS, LD |
- **`documentStatus`:** N (normal) ou C (correcção de um documento rejeitado, com `rejectedDocumentNo`).
- **Linhas:**
  - `operationType`, que é **novo** e obrigatório: SE, SS, STP, SR, SIF, SHS, ST, SG, TB, AS, QT, RD;
  - `unitPriceBase` e `unitPrice`;
  - `debitAmount` ou `creditAmount`;
  - `settlementAmount`;
  - `referenceInfo`, obrigatório nas NC.
- **Impostos por linha:**
  - `taxType`: IVA, IS, IEC, CEOC ou NS;
  - `taxCountryRegion`: AO ou **AO-CAB** (Cabinda);
  - `taxCode`: NOR, INT, RED, ISE ou OUT;
  - `taxExemptionCode`, obrigatório se o imposto for ISE ou NS;
  - `taxContribution`, **arredondado sempre por excesso ao cêntimo**, o que difere do arredondamento do Odoo.
- **Recibos (RC/RG/AR):** sem linhas, com `paymentReceipt.sourceDocuments`.
- **`withholdingTaxList`:** IRT, II, IS, IVA (cativo), IP, IAC, …
- **`currency`:** só em moeda estrangeira ou em exportações; o contravalor é validado com arredondamento matemático.
- **Cliente sem NIF:** `customerTaxID = "999999999"`.

### 3.5 QR Code no documento impresso
- **Formato:** QR Model 2, versão 4, correcção M, UTF-8, PNG 350×350, com logótipo AGT ocupando menos de 20 %.
- **URL:** `https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?emissor=<NIF>&document=<documentNo>`, com os espaços convertidos em `%20`.

### 3.6 Anexos (dados mestre para o `l10n_ao`)
Tabelas oficiais no anexo da v2:
- Códigos de Actividade Económica (CAE);
- taxas do IEC;
- verbas e taxas do Imposto de Selo;
- **códigos de isenção de IVA (M10…), de IS e de IEC**.

Isto resolve parte das "fontes externas" que estavam em falta.

## 4. Impacto no plano

1. **Certificação, que não é código.** Quem distribui o software tem de se registar como **produtor de software** na AGT, certificar o produto (e obter o `softwareValidationNumber`), pedir as credenciais e registar a chave pública. **Isto leva tempo e deve começar já, em paralelo com o desenvolvimento.**
   - **Alternativa:** um integrador já certificado, em que o Odoo envia os dados a um intermediário. É mais rápido, mas cria dependência e custo.
2. **Novo módulo, `l10n_ao_edi`, prioritário** (antes era "fase 5):
   - Modelo `l10n_ao.series`: séries AGT por tipo de documento, ano e estabelecimento, com o estado e o intervalo autorizado.
   - Em `account.move`:
     - campos novos: tipo de documento AO, `requestID`, estado AGT, erros, assinatura, QR;
     - fila de envio, com lotes de até 30 documentos e um cron de `obterEstado`;
     - modo de contingência;
     - bloqueio da emissão ao fim de 60 dias sem comunicação.
   - Em `account.tax`: `taxType`, `taxCode` e o código de isenção AGT.
   - Em `product` / `account.move.line`: `operationType`.
   - Recibos (RC) gerados a partir de `account.payment`.
   - `validarDocumento` para as facturas de fornecedor.
   - Referência de implementação no próprio Odoo: `l10n_es_edi_verifactu` (fila, estados, QR) e `l10n_sa_edi` (assinaturas por diário).
3. **Roadmap revisto:**
   - **Fase 1:** `l10n_ao` (PGC, impostos com os códigos AGT, isenções do anexo, AOA).
   - **Fase 1b, em paralelo:** processo de certificação na AGT.
   - **Fase 2:** `l10n_ao_invoicing` e **`l10n_ao_edi`** juntos, testados em homologação (`sifphml`), com a meta de produção **antes de 01/01/2027**.
   - **Fase 3:** `l10n_ao_saft`.
   - **Fase 4:** RH e salários.
   - **Fase 5:** demonstrações financeiras.

## 5. Ainda por obter
- **Texto integral do Decreto Executivo n.º 683/25.** O DR é pago e a documentação da AGT parece reflecti-lo, mas convém ter o diploma.
- **Regulamento e processo de certificação de software da AGT:** requisitos funcionais e testes de homologação.
- **Esquema XSD do SAF-T (AO)**, para a fase 3.

## Fontes
- Documentação oficial da API AGT, v2: https://quiosqueagt.minfin.gov.ao/doc-agt/doc-agt/2/index.html · v1: https://quiosqueagt.minfin.gov.ao/doc-agt/faturacao-electronica/1/index.html
- AGT, «Factura electrónica: o que mudará na gestão fiscal das empresas em 2026»: https://agt.minfin.gov.ao/PortalAGT/#!/sala-de-imprensa/noticias/14792/factura-electronica-o-que-mudara-na-gestao-fiscal-das-empresas-em-2026
- Decreto Executivo n.º 683/25 (metadados): https://www.lexlink.eu/conteudo/angola/ia-serie/4106155/decreto-executivo-no-68325/14793/por-tema
- Expansão, «Obrigatoriedade… só arranca a 01 de Outubro»: https://expansao.co.ao/angola/detalhe/facturacao-electronica-so-arranca-a-01-deobrigatoriedade-de-emissao-de-facturacao-electronica-so-arranca-a-01-de-outubro-outubro-67435.html
- Mercado, 07/05/2026, «Sem prorrogação, AGT dá até 31 de Dezembro…»: https://mercado.co.ao/sem-prorrogacao-agt-da-ate-31-de-dezembro-para-todas-as-empresas-aderirem-a-factura-electronica/
- Economia & Mercado, 06/05/2026, «Não haverá prorrogação do prazo»: https://www.economiaemercado.com/artigo/nao-havera-prorrogacao-do-prazo-de-obrigatoriedade-de-facturacao-electronica-avisa-a-agt
- Novo Jornal, «AGT começa a aplicar facturação electrónica em 1 de Janeiro de 2026»: https://www.novojornal.co.ao/economia/detalhe/agt-comeca-a-aplicar-facturacao-electronica-em-1-de-janeiro-de-2026-68608.html
