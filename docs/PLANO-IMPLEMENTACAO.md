# Plano geral de implementação: Odoo 20 Angola (produto)

## Contexto
O objectivo é transformar o Odoo 20 Community (em `odoo/`, submódulo) num **produto vendável a empresas e escolas angolanas**. Tem de cumprir quatro diplomas:
- **DP 71/25:** facturas;
- **DE 683/25:** facturação electrónica AGT;
- **Decreto 82/01:** PGC;
- **Lei 12/23:** LGT.

Absorve também **toda a gestão académica do secPed-Express** (`/Users/vadao/Projectos_Next/secPed-Express`, NestJS/Prisma, 168 modelos, em produção no Instituto «Vovó Eva»).

A facturação electrónica é **obrigatória para todos os sujeitos passivos de IVA a partir de 01/01/2027**, sem prorrogação, e exige software certificado pela AGT.

Já feito:
- análise legal em `docs/analise-legal/01–04`;
- especificação AGT e OCR do DE 683/25 em `docs/referencias/`;
- PDFs em `decretos/`.

Decisões tomadas:

| Tema | Decisão |
|---|---|
| Modelo | **Produto multi-cliente** |
| Certificação AGT | Própria ou via integrador, ainda **em aberto**. A arquitectura suporta as duas vias. |
| Salários | **Módulo próprio, Community** |
| Equipa | **1 pessoa + Claude** |
| Âmbito | Facturação, contabilidade, RH, salários, POS, stock, compras e académico (geral, técnico e universitário) |
| Alojamento | Por decidir, por isso **Docker genérico** |

> **Realismo do calendário.** Para uma pessoa, o sistema completo representa cerca de 12 meses de trabalho. Até 01/01/2027 (cerca de 10 semanas) cabe **o que é legalmente obrigatório**: o `l10n_ao` e a facturação certificada AGT com vendas, compras e POS. O resto vem por fases. **O académico arranca a tempo do ano lectivo 2027/28**, com o piloto Vovó Eva em Setembro de 2027.

## Estado (actualizado a 2026-10-20)
| Fase | Estado | Documento |
|---|---|---|
| 1. `l10n_ao` | Concluída | `docs/fases/fase-1-l10n_ao.md` |
| 2. `l10n_ao_edi` e `l10n_ao_edi_pos` | Concluída e auditada; falta a homologação AGT (sem credenciais) | `docs/fases/fase-2*.md`, `auditoria-fase-2.md` |
| 3. Contabilidade | Concluída: `l10n_ao_reports` (3a), `l10n_ao_asset` (3b), `l10n_ao_saft` (3c), `l10n_ao_stock` (3d, no lugar do `l10n_ao_edi_stock`) | `docs/fases/fase-3*.md` |
| 4. RH e salários | Por iniciar | |

## Princípios de arquitectura
1. **Nunca editar `odoo/`.** Todo o código fica em `custom_addons/`, para que as actualizações do Odoo 20.0 continuem a ser só `git submodule update`.
2. **Dois prefixos:**
   - `l10n_ao*` para a conformidade legal, reutilizável por qualquer cliente;
   - `edu_*` para a vertical académica.
3. **As propinas são facturas Odoo.** O módulo académico gera `account.move`, por isso **herda automaticamente** a certificação AGT, o SAF-T e a contabilidade PGC. Elimina-se a duplicação que existe hoje no secPed, onde há um `FiscalDocument` próprio.
4. **Multi-cliente:**
   - uma base de dados por cliente (`dbfilter` por subdomínio);
   - multi-empresa dentro de cada base (cada escola ou empresa é uma `res.company` com o seu NIF, chaves AGT e séries);
   - as chaves e credenciais AGT ficam por empresa (`certificate.key`).
5. **Reutilizar o secPed como fonte de verdade das regras e dos dados:**
   - plano de contas PGC: `secPed-Express/apps/api/prisma/pgc/plano-contas.ts`;
   - escalões do IRT (Lei 14/25): `scripts/seed-irt.ts`;
   - currículos nacionais: `prisma/templates/*`;
   - calendário: `scripts/calendario/*.json`;
   - fórmulas de pauta e promoção: `pauta-computation.service.ts`, `promotion.service.ts` e as docs `regime-avaliacao-*.md`;
   - análise já feita pelo dono: `docs/ANALISE-ODOO-RH-CONTABILIDADE.md`.
6. **Dados mestre da AGT a partir de `docs/referencias/agt-facturacao-electronica/anexos.txt`, não do OCR.** O `anexos.txt` está limpo e tem os mesmos códigos que o decreto:
   - 574 CAE;
   - 117 linhas de IEC;
   - cerca de 108 verbas de IS;
   - 42 isenções de IVA (M00…M93), 3 de IS (S01–S03) e 16 de IEC (I01–I16).

   Gera-se com um script em `tools/` que produz os CSV/XML do módulo.

## Mapa de módulos (`custom_addons/`)

### Conformidade (`l10n_ao*`)

| Módulo | Conteúdo | Reutiliza do Odoo |
|---|---|---|
| `l10n_ao` | Plano PGC (contas pai inactivas e hierarquia `parent_id`, `code_digits` para preservar os códigos); IVA, IS, IEC e CEOC com os campos AGT `taxType`/`taxCode`; motivos de isenção; CAE; validação do NIF; AOA activa; câmbio BNA; posições fiscais (Cabinda AO-CAB, exportação); feriados | `@template('ao')` como em `l10n_mz/models/template_mz.py`; CSV `data/template/<model>-ao.csv`; `tax_report.xml` com raiz `account.generic_tax_report` |
| `l10n_ao_edi` | Toda a facturação AGT. Ver o detalhe abaixo. | `l10n_es_edi_verifactu` (documento, fila, issuer, QR, bloqueio do "repor rascunho"); `l10n_my_edi/models/myinvois_document.py` (submissão e polling); `certificate.key._sign_with_key` (RS256 = PKCS1v15+SHA256) |
| `l10n_ao_edi_pos` | Talão de Venda (TV) e Factura-Recibo no POS, modo offline e contingência | `point_of_sale` |
| `l10n_ao_edi_stock` | `comunicarInventario` / `submeterInventario` | `stock.quant` |
| `l10n_ao_saft` | Exportação SAF-T (AO) da facturação e da contabilidade | Precisa do XSD (fonte externa) |
| `l10n_ao_reports` | Balanço, DR (natureza e funções), DFC e Notas, com N/N-1 em milhares; apuramento pela classe 8; fecho do exercício | O motor `account.report` só calcula no Enterprise, por isso faz-se um cálculo próprio sobre `account.move.line._read_group` por prefixo, com saída QWeb/XLSX |
| `l10n_ao_asset` | Imobilizado com quotas constantes e taxas legais | (o `account_asset` é Enterprise) |
| `l10n_ao_hr` | Regras da LGT sobre o `hr.version` (causas e duração dos contratos a termo, período experimental, aviso de não renovação); tipos de ausência; férias com accrual; horas extra (`hr.time.rule`, mais limites mensais e anuais); assistente de cessação (arts. 307.º–311.º); n.º de Segurança Social | `hr/models/hr_version.py`, `hr_work_entry/models/hr_time_rule.py`, `hr_holidays` accrual, `hr.employee.departure` |
| `l10n_ao_payroll` | Processamento salarial: períodos, recibos, linhas, regras; IRT (escalões configuráveis, importados do secPed); INSS 3%/8%; subsídios de férias e Natal; adiantamentos; limite de 25% nos descontos; lançamento contabilístico; ficheiro bancário; mapas do INSS e do IRT | Base própria; `hr.payroll.structure.type` (stub do `hr`) |

### `l10n_ao_edi` em detalhe

**Modelos novos**
- `l10n_ao_edi.series`: série AGT por tipo, ano e estabelecimento, com o código devolvido pelo `solicitarSerie`, o intervalo e o estado. Inclui também `listarSeries` e `estenderSerie`.
- `l10n_ao_edi.document`: o pedido enviado à AGT, com o JSON, o `requestID`, o estado e os erros.

**Fluxo de envio**
- O cron envia lotes de até 30 documentos (`registarFactura`).
- Outro cron consulta o estado com `obterEstado`, com o significado dos `resultCode`:

  | resultCode | Significado |
  |---|---|
  | 0 / 1 / 2 | Concluído |
  | 7 | Pedido prematuro, aguardar |
  | 8 | Ainda em processamento |
  | 9 | Cancelado |
- Os documentos rejeitados são corrigidos e reenviados com `documentStatus=C`.

**Campos novos**
- Em `account.move`:
  - `l10n_ao_document_type`, com os 18 tipos: FT, FR, FA, FG, GF, AC, AR, TV, RC, RG, RE, ND, NC, AF, RP, RA, CS, LD;
  - o estado AGT;
  - o QR, com o URL da v2 a confirmar em homologação.
- Na linha: `operationType`.
- Os recibos RC/RG são gerados a partir de `account.payment`.

**Assinaturas JWS RS256**
- Um helper próprio: header mais payload em JSON canónico, assinados com `_sign_with_key(formatting=None)` e codificados em base64url sem padding.
- O `mail/tools/jwt.py` serve de modelo, mas só tem ES256 e HS256.
- Há três assinaturas: a do software, a do documento e a do pedido.

**Regras do DP 71/25**
- NC obrigatória com motivo e referência; anulação (`anularFactura`).
- Prazo de emissão até ao 5.º dia útil.
- Menção «2.ª via» nas reimpressões.
- Arredondamento do `taxContribution` por excesso.
- Moeda estrangeira com contravalor.
- Contingência com a menção «pendente de autorização».
- Bloqueio da emissão ao fim de 60 dias sem comunicação.
- `restrict_mode_hash_table` forçado nos diários AO.

**Compras e auditoria**
- `validarDocumento` para as facturas de fornecedor, com o IVA dedutível.
- `comunicarServicosEstrangeiro`.
- Registo de auditoria de todos os eventos, como exige o Anexo III.

**Via integrador (opcional)**
- Uma camada `_l10n_ao_edi_transport()` permite trocar o envio directo à AGT por um integrador, sem mexer no resto.

### Vertical académica (`edu_*`): porte funcional do secPed

| Módulo | Conteúdo (entidades secPed → Odoo) |
|---|---|
| `edu_core` | Escola = `res.company` com os campos MED (tipo, natureza, modo de cobrança, código MED, signatários); `AcademicYear`/`Trimester`; `Course`, `Subject` (componentes), `SchoolClass`/`ClassOffering`; `Curriculum` e modelos nacionais (dados importados dos templates do secPed); instalações (campus, edifício, sala); turnos |
| `edu_people` | Aluno, encarregado e professor sobre `res.partner`/`hr.employee`; parentescos (`StudentGuardian`); n.º de matrícula |
| `edu_enrollment` | Candidaturas, matrículas (estados), inscrição em disciplinas, transferências, número de ordem |
| `edu_timetable` | Grelha, `TimeSlot`, horários, excepções, substituições, professor × disciplina × turma, director de turma |
| `edu_attendance` | Aulas (sumários), presenças por aula, regras de faltas (geral 3/4/5, técnico 3× os tempos semanais) |
| `edu_evaluation` | **A área mais crítica.** Avaliações e notas; políticas de avaliação, escalas e regras de promoção; motores de cálculo **geral (Dec. 424/25)** e **técnico (Despacho 60/08: CF cumulativa, Prova Global, PAP)**; janela de lançamento e autorizações; reapreciação; conselho de turma (votos, +2, quórum); RDEC no pré-escolar |
| `edu_exam` | Épocas, sessões, salas, vigilantes, exame nacional, recurso, extraordinário, melhoria, equivalência |
| `edu_records` | Histórico académico, decisões, certificados, diplomas, estágio, PAP |
| `edu_documents` | Cerca de 20 relatórios QWeb oficiais: pautas, mini-pauta, caderneta, termos, declarações com notas por extenso, certificado, diploma, guia de transferência, actas, RDEC/RDEA, cartão de estudante, todos com a identidade visual da escola |
| `edu_fees` | Planos de propinas → `account.move` certificadas pelo `l10n_ao_edi`; multas, bolsas, alocação de pagamentos; bloqueio de devedores (rematrícula, documentos, notas, exames, portaria); referência Multicaixa (gateway EMIS/GPO, ainda bloqueado) |
| `edu_secretaria` | Pedidos de documentos com prazo e preço; arquivo; portaria |
| `edu_library` / `edu_reprography` | Biblioteca (empréstimos, multas); reprografia sobre `stock` e `maintenance` |
| `edu_portal` | Portais do aluno, encarregado e professor (notas, faltas, propinas, horário, materiais) sobre o portal do Odoo; PWA no lugar da app Expo |
| `edu_university` | **Novo, o secPed não o tem:** licenciaturas, semestres, ECTS, unidades curriculares, precedências, épocas (normal, recurso, especial), defesa |
| `edu_migration_secped` | Importação idempotente a partir de um dump PostgreSQL do secPed para staging e daí para o Odoo, reaproveitando a lógica de `scripts/migracao-vovo-eva/` |

### Integração do académico com os outros módulos
Regra: **o académico não duplica o que o Odoo já faz.** Cada função transversal usa o módulo padrão ou `l10n_ao*` correspondente, através de chaves Many2one e de eventos, nunca de cópias de dados.

| Área académica | Integra com | Como |
|---|---|---|
| Propinas, emolumentos, multas, exames pagos, cartão | `account` + `l10n_ao_edi` | Cada cobrança é uma `account.move` (FT/FR) e cada pagamento um `account.payment` → recibo RC. Ficam certificadas na AGT e entram no SAF-T automaticamente. As bolsas e descontos são linhas e posições fiscais; a isenção de IVA do ensino é o código **M21** (art. 12.º n.º 1 l) do CIVA). |
| Contabilidade por escola, curso e turma | `account` analítica + `l10n_ao_reports` | Plano analítico Escola › Curso › Turma, que dá a receita e o custo por curso nos relatórios PGC |
| Professores e funcionários | `hr`, `l10n_ao_hr`, `l10n_ao_payroll` | O professor é um `hr.employee`. Os tempos lectivos dados (`edu_attendance`) alimentam a carga lectiva paga à aula, por isso o recibo de salário lê as aulas registadas. Faltas do professor → `hr.leave` |
| Alunos e encarregados | `res.partner` + `portal` | O encarregado é o cliente das facturas. O portal mostra notas, faltas, facturas e pagamentos online |
| Reprografia, uniformes, livros, material | `stock`, `purchase`, `point_of_sale` + `l10n_ao_edi_pos` | Venda no balcão da escola pelo POS (talão TV certificado). Compras a fornecedores com `validarDocumento` AGT. Consumo de papel e toner em stock |
| Biblioteca | `stock` (exemplares) ou modelo próprio + `account` | As multas de atraso geram uma factura certificada |
| Cantina e transporte (futuro) | `point_of_sale`, `fleet` | Pagamento por cartão de estudante |
| Calendário, avisos e mensagens | `calendar`, `mail`/Discuss, `sms` | Calendário escolar nacional; notificações a encarregados |
| Candidaturas online | `website` + `edu_enrollment` | Formulário público que cria uma candidatura e uma factura de inscrição |
| Documentos oficiais | `report` (QWeb), `documents` / `ir.attachment` | Os pedidos de documentos pagos geram uma factura. A emissão só é possível depois do pagamento (bloqueio de devedores) |
| Infra-estruturas | `maintenance` | Salas e equipamentos |

Normas de referência para o `edu_evaluation`, todas em `decretos/` com OCR em `docs/referencias/avaliacao/`:
- **Decreto Executivo n.º 424/25:** regime de avaliação do ensino geral;
- **Despacho n.º 60/08:** regime de avaliação do ensino técnico-profissional (EMT);
- **Resumo do Regime de Avaliação 2026/2027.**

As normas das universidades serão partilhadas pelo utilizador antes da fase 7.

Mapeamentos de plataforma:
- RBAC do secPed (433 permissões) → grupos Odoo e `ir.rule` por escola.
- Mensagens → `mail`/Discuss.
- Calendário → `calendar`.
- Auditoria → `mail.tracking` mais um log de auditoria.

## Fases e calendário

| Fase | Período | Entregáveis | Gate |
|---|---|---|---|
| **0. Fundações** | 21–31 Out 2026 | Estrutura de `custom_addons/`, pre-commit com ruff e pylint-odoo, `make test` por módulo, CI local, Dockerfile de produção (Odoo + wkhtmltopdf), empresa de testes AO, `tools/` geradores de dados | `make test` verde num módulo vazio |
| **0b. AGT, sem código, em paralelo e a começar JÁ** | Out–Dez 2026 | Email para `produtores.dfe.dcrr.agt@minfin.gov.ao`; registo no Portal do Parceiro (homologação); par de chaves RSA do produtor; credenciais; pedido de certificação; decisão entre via própria e integrador até **15/11** | Credenciais de homologação recebidas |
| **1. `l10n_ao`** | 1–15 Nov 2026 | Plano PGC, impostos com os códigos AGT, isenções, IS, IEC, CAE, NIF, BNA | Instalar a localização numa empresa nova; facturas com IVA 14% e isenção M-code correctas |
| **2. `l10n_ao_edi`** | 10 Nov – 15 Dez 2026 | Séries, envio, polling, JWS, QR, NC, RC, anulação, contingência, compras (`validarDocumento`), impressões | **Ciclo completo validado no `sifphml` (homologação AGT)** |
| **2b. `l10n_ao_edi_pos`** | 1–20 Dez 2026 | Talões TV e FR no POS | Venda no POS aceite em homologação |
| **Go-live legal** | **até 31 Dez 2026** | Certificação e produção (`sifp`) | Primeira factura real validada pela AGT |
| **3. Contabilidade** | Jan–Fev 2027 | `l10n_ao_saft`, `l10n_ao_reports`, `l10n_ao_asset`, `l10n_ao_edi_stock` | Balanço e DR de uma empresa de teste batem com o cálculo manual; SAF-T valida no XSD |
| **4. RH e salários** | Mar–Abr 2027 | `l10n_ao_hr`, `l10n_ao_payroll` (IRT do secPed, INSS, subsídios, carga lectiva dos professores) | Recibos de teste batem com os casos do secPed e as tabelas do IRT |
| **5. Académico (núcleo)** | Mai–Ago 2027 | `edu_core`, `edu_people`, `edu_enrollment`, `edu_timetable`, `edu_attendance`, `edu_evaluation`, `edu_exam`, `edu_records`, `edu_documents`, `edu_fees`, `edu_migration_secped` | **Migração da Vovó Eva:** as pautas do Odoo coincidem com as do secPed (19 554 notas) |
| **5b. Piloto** | Set 2027 | Arranque do ano lectivo 2027/28 na Vovó Eva | Primeiro trimestre fechado no Odoo |
| **6. Académico (complementos)** | Set–Dez 2027 | `edu_portal`, `edu_secretaria`, `edu_library`, `edu_reprography` | Portal do encarregado usado no piloto |
| **7. Universidade** | 2028 | `edu_university` | Desenho com uma universidade cliente |

## Ficheiros e locais críticos
- **Código novo:** `custom_addons/<módulo>/`, com a estrutura Odoo padrão (`__manifest__.py`, `models/`, `data/`, `views/`, `report/`, `tests/`, `i18n/pt.po`).
- **Geradores de dados:** `tools/gen_agt_tables.py` (lê o `anexos.txt`), `tools/gen_pgc_chart.py` (lê o `plano-contas.ts` do secPed e confronta-o com a §5.3 do Decreto 82/01).
- **Configuração:** `config/odoo.conf` (`dbfilter` e `proxy_mode` em produção), `docker-compose.yml`, mais um novo `docker/Dockerfile` e um `docker-compose.prod.yml`.
- **Referências:**
  - análise legal: `docs/analise-legal/04-facturacao-electronica-AGT.md`;
  - especificação AGT: `docs/referencias/agt-facturacao-electronica/servicos/servicos_solicitar_registo.txt`;
  - fórmulas de avaliação: `secPed-Express/docs/regime-avaliacao-*.md`.

## Verificação
- **Testes unitários Odoo** (`TransactionCase`/`tagged('post_install','-at_install')`) por módulo, com `make test d=test_ao m=<módulo>`.
- **`l10n_ao_edi`:**
  - testes com respostas AGT simuladas;
  - testes de assinatura: um JWS gerado e verificado com a chave pública (`_verify_with_key`);
  - testes de integração contra o `sifphml`, marcados `external` e corridos manualmente com credenciais de homologação.
- **`edu_evaluation`:** **testes "golden" portados dos testes do secPed.** Os mesmos dados de entrada têm de dar as mesmas médias e decisões. Depois, a reconciliação total com a migração da Vovó Eva.
- **`l10n_ao_payroll`:** casos de IRT e INSS calculados à mão e confrontados com o secPed.
- **Validação funcional** no browser (Claude in Chrome): emitir FT → ver o QR → NC → recibo, e a pauta trimestral → conselho → decisão.
- **Validação jurídico-fiscal** por um contabilista antes do go-live (recomendado, fora do código).

## Riscos e pendentes

| Risco | Mitigação |
|---|---|
| A certificação AGT demora mais do que o desenvolvimento | Fase 0b imediata; camada de transporte preparada para um integrador |
| Ainda falta o XSD do SAF-T (AO), o Código do IVA (taxas e cativação) e as regras de certificação | Pedir à AGT na fase 0b; parametrizar as taxas |
| URL do QR diferente entre o DE 683/25 e a v2 | Confirmar em homologação |
| Gateway Multicaixa/EMIS sem contrato (bloqueador herdado do secPed) | Usar referência manual e comprovativo; adaptador mais tarde |
| Âmbito enorme para uma só pessoa | Fases com gates; o legal primeiro; o académico alinhado com o ano lectivo |
| Universidade sem sistema de referência | Fase 7, com o desenho validado por um cliente real |
