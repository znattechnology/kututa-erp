# Análise de conformidade: Facturação, Odoo 20 Community face ao DP 71/25 (Angola)

**Fonte legal:** Decreto Presidencial n.º 71/25, de 20 de Março (DR I Série n.º 52, pp. 11902–11920). Entra em vigor 6 meses após a publicação, ou seja, cerca de 20/09/2025 (art. 42.º). Revoga o DP 292/18 (facturas) e o DP 144/23 (auto-facturação), e derroga os n.os 1 e 5 do art. 2.º do DP 312/18 (SAF-T) (art. 40.º).
**Código-fonte analisado:** `/Users/vadao/Projectos_Next/odoo/odoo/addons` (Odoo 20.0 Community).

## 0. Constatações prévias

- **Não existe `l10n_ao`** na árvore. A pesquisa `ls addons | grep -i _ao` não devolve nada. Para Angola existem apenas dados de base: o país `base.ao` com moeda AOA (`odoo/addons/base/data/res_country_data.xml:53`), a moeda `AOA` "Kz", **inactiva por defeito** (`res_currency_data.xml:544`) e o idioma `pt_AO` (`res.lang.csv:60`).
- **O `l10n_pt` Community não traz certificação.** Contém apenas o plano de contas, os impostos, o relatório de IVA, uma taxonomia (`l10n_pt/models/account_account.py`) e arredondamento "included" (`l10n_pt/models/account_tax.py`). Não tem hash RSA, ATCUD, séries AT nem SAF-T PT; isso fica no Enterprise. **O modelo a reutilizar não pode ser o l10n_pt.** As melhores referências Community são:
  - `l10n_es_edi_verifactu`: cadeia de hash por emissor, QR, envio em tempo real, substituição e anulação, documento EDI separado (`models/verifactu_document.py`, campos `chain_index`, `_fingerprint()`, `_never_unlink_chained_documents`).
  - `l10n_sa_edi` (ZATCA): cadeia por diário (`account_journal.py:88 l10n_sa_chain_sequence_id`, `l10n_sa_latest_submission_hash`), certificados, motivos de isenção (`account_tax.py:28`).
  - O módulo `certificate`, que dá assinatura RSA com chave privada (`certificate/models/key.py:117 _sign(message, hashing_algorithm=...)`).
- `l10n_mz` e `l10n_gw` trazem apenas planos de contas e impostos (templates CSV), sem nada de certificação. Servem só como molde para o `template_ao.py`.

## 1. Requisitos do DP 71/25 e estado no Odoo

Legenda: ✅ já existe · 🟡 parcial / configuração · 🔴 desenvolvimento necessário

### 1.1 Tipos de documento

| Requisito (artigo) | Odoo 20 | Estado |
|---|---|---|
| Factura (FT) (art. 3.º f, 4.º) | `account.move` `out_invoice` | ✅ |
| Factura-Recibo (FR): factura que comprova o pagamento total (art. 3.º k, 6.º/2 a) | Não existe como tipo. Seria uma factura com pagamento imediato, com série própria | 🔴 |
| Factura de Adiantamento (art. 3.º g), regularizada só por NC (art. 8.º/10) | Adiantamentos de `sale` (down payment) geram uma factura normal. Falta tipo/série próprios e a regra de regularização por NC | 🟡/🔴 |
| Factura Global, mensal, com guias anexas (art. 3.º j, 8.º/2-3) | Possível por agrupamento manual. Falta tipo, a ligação às guias e o controlo do prazo | 🟡 |
| Factura Genérica (instituições financeiras) / Aviso de Cobrança(-Recibo) (seguradoras) (art. 3.º d, i) | Não existe | 🔴 (sectorial, baixa prioridade) |
| Nota de Crédito (NC) (art. 3.º l, 8.º/4-5) | `out_refund` + assistente `account/wizard/account_move_reversal.py` (campo `reason`) | 🟡 |
| Nota de Débito (ND) **sem liquidação de imposto** (art. 3.º m, 4.º/3, 4.º/7) | `account_debit_note` gera uma factura de débito *com* impostos, o que contraria a definição angolana | 🔴 |
| Recibo (RC), obrigatório em cada pagamento total ou parcial (art. 6.º/1), com indicação de impostos retidos/cativos (art. 6.º/3) | `account.payment` não é um documento fiscal numerado, impresso e com hash | 🔴 |
| Talão de Venda, datado e numerado (art. 5.º/2-3) | POS emite talões, mas sem série/hash AGT | 🔴 (fase POS) |
| Auto-facturação: FR emitida pelo adquirente, série distinta, menção «Auto-Facturação» (art. 11.º–12.º, 10.º/3) | Diário de compras sem série/impressão fiscal | 🔴 |
| Documentos que **não são factura**: pró-forma, guia de remessa/transporte, orçamento, etc. (art. 4.º/9) | Cotações (`sale`) e guias (`stock`) existem, mas não são documentos fiscais | ✅ (ver §4: as guias podem ter regime próprio) |

### 1.2 Menções obrigatórias (art. 10.º/1)

| Alínea | Odoo 20 | Estado |
|---|---|---|
| a) Nome, NIF e sede do emitente e do adquirente (este quando for profissional) | `res.partner.vat`, endereço, layout de relatório. Falta validação de NIF AO (sem `base_vat` para AO) e a obrigatoriedade do NIF quando aplicável | 🟡 |
| b) Numeração sequencial e cronológica **por tipo de documento e ano**, uma ou mais séries identificadas | Sequência por diário com reset anual (`sequence.mixin`), `refund_sequence`/`payment_sequence` no diário (`account_journal.py:169,175`). Falta o conceito de "série AGT" comunicada (art. 24.º/1 c) e o bloqueio de séries não comunicadas (art. 35.º/4) | 🟡 |
| c) Discriminação, quantidades, embalagens retornáveis em separado com menção da devolução | Linhas de factura ✅. Falta a menção de embalagens | 🟡 |
| d) Preço unitário e total **em Kz** e **total por extenso** (excepto import/export) | `amount_total_words` (`account_move.py:637`) e `display_invoice_amount_total_words` no relatório (`report_invoice.xml:383`). Falta impor a moeda AOA (ou contravalor) e verificar o extenso em pt_AO ("Kwanzas"/"Cêntimos") | 🟡 |
| e) Taxas e montante do imposto; linhas com taxas diferentes em separado (10.º/2) | Quadro de impostos padrão | ✅ |
| f) **Motivo de não liquidação + norma legal** | `account.tax.invoice_legal_notes` (`account_tax.py:194`) e `ubl_cii_tax_exemption_reason_code`. Falta a tabela de códigos de isenção AGT por imposto | 🟡 (dados) |
| g) **Data, hora** e local de entrega dos bens ou de prestação do serviço; data de pagamento antecipado | `delivery_date`/`taxable_supply_date` são campos `Date`, **sem hora nem local** | 🔴 |
| h) Língua portuguesa | `pt_AO` existe. Falta revisão das traduções | 🟡 |
| i) Data de emissão | `invoice_date` | ✅ |
| j) **Identificação do software validado pela AGT, código hash e n.º de certificação** | `inalterable_hash` existe (`account_move.py:364`), mas é SHA-256 encadeado e interno, não o formato AGT | 🔴 |
| Impressão «Original» / «2.ª via, em conformidade com a original» (art. 7.º/4-5); triplicado (art. 7.º/3) | Não existe contador de impressões | 🔴 |
| «Repasse de Despesas» (art. 4.º/8); «Auto-Facturação» (art. 12.º/1); «Anulação»/«Rectificação» na NC (art. 8.º/5); «emitido em contingência, pendente de autorização» (art. 18.º/2) | Não existe | 🔴 |
| NC: todos os requisitos menos a g) (10.º/5). Recibo: todos menos c) e g) (10.º/6) | — | 🔴 (ligado aos tipos) |

### 1.3 Integridade, rectificação e anulação

| Requisito | Odoo 20 | Estado |
|---|---|---|
| Software que **não permite eliminar** após emissão (art. 3.º n) | `_unlink_forbid_parts_of_chain` e `_unlink_account_audit_trail_except_once_post` (`account_move.py:4177-4207`) com `res.company.restrictive_audit_trail` (`company.py:280`). Pode ser forçado por país em `_compute_force_restrictive_audit_trail` (ex.: `l10n_de/models/res_company.py`) | 🟡 (forçar para AO) |
| Proibição de edição após emissão | `restrict_mode_hash_table` no diário (`account_journal.py:137`) bloqueia a alteração de campos com hash (`account_move.py:4035`) e o `button_draft` (`_check_draftable`, linha 7072). Contudo, um utilizador pode desactivar a opção e `group_account_manager` contorna parte das regras | 🟡 |
| Anulação/rectificação **só por NC com motivo**, expressão «anulação/rectificação», referência ao documento de origem, **prova do conhecimento do adquirente** (carta, email, assinatura+NIF, carimbo; presunção se regularizar o IVA) (art. 8.º/4-7, 21.º) | `reversed_entry_id` e `reason` existem. Faltam o tipo de NC, a menção e o registo/anexo do conhecimento do adquirente | 🔴 |
| Excepção: erro só nos dados de identificação (10.º/1 a) ou factura não enviada → **anulação directa no software, sem NC** (art. 8.º/8-9) | `button_cancel` existe, mas exige rascunho ou não tem estado "anulado" auditável. Usar `is_move_sent` como condição | 🔴 |
| Detecção de alterações não autorizadas e bloqueio até relatório técnico do produtor (art. 22.º/2 b, d) | Relatório de integridade de hash (`_check_hash_integrity`) só reporta, não bloqueia | 🔴 |
| Controlo de acessos, cópias de segurança, exportação de cópias exactas (art. 22.º/2 a, c, e; 22.º/6; 26.º/2) | Grupos de segurança, backup da base de dados, exportação | 🟡 (organizacional e técnico) |
| Documentação técnica: funcionalidades, ciclos, dicionário de dados por versão (art. 22.º/3, 5) | — | 🔴 (documental, não é código) |

### 1.4 Prazos e regimes

| Requisito | Odoo 20 | Estado |
|---|---|---|
| Emissão até ao **5.º dia útil** após a operação; global até ao 5.º dia útil após o período (art. 8.º/1-3; coima de 0,2%, art. 35.º/10) | Não há controlo. Pode comparar-se `invoice_date` com `delivery_date` e o calendário `resource` | 🔴 (aviso/validação) |
| Regimes IVA Geral/Simplificado: software validado obrigatório. Exclusão: blocos ou Portal (art. 7.º, 9.º) | Campo de regime IVA na empresa/parceiro inexistente | 🔴 (campo + regras) |
| Contingência manual: blocos tipográficos até 45 dias, com autorização AGT (art. 7.º/6, 18.º/1 b) → registar depois documentos externos (série manual) | — | 🔴 |
| Transacções ≥ Kz 25 000 000 → factura electrónica/Portal (art. 38.º). Reporte de vendas por grosso a pessoas singulares ≥ 25 M Kz (art. 15.º) | — | 🔴 (validação + relatório) |
| Auto-facturação: limite de 20%/40% dos custos CMVMC+FSE (art. 13.º); retenção na fonte (II provisório sobre vendas / IRT serviços) (art. 14.º) | `l10n_account_withholding_tax` (`models/account_tax.py:13 is_withholding_tax`) dá a base para a retenção. Falta o controlo do limite | 🟡/🔴 |
| Recibos com impostos retidos e **IVA cativo** (art. 6.º/3) | Retenção via `l10n_account_withholding_tax`. Não existe IVA cativo | 🔴 |

### 1.5 Facturação electrónica e comunicação à AGT

| Requisito | Odoo 20 | Estado |
|---|---|---|
| Obrigatória para o IVA Geral/Simplificado. Fase 1 (12 meses após o Decreto Executivo): Grandes Contribuintes e fornecedores do Estado (art. 16.º, 37.º) | — | 🔴 |
| **Transmissão em tempo real** à AGT (art. 3.º h, 17.º/1, 20.º/2) | Framework `account_edi` / `account_move_send` (modelo Veri*Factu, ZATCA) | 🔴 |
| Comunicação de actividade e valor global de vendas **a cada 2 meses**; **bloqueio da emissão** após mais de 60 dias sem comunicação (art. 17.º/4-5) | — | 🔴 |
| Modo offline/contingência com menção, submissão posterior e aviso imediato à AGT (art. 18.º) | Veri*Factu tem fila/estados (`l10n_es_edi_verifactu_state`) | 🔴 |
| **Código digital AGT** para autenticidade e não-repúdio (art. 19.º/2) | `certificate` (assinatura RSA) | 🔴 (especificação externa) |
| Manifestação electrónica do adquirente sobre a NC (art. 21.º) | — | 🔴 |
| Comunicação de estabelecimentos, softwares, **séries usadas e não usadas**, inventário até 15/02, SAF-T de contabilidade até 10/04 (art. 24.º); actualizar antes de emitir (24.º/2) | — | 🔴 |
| Comunicação de facturas, recibos e restantes documentos em **SAF-T (AO)** (art. 25.º); coimas por omissão (35.º/11-13) | Não existe exportador SAF-T | 🔴 |
| Acesso da AGT a dados em "formato normalizado" (art. 23.º/2 b) | Coberto pelo SAF-T | 🔴 |
| NIF do consumidor para a Factura Premiada (art. 29.º/3, 30.º) | `partner.vat` | ✅/🟡 (permitir NIF em "Consumidor Final") |

### 1.6 Arquivo

| Requisito | Odoo 20 | Estado |
|---|---|---|
| Arquivar e conservar nos prazos do **Código Geral Tributário** (art. 26.º/1), incluindo registos de programação | PDF anexo (`message_main_attachment`), auditoria `mail.tracking` | 🟡 (prazo é fonte externa) |
| Integridade do arquivo, prevenção de destruição, recuperação (art. 27.º) | Bloqueio de `unlink` de anexos de facturas emitidas inexistente no Community | 🔴 (ligeiro) |

## 2. Proposta de módulos

| Módulo | Âmbito |
|---|---|
| **`l10n_ao`** (base) | `models/template_ao.py` (molde: `l10n_mz/models/template_mz.py`). CSV `account.account-ao` (PGC Angola), `account.tax-ao`, `account.tax.group-ao`, `account.fiscal.position-ao`. Activar AOA, idioma pt_AO, campos `res.company/res.partner`: `l10n_ao_vat_regime` (geral/simplificado/exclusão), `l10n_ao_is_large_taxpayer`, `l10n_ao_is_state_supplier`. Validação do formato do NIF. Motivos de isenção AGT como `l10n_ao_exemption_code` + `invoice_legal_notes` em `account.tax`. Impostos de retenção via dependência de `l10n_account_withholding_tax`. |
| **`l10n_ao_certification`** (software validado) | Ver §3: tipos de documento, séries, hash RSA, impressão, anulação/NC, prazos, imutabilidade. |
| **`l10n_ao_saft`** | Exportador XML SAF-T (AO) para facturação e contabilidade (arts. 24.º e 25.º): wizard + QWeb XML + validação XSD. |
| **`l10n_ao_edi`** (fase 2) | Comunicação em tempo real à AGT, contingência, bloqueio de 60 dias, manifestação do adquirente (arts. 16.º–21.º). Só depois de publicado o Decreto Executivo do art. 36.º. |
| `l10n_ao_pos` (fase 3) | Talões/FR no POS com a mesma série e hash. |

## 3. Abordagem técnica para os itens 🔴

1. **Tipos de documento e séries.** Criar o campo `l10n_ao_document_type` em `account.move` (FT, FR, NC, ND, RC, FA, FG, AF, …) e o modelo `l10n_ao.series` (código, tipo, ano, estabelecimento, `state`: por comunicar / comunicada / encerrada), com ligação a `account.journal`. Bloquear `_post()` se a série não estiver comunicada (art. 35.º/4). Prefixo de numeração por tipo, série e ano via `sequence_override_regex` ou sequência própria. Usar diários distintos por tipo para a auto-facturação (art. 10.º/3). Na **ND**, impor linhas sem impostos (constraint). No **Recibo**, criar o modelo `l10n_ao.receipt` gerado no `action_post` de `account.payment`, numerado, com hash, que lista facturas, retenções e IVA cativo. Na **FR**, usar uma factura com pagamento integral obrigatório no `_post`, num diário/série FR.
2. **Hash e assinatura.** Não reutilizar `inalterable_hash` (é SHA-256 sem chave). Seguir o padrão do `l10n_es_edi_verifactu`: campos `l10n_ao_hash`, `l10n_ao_hash_control` e `l10n_ao_previous_hash`, com cadeia por série bloqueada com `SELECT … FOR UPDATE` sobre a série, como `next_by_id` em `verifactu_document.py:512-524`. Assinar com `certificate.key._sign()` (RSA, algoritmo e string a assinar definidos pela AGT). Imprimir os caracteres do hash exigidos e a frase "Processado por programa validado n.º …/AGT". O n.º de certificação vai como parâmetro do sistema/produtor, não editável pelo cliente.
3. **Imutabilidade.** Forçar `restrictive_audit_trail` e `restrict_mode_hash_table` em diários de venda AO (override de `_compute_force_restrictive_audit_trail`, como `l10n_de`). Bloquear `button_draft`/`unlink` para documentos AO emitidos, mesmo para administradores. Verificar a integridade da cadeia ao arrancar/emitir e bloquear se falhar (art. 22.º/2 d).
4. **NC e anulação.** Estender o `account.move.reversal` com motivo obrigatório, tipo «Anulação»/«Rectificação» e anexo/registo de prova do conhecimento do adquirente (`l10n_ao_customer_ack_type`, `l10n_ao_customer_ack_date`). A anulação directa (art. 8.º/8-9) passa a ser o novo estado `l10n_ao_cancelled`, com motivo, permitido apenas se `not is_move_sent` ou se só mudam os dados de identificação. Nunca volta a rascunho.
5. **Impressão.** Criar o contador `l10n_ao_print_count`, com override do `_render_qweb_pdf` / `ir.actions.report` para `account.report_invoice`: na 1.ª impressão «Original», nas seguintes «2.ª via, em conformidade com a original». Opção de triplicado (Original/Duplicado/Triplicado). Menções condicionais: Repasse de Despesas, Auto-Facturação, Contingência.
6. **Data, hora e local (10.º/1 g).** Adicionar o campo `l10n_ao_supply_datetime` (Datetime) e o local (`l10n_ao_supply_place` ou o armazém de `stock.picking`), preenchidos a partir da validação da guia.
7. **Prazos.** Usar uma constraint/aviso no `_post` se `invoice_date` for posterior a `delivery_date` + 5 dias úteis (`resource.calendar` com feriados AO) e um cron que lista operações entregues e não facturadas.
8. **SAF-T AO.** Gerar XML a partir de `account.move`, `account.payment`/recibos, parceiros, produtos e impostos, com template QWeb XML e validação XSD em `data/xsd`. A secção GeneralLedgerEntries vem do `account.move.line`. Não há modelo Community para reutilizar: o SAF-T PT está no Enterprise.
9. **EDI em tempo real.** Criar o modelo `l10n_ao.edi.document` (um por envio), com estados, fila, retry e cron, segundo `l10n_es_edi_verifactu/models/verifactu_document.py` (`_send_as_batch`, `trigger_next_batch`). O contador "última comunicação" na empresa permite bloquear `_post` quando passarem mais de 60 dias (art. 17.º/5). A contingência é uma flag no documento com a menção impressa.

## 4. Fontes externas necessárias (não constam do DP 71/25)

- **Decreto Executivo do art. 36.º**: estrutura de dados, modelo da factura electrónica, API, "código digital" (art. 19.º/2) e regras de validação. É **bloqueante** para `l10n_ao_edi` e para o algoritmo de hash/assinatura.
- **Regulamento de validação/certificação de software pela AGT** (requisitos técnicos, algoritmo e chave RSA, string do hash, caracteres impressos, frase de certificação). Não está neste diploma.
- **Esquema SAF-T (AO)** (XSD e versão em vigor) e o **DP 312/18** na parte não derrogada (periodicidade e prazos de submissão).
- **Código do IVA**: taxas em vigor (taxa geral e taxas reduzidas, a confirmar), regime de **IVA cativo** (percentagens e entidades cativadoras), regimes Geral/Simplificado/Exclusão e **tabela de códigos de isenção** com a norma legal (art. 10.º/1 f).
- **Código do Imposto Industrial** (taxa de liquidação provisória sobre vendas) e **Código do IRT** (retenção sobre serviços), para o art. 14.º e para os recibos.
- **Imposto do Selo** e outros impostos a mencionar nos recibos. Não são tratados aqui.
- **Código Geral Tributário**: prazo de conservação (art. 26.º).
- **Plano Geral de Contabilidade de Angola**, para o plano de contas do `l10n_ao`.
- **Regime das guias de remessa/transporte** (o DP 71/25 diz apenas que não são facturas): confirmar se há obrigação de comunicação ou certificação noutro diploma.
- O diploma **não menciona QR code** nem "factura simplificada". Confirmar na especificação AGT antes de implementar.
- Instrumentos da AGT sobre prazos dilatados (art. 8.º/11) e a periodicidade da Factura Premiada (art. 31.º).
