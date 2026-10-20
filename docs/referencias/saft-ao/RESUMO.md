# SAF-T (AO): resumo para o `l10n_ao_saft`

Fontes: `SAFTAO1.01_01.xsd` (master assoft, 2024-10-16) e Anexo do **DE 317/20** (estrutura de dados em vigor; substitui o anexo do DP 312/18). A árvore completa, com tipos e facetas, está em `arvore-xsd.txt`.

Notação: `[1]` obrigatório · `[0..1]` opcional · `[0..n]`/`[1..n]` repetível · `choice` = um dos dois.

**Fonte das afirmações:**
- *XSD* = validado pelo esquema.
- *DE* = regra textual do DE 317/20 que o XSD não valida.
- ⚠ = incerto.

---

## 1. Enquadramento legal (estado em Out/2026)

| Ficheiro | Base legal | Periodicidade e prazo | Situação |
|---|---|---|---|
| **SAF-T de facturação** (tipo F / "Aquisição de bens e serviços" A) | DP 312/18, art. 3.º/1: ficheiro mensal do mês anterior, "até ao último dia do mês seguinte". DP 71/25, art. 25.º: os regimes simplificado e geral do IVA comunicam facturas, recibos e outros documentos "em formato SAF-T". | Mensal, pelo DP 312/18 | **Dispensado para quem emite facturação electrónica** (comunicado AGT de 20/03/2026; a informação já chega em tempo real pelo art. 16.º e seguintes do DP 71/25). ⚠ O DP 71/25 (art. 40.º/2) derrogou os n.os 1 e 5 do art. 2.º do DP 312/18, o âmbito para o qual o art. 3.º remete. A periodicidade mensal para quem não emite facturas electrónicas fica assim sem confirmação expressa. |
| **SAF-T de contabilidade** (tipo C ou I) | DP 71/25, art. 24.º/1 e) | **Anual**: exercício anterior, até **10 de Abril** | Exercício 2025 facultativo e sem coimas (comunicado AGT de 15/04/2026). **Obrigatório para o exercício de 2026, a entregar até 10/04/2027.** A estrutura é a do DE 317/20 (cabeçalho, tabelas mestres e movimentos). |
| **SAF-T de inventários** | DP 71/25, art. 24.º/1 d) | Anual: existências a 31/12, até **15 de Fevereiro** | A estrutura **não é a do XSD SAFTAO**. Segue a Circular n.º 05/GACA/GJ/DSF/AGT/2026 (resumo abaixo). Em 2025 o prazo foi prorrogado até 15/04/2026. |
| Pedido avulso da AGT | DP 312/18, art. 3.º/2; DP 71/25, art. 23.º/2 b) | A qualquer momento | — |

**Coimas** (DP 71/25, art. 35.º):
- n.º 11: SAF-T com documentos omitidos.
- n.º 12: SAF-T não submetido em mais de 3 períodos consecutivos (coima a partir do 4.º).
- n.º 13: Kz 600 000 por período ao **produtor de software**, se a falha de submissão lhe for imputável.

**Validação de software** (DP 312/18, art. 7.º):
- Cifra assimétrica com chave privada exclusiva do produtor.
- Produtor residente ou representado em Angola.
- Certificado válido 24 meses (art. 9.º/5).

⚠ **O algoritmo e a mensagem do Hash não constam do XSD nem do DE 317/20.** Estão no DE 74/19, de 6 de Março (requisitos técnicos de validação), que **não foi obtido**.

**Inventário** (Circular 05/2026), em XML, JSON ou Excel pelo Portal do Contribuinte:
- `StockHeader`: Assinatura (500), TaxRegistrationNumber, DateCreated, SoftwareValidationNumber, ProductID, ProductVersion, Ano (4) e "Sem operações" (Sim).
- `Stock`: Método de custeio (FIFO/LIFO/CMP) e Tipo de produto (M/P/A/S/T/B).
- Também em `Stock`: ProductCode (o mesmo da facturação), ProductDescription, Quantity, UnitOfMeasure e Valor.
- ⚠ O OCR deixou os nomes de alguns campos incompletos: confirmar no PDF.

## 2. Regras gerais (DE 317/20, notas do Anexo)

- **Namespace:** `urn:OECD:StandardAuditFile-Tax:AO_1.01_01`. Raiz `AuditFile`. `AuditFileVersion` = `1.01_01` (padrão fixo, *XSD*).
- **Período anual de tributação:** o ficheiro cobre o ano, total ou parcial, desde o início até ao termo ou até à data de geração.
- **Unicidade:**
  - O SAF-T de contabilidade é único por período.
  - O de facturação pode ser um por estabelecimento, se este facturar de forma independente.
- **Exportação de vários meses:** em casos justificados, as tabelas 2.2–2.5 (e 2.1 e 3, se o sistema for integrado) podem ir só no último período.
- **Datas:**
  - `AAAA-MM-DD`.
  - Data e hora `AAAA-MM-DDThh:mm:ss`, **sem fuso horário e sem milissegundos**.
- **Não há valores negativos** (`minInclusive=0` em todos os montantes):
  - o sinal exprime-se por Debit/Credit;
  - os restantes montantes vão em valor absoluto.
- **Totais dos documentos** (`TaxPayable`, `NetTotal`, `GrossTotal`, `DeductibleAmount` e `TaxBase` de Deductible): padrão `\d+(\.\d{2})`, ou seja, **exactamente 2 casas decimais** (*XSD*).
- **Moeda:**
  - `Header/CurrencyCode` ∈ {AOA, USD} no XSD; o DE manda "AOA".
  - A estrutura `Currency` (ISO 4217, CurrencyAmount, ExchangeRate) só se gera quando a moeda do documento ≠ AOA.
  - Nunca se usa "Kz" no XML.
- **Tipos de ficheiro (`TaxAccountingBasis`) e tabelas que cada um leva:**

| Código | Tipo | Tabelas |
|---|---|---|
| I | Contabilidade integrada com facturação | 1, 2.1–2.5, 3, 4.1, 4.3, 4.4, 4.5 |
| C | Contabilidade | 1, 2.1, 2.2, 2.3, 2.5, 3 |
| F | Facturação | 1, 2.2, 2.4, 2.5, 4.1, 4.3, 4.4 |
| P | Facturação parcial | ⚠ o DE não lista as tabelas |
| R | Recibos | 1, 2.2, 2.5, 4.4 |
| S | Autofacturação | 1, 2.2, 2.4, 2.5, 4.1 (InvoiceStatus = "S") |
| A | Aquisição de bens e serviços | 1, 2.3, 2.5, 4.5 |
| Q | Aquisição integrada com facturação | 1, 2.2, 2.3, 2.4, 2.5, 4.1, 4.3, 4.4, 4.5 |
| E | Facturação para o Estado | 1, 2.2, 4.1 |

- **MovementOfGoods (4.2):** existe no XSD, mas **não consta de nenhuma lista de tipos de ficheiro do DE 317/20** (só aparece "4.2 — Documentos de movimentação de mercadorias" no índice geral).

## 3. Header [1]

| Campo | Card. | Regra AO |
|---|---|---|
| AuditFileVersion | 1 | `1.01_01` |
| CompanyID | 1 | Registo comercial (máx. 50) |
| TaxRegistrationNumber | 1 | NIF angolano sem prefixo, 10–15 caracteres |
| TaxAccountingBasis | 1 | I, C, F, P, R, A, Q, S, E |
| CompanyName | 1 | 200 |
| BusinessName | 0..1 | 60 |
| CompanyAddress | 1 | BuildingNumber?, StreetName?, **AddressDetail**, **City**, PostalCode?, Province?, **Country fixo "AO"** |
| FiscalYear | 1 | Inteiro (regras do CII) |
| StartDate, EndDate, DateCreated | 1 | date |
| CurrencyCode | 1 | AOA (ou USD) |
| TaxEntity | 1 | Facturação: estabelecimento ou "Global". Contabilidade ou integrado: "Sede" (máx. 20) |
| **ProductCompanyTaxID** | 1 | NIF do **produtor do software** (máx. 20) |
| **SoftwareValidationNumber** | 1 | `\d+/AGT/\d{4}` (NNN/AGT/AAAA) ou "0" |
| ProductID | 1 | "Nome da aplicação/Nome da empresa produtora" (padrão `[^/]+/[^/]+`) |
| ProductVersion | 1 | 30 |
| HeaderComment, Telephone, Fax, Email, Website | 0..1 | — |

Diferenças face ao SAF-T PT:
- não há `SoftwareCertificateNumber`; o AO usa `SoftwareValidationNumber`;
- não há ATCUD;
- o Country da empresa é fixo "AO".

## 4. MasterFiles [1]

```
GeneralLedgerAccounts [0..n] > Account [1..n]
  AccountID [1] (máx. 30; todas as contas, incluindo integradoras)
  AccountDescription [1]
  OpeningDebitBalance, OpeningCreditBalance, ClosingDebitBalance, ClosingCreditBalance [1]
  GroupingCategory [1]  GR|GA|GM|AR|AA|AM   (1.º grau / agregadora / movimento; geral (G) ou analítica (A))
  GroupingCode [0..1]   conta-mãe do grau imediatamente superior (excepto no 1.º grau); keyref para AccountID
Customer [0..n]
  CustomerID [1] (único), AccountID [1] (conta-corrente ou "Desconhecido"),
  CustomerTaxID [1] (sem prefixo; "Consumidor final" → 999999999), CompanyName [1], Contact?,
  BillingAddress [1] (Country ISO-3166 ou "Desconhecido"), ShipToAddress [0..n],
  Telephone?, Fax?, Email?, Website?, SelfBillingIndicator [1] 0|1
Supplier [0..n]  (estrutura igual: SupplierID, AccountID, SupplierTaxID (20), ..., ShipFromAddress [0..n], SelfBillingIndicator)
Product [0..n]
  ProductType [1]  P|S|O|E|I   (E = Impostos Especiais de Consumo, IEC; I = outros impostos/taxas excepto IVA/IS)
  ProductCode [1] (único), ProductGroup?, ProductDescription [1],
  ProductNumberCode [1] (EAN, ou o ProductCode quando não há EAN), CustomsDetails? > UNNumber [0..n]
TaxTable [0..1] > TaxTableEntry [1..n]
  TaxType [1]  IVA|IS|NS
  TaxCountryRegion [0..1]  ISO-3166 + "AO-CAB" (Cabinda) + PT-AC/PT-MA
  TaxCode [1]  NOR|RED|INT|ISE|OUT|NS|NA|numérico   (IS → "ISE" segundo a doc.; "NA" = recibos sem imposto)
  Description [1], TaxExpirationDate?
  choice: TaxPercentage | TaxAmount
```

**TaxType** só admite `IVA`, `IS` e `NS`. **Não existe TaxType "IEC".** O IEC exprime-se de duas formas:
- produto com `ProductType="E"`;
- `Line/CustomsInformation/IECAmount`.

## 5. GeneralLedgerEntries [0..1]

```
NumberOfEntries [1], TotalDebit [1], TotalCredit [1]
Journal [0..n]: JournalID [1] (único, sem espaços, máx. 30), Description [1]
  Transaction [0..n]
    TransactionID [1]  "AAAA-MM-DD JournalID DocArchivalNumber" (padrão XSD, máx. 70, único)
    Period [1] 1..16, TransactionDate [1], SourceID [1], Description [1],
    DocArchivalNumber [1] (sem espaços, máx. 20),
    TransactionType [1]  N|R|A|J  (Normal / Regularizações / Apuramento de resultados / Ajustamento)
    GLPostingDate [1]
    choice[0..1]: CustomerID | SupplierID
    Lines [1]: primeiro DebitLine [1..n], depois CreditLine [1..n]
      RecordID [1], AccountID [1] (keyref), SourceDocumentID [0..1], SystemEntryDate [1],
      Description [1], DebitAmount / CreditAmount [1]
```

## 6. SourceDocuments [0..1]

### 4.1 SalesInvoices [0..1]

```
NumberOfEntries, TotalDebit, TotalCredit [1]
Invoice [0..n]
  InvoiceNo [1]  "<Tipo> <série>/<n.º>"  padrão `[^ ]+ [^/^ ]+/[0-9]+` (ex.: "FT S001/1"), único
  DocumentStatus [1]: InvoiceStatus N|S|A|R, InvoiceStatusDate (dateTime), Reason?, SourceID, SourceBilling P|I|M
  Hash [1] (máx. 172)       HashControl [1] (máx. 70) = versão da chave privada; "0" se o programa não for validado
  Period [0..1] 1..12, InvoiceDate [1]
  InvoiceType [1]  FT|FR|GF|FG|AC|AR|ND|NC|AF|TV|RP|RE|CS|LD|RA
  SpecialRegimes [1]: SelfBillingIndicator 0|1, CashVATSchemeIndicator 0|1,
                      ThirdPartiesBillingIndicator 0..3  (1 = por conta de terceiros; 2 = IVA cativo; 3 = ambos)
  SourceID [1], EACCode [0..1] (CAE, 5 dígitos), SystemEntryDate [1] (momento da assinatura)
  TransactionID [0..1] (# obrigatório se a contabilidade for integrada), CustomerID [1]
  ShipTo?, ShipFrom? (DeliveryID*, DeliveryDate?, WarehouseID/LocationID*, Address?), MovementEndTime?, MovementStartTime?
  Line [1..n]
    LineNumber, OrderReferences [0..n] (OriginatingON?, OrderDate?), ProductCode, ProductDescription,
    Quantity, UnitOfMeasure, UnitPrice (sem impostos, já com descontos), TaxBase? , TaxPointDate [1],
    References [0..n] (Reference?, Reason?)  ← nas NC, referência ao documento rectificado
    Description [1], ProductSerialNumber? > SerialNumber [1..n]
    choice: DebitAmount | CreditAmount
    Tax [1]: TaxType IVA|IS|NS, TaxCountryRegion?, TaxCode, choice TaxPercentage | TaxAmount
    TaxExemptionReason + TaxExemptionCode [0..1, em par]  ← obrigatórios quando a taxa é 0
    SettlementAmount? (descontos que afectam o GrossTotal)
    CustomsInformation? : ARCNo [0..n] (DU), IECAmount?
  DocumentTotals [1]: TaxPayable, NetTotal, GrossTotal (2 casas decimais),
    Currency? , Settlement [0..n] (SettlementDiscount?, SettlementAmount?, SettlementDate?, PaymentTerms?),
    Payment [0..n] (PaymentMechanism?, PaymentAmount, PaymentDate)
  WithholdingTax [0..n]: WithholdingTaxType IRT|II|IS|IVA|IPU|IAC|OU, Description?, Amount
```

**InvoiceType:**
- FT Factura · FR Factura/recibo · GF Factura genérica · FG Factura global
- AC Aviso de cobrança · AR Aviso de cobrança/recibo
- ND Nota de débito · NC Nota de crédito
- AF Factura/recibo (autofacturação) · TV Talão de venda
- Só para seguros: RP, RE, CS, LD, RA
- Não há o "FS" do PT.

**InvoiceStatus:** N Normal · S Autofacturação · A Anulado · R Resumo de documentos de outras aplicações.

**SourceBilling:** P Produzido na aplicação · I Integrado de outra aplicação · M Recuperação ou emissão manual.

**PaymentMechanism:** CC, CD, CH, CI, CO, CS, DE, MB (Multicaixa), NU, OU, PR, TB.

**TaxExemptionCode:**
- Padrão `(M[0-9]{2})+`; Reason com 6 a 60 caracteres.
- `TaxExemptions.xml` (2021) lista M00, M02, M04, M10–M24, M30–M38, M80–M86 e M90–M94.
- ⚠ A lista está desactualizada. Usar a lista oficial em vigor (anexos AGT ou DE 683/25).

⚠ **ThirdPartiesBillingIndicator:** o DE 317/20 só prevê 0 e 1. Os valores 2 e 3 (IVA cativo) vêm de uma revisão posterior do XSD. A documentação do XSD chama-lhe por engano "Indicador de regime de IVA de Caixa".

### 4.2 MovementOfGoods [0..1]

```
NumberOfMovementLines [1], TotalQuantityIssued [1]
StockMovement [0..n]
  DocumentNumber [1] (mesmo padrão), DocumentStatus: MovementStatus N|T|A|F|R, MovementStatusDate, Reason?, SourceID, SourceBilling
  Hash [1], HashControl [1], Period?, MovementDate [1]
  MovementType [1]  GR (remessa) | GT (transporte, incluindo globais) | GA (activos próprios) | GD (devolução)
  SystemEntryDate [1], TransactionID?, choice CustomerID | SupplierID, SourceID [1], EACCode?, MovementComments?
  ShipTo?, ShipFrom?, MovementEndTime?, MovementStartTime [1], AGTDocCodeID [0..1] (sem doc. ⚠)
  Line [1..n]: ... (sem TaxBase, TaxPointDate nem References), choice Debit|Credit,
       Tax [0..1]: TaxType IVA|NS, TaxCode RED|INT|NOR|ISE|OUT|NS|NA, TaxPercentage [1]; TaxExemptions?; SettlementAmount?; CustomsInformation?
  DocumentTotals [1]: TaxPayable, NetTotal, GrossTotal, Currency?
```

### 4.3 WorkingDocuments [0..1]

```
NumberOfEntries, TotalDebit, TotalCredit [1]
WorkDocument [0..n]
  DocumentNumber [1], DocumentStatus: WorkStatus N|A|F, WorkStatusDate, Reason?, SourceID, SourceBilling
  Hash [1], HashControl [1], Period?, WorkDate [1]
  WorkType [1]  CM|CC|GR|NR|FO|NE|OU|OR|PF|DC|RP|RE|CS|LD|RA|PP|GC
  SourceID [1], EACCode?, SystemEntryDate [1], TransactionID?, CustomerID [1]
  Line [1..n]: igual a SalesInvoices, mas com Tax [0..1]
  DocumentTotals [1]: TaxPayable, NetTotal, GrossTotal, Currency?
```

**WorkType:**
- CM Consultas de mesa · CC Crédito de consignação · GR Guia de remessa · NR Nota de remessa
- FO Folhas de obra · NE Nota de encomenda · OU Outros · OR Orçamentos · PF Pró-forma
- DC Documentos de conferência · GC Guia de consignação
- Seguros: RP, RE, CS, LD, RA
- ⚠ `PP` está na enumeração do XSD, mas não na documentação.

### 4.4 Payments [0..1]

```
NumberOfEntries, TotalDebit, TotalCredit [1]
Payment [0..n]
  PaymentRefNo [1] (mesmo padrão), Period?, TransactionID?, TransactionDate [1]
  PaymentType [1]  RC (recibo emitido) | AR (aviso de cobrança/recibo) | RG (outros recibos)
  Description?, SystemID? (35)
  DocumentStatus [1]: PaymentStatus N|A, PaymentStatusDate, Reason?, SourceID, SourcePayment P|I|M
  PaymentMethod [0..n] (PaymentMechanism?, PaymentAmount, PaymentDate)
  SourceID [1], SystemEntryDate [1], CustomerID [1]
  Line [1..n]: LineNumber, SourceDocumentID [1..n] (OriginatingON [1], InvoiceDate [1], Description?),
       SettlementAmount?, choice Debit|Credit, Tax [0..1] (TaxCode admite "NA"), TaxExemptions?
  DocumentTotals [1]: TaxPayable, NetTotal, GrossTotal, Settlement? > SettlementAmount, Currency?
  WithholdingTax [0..n]
```

**Payments não tem `Hash` nem `HashControl` no XSD.**

### 4.5 PurchaseInvoices [0..1] (específico do AO; não existe no PT)

```
NumberOfEntries [1]
Invoice [0..n]
  InvoiceNo [1] (texto livre, máx. 60: numeração do fornecedor), References [0..n] (Reference?, InvoiceDate?) (# obrigatório nas NC)
  Hash [1]  ← os "4 caracteres do Hash" impressos no documento do fornecedor, ou "0"
  SourceID [1], Period?, InvoiceDate [1]
  PurchaseType [1]  FT|FR|GF|FG|AC|AR|AF|TV|NL|NC|RC   (RC só no regime de caixa)
  SupplierID [1]
  DocumentTotals [1]: TaxPayable, NetTotal, GrossTotal,
    Deductible [0..n]: TaxBase, DeductibleAmount, DeductiblePercentage,
                       DeductibleTaxType MFI|INV|OBC|SERV|IMPT|SCE
    Currency?
  WithholdingTax [0..n]
```

## 7. Restrições de integridade (*XSD*)

- **Únicos:** AccountID, CustomerID, SupplierID, ProductCode, JournalID, TransactionID, InvoiceNo, DocumentNumber (StockMovement e WorkDocument) e PaymentRefNo.
- **keyref** (o valor tem de existir na tabela mestra):
  - GroupingCode → AccountID;
  - DebitLine/CreditLine → AccountID;
  - Customer/SupplierID de GL, Invoice, StockMovement, WorkDocument e Payment;
  - ProductCode das linhas → Product;
  - SupplierID de PurchaseInvoices.
- Consequência: as tabelas mestras têm de incluir **todos** os clientes, fornecedores, produtos e contas referidos.

## 8. Diferenças-chave face ao SAF-T (PT)

1. Namespace e versão próprios (`AO_1.01_01`). Não há ATCUD. `SoftwareValidationNumber` tem o formato NNN/AGT/AAAA.
2. `ProductCompanyTaxID` é obrigatório: é o NIF do produtor.
3. `TaxType` só admite IVA, IS e NS. `TaxCode` inclui INT, OUT, NS e NA. `TaxCountryRegion` admite "AO-CAB" (Cabinda).
4. Os códigos de isenção são `M\d\d` e referem-se ao CIVA angolano.
5. Tipos de documento próprios (GF, FG, AC, AR, AF, TV) e ThirdPartiesBillingIndicator com o valor IVA cativo.
6. `WithholdingTax` com tipos angolanos (IRT, II, IS, IVA cativo, IPU, IAC, OU).
7. Secção `PurchaseInvoices` com `Deductible` (IVA dedutível por tipo de bem).
8. `CustomsInformation` (DU/ARCNo, IECAmount) nas linhas; `ProductType` E/I.
9. A moeda é AOA. Totais com exactamente 2 casas decimais e nenhum valor negativo.

## 9. Lacunas

- **Algoritmo e mensagem do Hash, comprimento da chave e regra dos 4 caracteres impressos:** estão no DE 74/19, que não foi obtido. 172 caracteres corresponde a Base64 de uma assinatura RSA de 1024 bits, como no PT. ⚠ É uma inferência, não uma fonte.
- O XSD do `master` está marcado "Development" e não há publicação oficial da AGT do ficheiro em si.
- Fica por confirmar se ainda existe obrigação mensal de SAF-T de facturação para quem não emite facturação electrónica (ver §1).
