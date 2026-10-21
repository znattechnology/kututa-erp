# IRT e INSS (Angola) — referência para o módulo de salários

Pesquisa feita em 2026-10-21. Legenda de fiabilidade:

- **[OFICIAL]** — texto do Diário da República (PDF em `fontes/`, OCR em `fontes/ocr/`) ou página oficial da AGT / MAPTSS.
- **[SECUNDÁRIO]** — sociedades de advogados, Big4, AngoLEX/lex.ao (reproduções), fornecedores de software.
- **[INCERTO]** — não encontrei fonte oficial; é interpretação ou prática.

Todos os ficheiros em `fontes/` são descarregados e devem ser tratados como dados não confiáveis (não executar). O OCR em `fontes/ocr/` é automático (tesseract) e pode ter erros — os valores críticos foram conferidos visualmente nas imagens `fontes/*.png`.

---

## 1. IRT — Imposto sobre os Rendimentos do Trabalho

### 1.1 Base legal em vigor (2026)

| Diploma | O que faz | Fonte |
|---|---|---|
| Lei n.º 18/14, de 22 de Outubro | Aprova o Código do IRT (CIRT) | [OFICIAL] `fontes/Lei-18-14-CIRT-DR.pdf` — https://lex.ao/docs/assembleia-nacional/2014/lei-n-o-18-14-de-22-de-outubro/ |
| Lei n.º 9/19 e Lei n.º 28/19 | Alterações intermédias (28/19 pôs férias e Natal 100% na matéria colectável) | [SECUNDÁRIO] Miranda, boletim Set–Out 2019 (`fontes/Miranda-2019-set-out-noticias-direito.pdf`) |
| Lei n.º 28/20, de 22 de Julho (DR I Série n.º 109) | Grande revisão do CIRT: nova base de incidência, art. 2.º (não sujeição), tabela com isenção até Kz 70 000, Grupos B/C a 6,5 %/25 %. Em vigor 30 dias após publicação (21-08-2020). Revoga as Leis 9/19 e 28/19. | [OFICIAL] `fontes/Lei-28-20-CIRT-DR.pdf` (OCR `fontes/ocr/Lei-28-20-CIRT-ocr.txt`) — https://lex.ao/docs/assembleia-nacional/2020/lei-n-o-28-20-de-22-de-julho/ |
| Lei n.º 15/23, de 29 de Dezembro (OGE 2024), art. 20.º | Isenção sobe para Kz 100 000; nova tabela (12 escalões). Em vigor 01-01-2024 | [OFICIAL] `fontes/Lei-15-23-OGE-2024-DR.pdf`, tabela na imagem `fontes/Lei-15-23-OGE-2024-anexo-tabela-IRT-p17.png` |
| Lei n.º 18/24 (OGE 2025) | Mantém isenção de Kz 100 000 e regras do Grupo C | [SECUNDÁRIO] PLMJ `fontes/PLMJ-OGE-2025.pdf`; número da lei via CABRI (não confirmado no DR) |
| **Lei n.º 14/25, de 30 de Dezembro (OGE 2026), art. 21.º e Anexo I** (DR I Série n.º 244, pág. 23173 e 23180) | **Isenção sobe para Kz 150 000; nova tabela (11 escalões); multa por não entrega passa a 100 % do imposto em falta; mantém Grupo C 6,5 % (facturação ≤ Kz 10 M) e 10 % agro-pecuária; suspende o n.º 2 do art. 9.º do CIRT (art. 41.º). Em vigor 01-01-2026 (art. 43.º)** | [OFICIAL] `fontes/Lei-14-25-OGE-2026-DR.pdf` (766 pág., 83 MB), OCR pp. 1–45 em `fontes/ocr/Lei-14-25-OGE-2026-pp1-45-ocr.txt`; tabela conferida na imagem `fontes/Lei-14-25-OGE-2026-AnexoI-tabela-IRT-p20.png` — https://lex.ao/docs/assembleia-nacional/2025/lei-n-o-14-25-de-30-de-dezembro/ |

Não encontrei nenhuma lei posterior (2026) a alterar o IRT. As leis do OGE alteram a tabela "por fora" (artigo da lei orçamental + anexo) sem republicar o CIRT; a AGT aplica a tabela do OGE em vigor no Portal do Contribuinte.

Confirmações secundárias da tabela 2026: KPMG Angola (https://kpmg.com/ao/pt/insights/tax-news/lei-orcamento-geral-estado-2026.html), EY (`fontes/EY-tax-alert-OGE-2026.pdf`, pág. 17), PwC (https://www.pwc.pt/pt/pwcinforfisco/flash/angola/angola-aprovacao-orcamento-geral-estado-2026.html), PaySpace (https://support.payspace.com/portal/en/kb/articles/angola-2026-income-tax-law-enacted-key-payroll-changes-effective-1-january-2026), AngoLEX (https://angolex.com/paginas/outros/tabela-do-imposto-de-rendimento-do-trabalho-em-vigor-angola-irt-2026a.html).

### 1.2 Tabela do IRT — Grupo A — em vigor desde 01-01-2026 [OFICIAL]

Anexo I da Lei n.º 14/25 ("A que se refere o n.º 3 do artigo 21.º — sobre o Limite do Rendimento Isento de Pagamento de IRT"). Valores em Kz, mensais, aplicados à **matéria colectável** (ver 1.4). CSV: `irt_escaloes.csv`.

| Escalão | Acima de (limite inferior) | Até (limite superior) | Parcela fixa | Taxa sobre o excesso | Excesso de |
|---|---:|---:|---:|---:|---:|
| 1.º | 0 | 150 000 | 0 | — (isento) | — |
| 2.º | 150 000 | 200 000 | 12 500 | 16,00 % | 150 000 |
| 3.º | 200 000 | 300 000 | 31 250 | 18,00 % | 200 000 |
| 4.º | 300 000 | 500 000 | 49 250 | 19,00 % | 300 000 |
| 5.º | 500 000 | 1 000 000 | 87 250 | 20,00 % | 500 000 |
| 6.º | 1 000 000 | 1 500 000 | 187 250 | 21,00 % | 1 000 000 |
| 7.º | 1 500 000 | 2 000 000 | 292 250 | 22,00 % | 1 500 000 |
| 8.º | 2 000 000 | 2 500 000 | 402 250 | 23,00 % | 2 000 000 |
| 9.º | 2 500 000 | 5 000 000 | 517 250 | 24,00 % | 2 500 000 |
| 10.º | 5 000 000 | 10 000 000 | 1 117 250 | 24,50 % | 5 000 000 |
| 11.º | 10 000 000 | (sem limite) | 2 342 250 | 25,00 % | 10 000 000 |

Fórmula (texto da tabela: "Parcela Fixa" + "Taxa" sobre o "Excesso de"):

```
MC <= 150 000            -> IRT = 0
MC  > limite_inferior_n  -> IRT = parcela_fixa_n + taxa_n * (MC - excesso_de_n)
```

Observações importantes para a implementação:

- O limiar de Kz 150 000 é um **limite de isenção, não uma dedução**: com MC = 150 001 o IRT é 12 500 + 16 % × 1 = 12 500,16 (salto). Isto é propositado — a parcela fixa de cada escalão ficou igual à da Lei 28/20 (incluía o imposto dos escalões agora isentos). KPMG descreveu o mesmo comportamento em 2020 ("a partir de 70 001 passam a ter retenção sobre o montante total"). [OFICIAL quanto aos números; comportamento confirmado por SECUNDÁRIO]
- O limite do 1.º escalão é "até 150 000" e o 2.º é "acima de 150 000": MC exactamente 150 000 é isento.
- Há uma descontinuidade entre o 2.º e o 3.º escalão (12 500 + 16 % × 50 000 = 20 500 ≠ 31 250). É assim na tabela oficial (e já era na Lei 18/14 e na Lei 28/20); não "corrigir".
- Arredondamento: **não existe regra no CIRT nem nas leis do OGE** [INCERTO]. O SIGT/Portal do Contribuinte calcula o imposto a partir do mapa (ver 1.8); na prática usa-se o valor em Kz com 2 casas decimais. Sugestão: calcular com 2 decimais e permitir configuração.

### 1.3 Tabelas anteriores (para histórico/recibos de anos anteriores)

**2024–2025 — Lei n.º 15/23, art. 20.º n.º 3 e anexo [OFICIAL]** (imagem `fontes/Lei-15-23-OGE-2024-anexo-tabela-IRT-p17.png`; a Lei 18/24 do OGE 2025 manteve-a):

| Escalão | De | a | Parcela fixa | Taxa | Excesso de |
|---|---:|---:|---:|---:|---:|
| 1.º | — | 100 000 | — | — | — |
| 2.º | 100 001 | 150 000 | — (0) | 13,0 % | 100 001 |
| 3.º | 150 001 | 200 000 | 12 500 | 16,0 % | 150 001 |
| 4.º | 200 001 | 300 000 | 31 250 | 18,0 % | 200 001 |
| 5.º | 300 001 | 500 000 | 49 250 | 19,0 % | 300 001 |
| 6.º | 500 001 | 1 000 000 | 87 250 | 20,0 % | 500 001 |
| 7.º | 1 000 001 | 1 500 000 | 187 249 | 21,0 % | 1 000 001 |
| 8.º | 1 500 001 | 2 000 000 | 292 249 | 22,0 % | 1 500 001 |
| 9.º | 2 000 001 | 2 500 000 | 402 249 | 23,0 % | 2 000 001 |
| 10.º | 2 500 001 | 5 000 000 | 517 249 | 24,0 % | 2 500 001 |
| 11.º | 5 000 001 | 10 000 000 | 1 117 249 | 24,5 % | 5 000 001 |
| 12.º | 10 000 001 | — | 2 342 248 | 25,0 % | 10 000 001 |

(Sim, a tabela de 2024 tem parcelas fixas "…249/…248" e "excesso de …001" — está assim no DR. A tabela de 2026 voltou a "…250" e "excesso de …000".)

**2020-09 a 2023 — Lei n.º 28/20, art. 3.º [OFICIAL]** (OCR; 13 escalões): até 70 000 isento; 70 001–100 000: 3 000 + 10 % sobre o excesso de 70 000; 100 001–150 000: 6 000 + 13 % s/ 100 000; 150 001–200 000: 12 500 + 16 % s/ 150 000; 200 001–300 000: 31 250 + 18 %; 300 001–500 000: 49 250 + 19 %; 500 001–1 000 000: 87 250 + 20 %; 1 000 001–1 500 000: 187 250 + 21 %; 1 500 001–2 000 000: 292 250 + 22 %; 2 000 001–2 500 000: 402 250 + 23 %; 2 500 001–5 000 000: 517 250 + 24 %; 5 000 001–10 000 000: 1 117 250 + 24,5 %; > 10 000 000: 2 342 250 + 25 %.

Todas as três tabelas estão em `irt_escaloes_historico.csv`.

### 1.4 Matéria colectável do Grupo A (como se calcula a base)

Art. 7.º n.º 2 do CIRT (redacção vigente, reproduzida na página oficial da AGT — `fontes/AGT-portal-IRT-pagina.html`, https://portaldocontribuinte.minfin.gov.ao/impostos-e-taxas/imposto-sobre-rendimentos-do-trabalho) [OFICIAL]:

> "A matéria colectável é constituída por todas as remunerações expressas em dinheiro ainda que auferidas em espécie, de natureza contratual e não contratual, periódicas ou ocasionais, fixas ou variáveis, independentemente da sua proveniência, local, moeda, forma estipulada para o seu cálculo e pagamento, auferidas pelo trabalhador por conta de outrem, **deduzidas da retribuição global das contribuições obrigatórias para a Segurança Social e das componentes remuneratórias não sujeitas ou isentas**, nos termos do CIRT."

Ou seja:

```
MC = Rendimento bruto sujeito (salário base + subsídios/prémios/horas extra/comissões/
     parte tributável dos subsídios de alimentação e transporte + férias + Natal + ...)
   - contribuição do trabalhador para o INSS (3 % da base de incidência INSS, ver 2.3)
   - componentes não sujeitas (art. 2.º) e isentas (art. 5.º)
```

Nota: a dedução é da contribuição **efectivamente** devida à Segurança Social (3 % sobre a base INSS, que exclui o subsídio de férias — ver 2.3), não "3 % do bruto". Em folhas sem subsídio de férias no mês as duas coisas coincidem.

Art. 10.º n.º 1 (Lei 28/20) [OFICIAL]: "A liquidação do imposto devido pela atribuição de rendimentos do Grupo A é efectuada **mensalmente**, pela entidade responsável pelo pagamento destes rendimentos, após a realização das deduções previstas no n.º 2 do artigo 7.º, pela aplicação da tabela de taxas".

Incidência (art. 1.º, redacção Lei 28/20, e página AGT) [OFICIAL]: "ordenados, vencimentos, salários, honorários, avenças, gratificações, subsídios, prémios, comissões, participações, senhas de presença, emolumentos, participações em multas, custas e outras remunerações acessórias"; remunerações acessórias = "todos os direitos, as regalias ou os benefícios patrimoniais ou financeiros não incluídos na remuneração principal […] que representem uma vantagem económica".

### 1.5 Rendimentos não sujeitos (art. 2.º CIRT, redacção Lei 28/20) e isentos (art. 5.º)

Lista vigente, conforme página oficial da AGT [OFICIAL] (coincide com o OCR da Lei 28/20, que marca como **revogadas** as alíneas b, c, f, g, m e os n.ºs 2–4 do art. 2.º):

| Item | Limite | Nota |
|---|---|---|
| Prestações sociais pagas pelo INSS no âmbito da protecção social obrigatória | — | |
| **Abono de família pago pela entidade empregadora** | **até 5 % do ordenado base mensal** | excluídos trabalhadores do regime da função pública; o excesso é tributado |
| Contribuições para a Segurança Social | — | (é a dedução do 3 %) |
| Salários de trabalhadores eventuais agrícolas nacionais e domésticos contratados por pessoas singulares/agregados, inscritos na SS | até Kz 100 000 | alínea h) |
| Subsídios atribuídos por lei a cidadãos com deficiência | — | |
| Subsídios diários, de representação, viagem e deslocação de funcionários do Estado | limites da legislação específica | alínea j) |
| **Subsídio diário de alimentação** (trabalhadores não incluídos na al. j) | **até Kz 30 000 / mês** | alínea k); o excesso é tributado |
| **Subsídio diário de transporte** (idem) | **até Kz 30 000 / mês** | alínea n); o excesso é tributado |
| Reembolso de despesas documentadas de trabalhadores deslocados ao serviço (entidades sujeitas a Imposto Industrial) | documentadas nos termos do CII | alínea l) |

Os dois limites de Kz 30 000 são **separados** (um para alimentação, outro para transporte) — redacção "até ao limite mensal de AKz: 30.000,00" em cada alínea [OFICIAL].

**Deixaram de estar não sujeitos (tributados a 100 % desde 2019/2020)** [OFICIAL pela revogação; explicação SECUNDÁRIO VdA `fontes/VdA-2020-alteracoes-CIRT.pdf`, Miranda 2019]: gratificação/subsídio de férias e subsídio de Natal (antiga al. m, "até 100 % do salário base"); subsídio de renda de casa (antes 50 %); compensações por rescisão; abonos para falhas; gratificações de fim de carreira.

Horas extraordinárias, prémios, comissões, subsídio de turno, subsídio nocturno, etc.: **sujeitos** (não há qualquer exclusão) [OFICIAL por omissão na lista].

Isenções (art. 5.º) [OFICIAL AGT]: agentes de missões diplomáticas/consulares (reciprocidade); pessoal estrangeiro de organizações internacionais e de ONG (com reconhecimento prévio da AGT); deficientes físicos e mutilados de guerra com incapacidade ≥ 50 %; antigos combatentes, veteranos da pátria e deficientes de guerra registados no departamento ministerial de tutela.

### 1.6 Subsídio de férias e de Natal (13.º mês) — tratamento em IRT

- São **integralmente tributados** (ver 1.5) [OFICIAL].
- O CIRT manda liquidar **mensalmente** sobre os rendimentos pagos no mês (art. 10.º n.º 1); **não existe norma que mande tributar o subsídio de férias ou de Natal "em separado"/autonomamente** — a leitura literal é que entram na matéria colectável do mês em que são pagos e sobem o escalão desse mês. [INCERTO quanto à prática: alguns softwares angolanos oferecem a opção "tributar em separado"; não encontrei base legal para isso nem orientação da AGT. O mapa mensal de remunerações no Portal do Contribuinte recebe um total de rendimento por trabalhador e por mês e o SIGT calcula o IRT sobre esse total, o que favorece a leitura "em conjunto".]
- Recomendação para o módulo: por omissão, somar ao mês; disponibilizar um parâmetro "tributar subsídios anuais em separado" desligado, com aviso.
- Em INSS o tratamento é diferente (férias excluído; Natal incluído) — ver 2.3.

### 1.7 Grupos B e C (resumo, para rendimentos pagos a independentes)

[OFICIAL — página AGT + Lei 28/20 art. 16.º + Lei 14/25 art. 21.º]

- Grupo B (profissões liberais da lista anexa, titulares de órgãos sociais são Grupo A): rendimentos pagos por entidades com contabilidade ou modelo simplificado → **retenção na fonte de 6,5 %** sobre o valor do serviço, entregue pela entidade pagadora até ao final do mês seguinte; restantes → 25 % liquidado pelo próprio (Modelo 1 até fim de Março).
- Grupo C (actividades industriais/comerciais da Tabela dos Lucros Mínimos): retenção 6,5 % quando pagos por entidades com contabilidade; 25 % sobre a matéria colectável não sujeita a retenção; **Lei 14/25 art. 21.º**: contribuintes com facturação 2025 ≤ Kz 10 000 000 → 6,5 % sobre o volume de vendas não sujeitas a retenção; com contabilidade organizada → regras do Imposto Industrial; agrícola/silvícola/pecuária/pesca acima de Kz 10 M → 10 %; n.º 2 do art. 9.º (4× Tabela dos Lucros Mínimos) suspenso (art. 41.º n.º 2).
- Auto-facturação (Grupos B/C): retenção não liberatória de 2 % ou 6,5 % sobre a auto-factura, entrega em 5 dias (art. 10.º n.º 4).
- Não residentes: retenção de 15 % (VdA 2020) [SECUNDÁRIO].

### 1.8 Obrigações da entidade empregadora (Grupo A)

| Obrigação | Regra | Fonte |
|---|---|---|
| Retenção na fonte | Liquidação mensal pela entidade pagadora (art. 10.º n.º 1) | [OFICIAL] |
| **Entrega do imposto** | **"até ao final do mês seguinte ao do respectivo pagamento"**, na Repartição Fiscal competente (art. 11.º, página AGT "Pagamento e Entrega — Grupo A") | [OFICIAL] |
| **Mapa Mensal de Remunerações de IRT** | Art. 17.º CIRT: obrigatório para entidades com **mais de 3 trabalhadores** (incluindo isentos). Desde 01-01-2022 a liquidação do IRT por conta de outrem faz-se **apenas** com a submissão electrónica do mapa no Portal do Contribuinte (Declarações → IRT → Entregar → Mapa de Remuneração), por template Excel/CSV/XML ou linha a linha; o SIGT calcula o IRT e emite a Nota de Liquidação + mapa; o mapa de substituição tem de incluir todos os trabalhadores. Entidades com ≤ 3 trabalhadores podem usar o portal. | [OFICIAL] comunicado AGT de 10-09-2021 (https://portaldocontribuinte.minfin.gov.ao/noticia?id=809186) e guias rápidos `fontes/AGT-guia-rapido-mapa-mensal-remuneracoes-IRT*.pdf` (https://portaldocontribuinte.minfin.gov.ao/pdfs/guia-rapido/irt/novos-guias/guia-rapido-mapa-mensal-de-remuneracoes-de-irt.pdf) |
| Prazo do mapa | O mesmo do pagamento (o mapa gera a nota de liquidação): final do mês seguinte. Em 2023 a AGT prorrogou excepcionalmente o mapa de Janeiro até 31-03. | [SECUNDÁRIO] Ver Angola 03/2023 |
| Documento de pagamento | Nota de Liquidação gerada pelo portal; pagamento via referência/DAR (antes de 2022 usava-se o classificador de receita A12) | [OFICIAL] comunicado AGT 2021 |
| **Declaração anual Modelo 2** | Art. 12.º CIRT: em **Fevereiro**, por trabalhador (nome, morada, NIF, NISS, rendimento total e imposto do ano anterior). A AGT anunciou que deixou de exigir a entrega manual: o Modelo 2 anual passa a ser gerado pelo sistema a partir dos mapas mensais e o contribuinte confirma no portal. Multa por falta: Kz 4 000 por trabalhador (art. 28.º n.º 4, notícia 2020). | Art. 12.º [OFICIAL via AngoLEX consolidado — SECUNDÁRIO]; geração automática [SECUNDÁRIO] PaySpace (https://support.payspace.com/portal/en/kb/articles/angola-manual-model-2-annual-declaration-discontinued) |
| Recibo de vencimento | Art. 35.º CIRT: recibo mensal com remunerações e descontos, assinado e carimbado | [SECUNDÁRIO] AngoLEX consolidado |
| **Multa por não entrega / entrega inferior** | Lei 14/25 art. 21.º n.º 5: multa igual ao imposto em falta (100 %), sem prejuízo de procedimento criminal (o CIRT previa o dobro) | [OFICIAL] |

Não encontrei no Portal do Contribuinte o layout de colunas do template Excel/CSV/XML do mapa (exige login). Os guias rápidos descarregados mostram apenas o fluxo de ecrãs. **[INCERTO]** — obter o template com credenciais de um contribuinte antes de implementar a exportação.

---

## 2. INSS — Protecção Social Obrigatória

### 2.1 Base legal

- **Lei n.º 7/04, de 15 de Outubro** — Lei de Bases da Protecção Social (em revisão em 2026, ainda não aprovada — Miranda, boletim Abr–Jun 2026, `fontes/Miranda-2026-abr-jun-boletim-laboral.pdf`) [SECUNDÁRIO].
- **Decreto Presidencial n.º 227/18, de 27 de Setembro** (DR I Série n.º 147) — Regime Jurídico de Vinculação e de Contribuição da Protecção Social Obrigatória; revoga o Decreto 38/08; em vigor 90 dias após publicação (27-12-2018). [OFICIAL] `fontes/DP-227-18-INSS-DR.pdf`, OCR `fontes/ocr/DP-227-18-INSS-ocr.txt` — https://lex.ao/docs/presidente-da-republica/2018/decreto-presidencial-n-o-227-18-de-27-de-setembro/
- Decreto Presidencial n.º 11/26, de 8 de Janeiro — comunicação e tramitação electrónica dos procedimentos da Protecção Social Obrigatória (registo obrigatório no site do INSS, notificações electrónicas com presunção aos 10 dias) [SECUNDÁRIO] PLMJ (https://www.plmj.com/en/knowledge/informative-notes/Angola-The-legal-framework-for-electronic-processing-in-compulsory-social-protection/34315/).
- Decreto Presidencial n.º 95/26, de 22 de Maio — Regime Jurídico das Prestações Familiares (abono de família, maternidade, aleitamento); revoga o DP 8/11 excepto arts. 29.º–31.º e 35.º (subsídio de funeral) [SECUNDÁRIO] Miranda 2026, Cegid (https://www.cegid.com/ao/blog/novo-regime-juridico-prestacoes-familiares-angola/), AngoLEX (https://angolex.com/paginas/decreto-presidencial/regime-juridico-das-prestacoes-familiares-na-proteccao-social-obrigatoria-95a-26a.html).
- Não encontrei nenhum decreto a alterar as taxas de 8 %/3 % até 2026-10.

### 2.2 Taxas (art. 12.º DP 227/18) [OFICIAL]

> "1. A taxa contributiva é fixada em **8 % para a Entidade Empregadora e 3 % para o trabalhador**, do total das remunerações do trabalhador sobre as quais incidem as contribuições. 2. […] a taxa contributiva para o trabalhador já reformado é fixada em 8 %. 3. A legislação sobre regimes especiais […] pode fixar […] taxas […]. 5. A actualização da taxa contributiva […] é feita por Decreto Presidencial."

Sem tecto/limite máximo de base (o diploma não prevê nenhum) [OFICIAL por omissão]. Sem regra de arredondamento [INCERTO].

### 2.3 Base de incidência (art. 13.º DP 227/18) [OFICIAL]

> "1. Considera-se base de incidência contributiva a **remuneração ilíquida** do trabalhador, nomeadamente todas as prestações pecuniárias que, nos termos da relação jurídico-laboral, são devidas pelas Entidades Empregadoras aos trabalhadores.
> 2. No caso do trabalhador auferir parte da remuneração em espécie, esta deve ser referenciada em dinheiro […].
> 3. **Não integram** a base de incidência contributiva as seguintes prestações pecuniárias:
> a) As prestações sociais pagas pelas Entidades Empregadoras no âmbito da Protecção Social Obrigatória [abono de família, subsídio de maternidade pago por conta do INSS, etc.];
> b) **O valor correspondente ao Subsídio de Férias**;
> c) Os valores correspondentes à subscrição ou participação […] de modalidades de protecção social complementar […]."

Consequências práticas (dedução pela letra da lei; confirmadas por Miranda 10/2018, PLMJ 10/2018, MLGTS 01/2019 — `fontes/Miranda-2018-DP-227-18-INSS.pdf`, `fontes/PLMJ-2018-10-regime-contribuicoes-seg-social.pdf`, `fontes/MLGTS-2019-01-seg-social-DP-227-18.pdf`):

| Componente | INSS (3 % / 8 %) | IRT |
|---|---|---|
| Salário base | sim | sim |
| Subsídio de alimentação, transporte | **sim, na totalidade** (não há exclusão nem limite no DP 227/18) | não sujeito até Kz 30 000 cada |
| Horas extra, subsídio nocturno, turno, prémios, comissões, subsídio de renda | sim | sim |
| Subsídio de férias / gratificação de férias | **não** (al. b) | sim |
| **Subsídio de Natal / 13.º mês** | **sim** (não está excluído; Expansão e Miranda confirmam) | sim |
| Abono de família (prestação da PSO) | não (al. a) | não sujeito até 5 % do base |
| Compensação por rescisão/indemnização | [INCERTO] — não é "remuneração devida pela relação jurídico-laboral" em sentido estrito; a prática corrente é não contribuir; sem fonte oficial | sujeito |
| Remuneração em espécie | sim, valorizada em dinheiro | sim |

### 2.4 Folha de remunerações, prazo e pagamento [OFICIAL]

- Art. 14.º n.º 1: "As Entidades Empregadoras devem declarar à Entidade Gestora […] através da **folha de registo de remunerações**, a relação dos trabalhadores ao seu serviço, o valor da remuneração que constitui a base de incidência contributiva e a taxa contributiva aplicável." N.º 2: elaborada **através do sistema electrónico** disponibilizado pelo INSS. N.º 3: se não for declarada, vale a última remuneração declarada. N.º 4: pode ser suprida oficiosamente.
- Art. 15.º n.º 1: o pagamento de ambas as contribuições é da responsabilidade da entidade empregadora, que desconta directamente a parte do trabalhador. **N.º 2: "As contribuições devem ser pagas mensalmente, através da liquidação da guia de pagamento, até ao dia 10 do mês seguinte** àquele a que as contribuições dizem respeito, salvo nos regimes especiais".
- Art. 16.º: juros de mora de 1 % ao mês. Multas (cap. IV): entre 1 e 8 vezes a "remuneração média mensal" da empresa [SECUNDÁRIO PLMJ/MLGTS].
- Inscrição da empresa: 30 dias após constituição; inscrição do trabalhador e dependentes: 30 dias após início do vínculo (art. 7.º); comunicação de suspensão/cessação: 30 dias (art. 9.º).
- O diploma não fixa um prazo autónomo para a folha diferente do dia 10; na prática submete-se a folha na plataforma do INSS e paga-se a guia até ao dia 10 (Miranda 2018/2020). Nome da plataforma: "Plataforma Virtual do INSS" (Miranda 2026) [SECUNDÁRIO].

### 2.5 13.º mês e INSS

O subsídio de Natal entra na base no mês em que é pago (não há regra de diferimento) [OFICIAL por omissão]. O subsídio de férias fica de fora. A LGT (art. 238.º) fixa o mínimo de 50 % do salário base para cada um, pagos uma vez por ano de serviço efectivo, com proporcional por meses completos no 1.º ano/cessação.

### 2.6 Prestações familiares pagas pelo empregador (DP 95/26) [SECUNDÁRIO — confirmar no DR]

- Abono de família por filho/mês, pago pela entidade empregadora: Kz 2 400 (remuneração até 5 SMN), Kz 1 500 (5–10 SMN), Kz 900 (> 10 SMN); máximo 5 filhos; dos 37 aos 216 meses; condições de vacinação/escolaridade. (Miranda cita 6 000/4 000/2 000 mas esses são os valores do subsídio de aleitamento segundo a Cegid; discrepância a confirmar.)
- Subsídio de maternidade: 3 × média das últimas 12 remunerações declaradas (excluindo férias, Natal e irregulares); pré-maternidade 60 %; pago pela entidade empregadora por transferência em 30 dias e reembolsado pelo INSS.

---

## 3. Fórmulas de folha (LGT — Lei n.º 12/23, de 27 de Dezembro) [OFICIAL]

Fonte: `fontes/Lei-12-23-LGT-DR.pdf` (DR I Série n.º 245), OCR `fontes/ocr/Lei-12-23-LGT-ocr.txt` — https://lex.ao/docs/assembleia-nacional/2023/lei-n-o-12-23-de-27-de-dezembro/

- **Art. 237.º n.º 7 — salário-hora**: "S/H = (Sm x 12) / (52s x Hs), em que S/H significa o valor do salário-horário, Sm o salário-base mensal, 12 o número de meses do ano, 52s o número de semanas laborais do ano e Hs o horário normal semanal". Para 44 h: S/H = Sm × 12 / 2288 = Sm / 190,67.
- **Art. 148.º — período normal**: 44 h semanais e 8 h diárias (alargável a 54 h/semana em turnos/horário modulado; 9 h ou 10 h/dia em trabalho intermitente).
- **Art. 185.º n.º 1 — limites do trabalho extraordinário**: "a) 2 horas por dia normal de trabalho; b) 40 horas por mês de trabalho; c) 200 horas anuais" (n.º 2: casos de força maior fora dos limites; n.º 3: ultrapassagem com consentimento do trabalhador e autorização da IGT).
- **Art. 188.º — remuneração do trabalho extraordinário**: n.º 1 "Cada hora de trabalho extraordinário é remunerada com um adicional até ao limite de 30 horas por mês, correspondente a **50 %** do valor da hora normal"; n.º 2 "O tempo de trabalho extraordinário que exceda o limite estabelecido no número anterior é remunerado, por cada hora, com adicional de **75 %**"; n.º 3 os adicionais acumulam com outros (nomeadamente o nocturno do art. 182.º n.º 1); n.º 4 fracções: < 15 min não contam, 15–44 min = meia hora, 45–60 min = 1 hora; n.º 5 o dia/meio-dia de descanso complementar conta como dia normal para este efeito.
- **Art. 179.º/182.º — trabalho nocturno**: entre as 20:00 e as 06:00; **adicional de 20 % do salário de base** (substituível por redução de horário via convenção colectiva).
- **Art. 194.º — dia de descanso semanal**: valor do tempo trabalhado **+ 75 %**, com mínimo de 3 horas.
- **Art. 200.º — feriados**: n.º 1 feriados, tolerância de ponto e vésperas do Dia da Família e Ano Novo são dias normais para efeito de salário; n.º 2 trabalho em feriado por razões ponderosas oficialmente reconhecidas: "acréscimo de mais de um dia de salário normal" + 1 dia de descanso compensatório nos 3 dias seguintes; n.º 3 não se aplica a turnos. (Mesma regra no art. 8.º da Lei 10/11.)
- **Art. 170.º n.º 2 — regime de disponibilidade**: adicional de 20 % do salário base nos dias em disponibilidade [SECUNDÁRIO — lido via lex.ao, não conferido no OCR].
- **Art. 238.º — complementos anuais**: mínimo **50 % do salário-base** como gratificação de férias (paga até 15 dias antes do gozo) e mínimo **50 % do salário-base** como subsídio de Natal; proporcional aos meses completos quando não há 1 ano de serviço.
- **Art. 241.º** — salário mínimo nacional fixado pelo Presidente da República (ver `SALARIO-MINIMO.md`).
- **Art. 245.º** — salário pago até ao último dia útil do período (mês/quinzena/semana); na cessação, tudo pago nos 3 dias subsequentes.

---

## 4. Exemplo de cálculo (2026)

Trabalhador com salário base Kz 400 000, subsídio de alimentação Kz 40 000, subsídio de transporte Kz 25 000, sem férias/Natal no mês:

```
Base INSS   = 400 000 + 40 000 + 25 000            = 465 000
INSS trab.  = 3 %  × 465 000                       =  13 950
INSS empr.  = 8 %  × 465 000                       =  37 200
Não sujeito = 30 000 (alim.) + 25 000 (transp.)    =  55 000
MC IRT      = 465 000 − 13 950 − 55 000            = 396 050   -> 4.º escalão (300 000–500 000)
IRT         = 49 250 + 19 % × (396 050 − 300 000)  =  67 499,50
Líquido     = 465 000 − 13 950 − 67 499,50         = 383 550,50
```

---

## 5. Resumo do que é certo e do que não é

**Certo [OFICIAL]**: tabela 2026 (Lei 14/25 Anexo I, conferida na imagem do DR); isenção Kz 150 000; tabelas 2024–25 e 2020–23; base = bruto − INSS − não sujeitos; limites de Kz 30 000 (alimentação) e Kz 30 000 (transporte) separados; abono de família até 5 %; férias e Natal 100 % sujeitos a IRT; entrega do IRT até ao fim do mês seguinte; mapa mensal electrónico obrigatório (> 3 trabalhadores); INSS 3 %/8 % sobre remuneração ilíquida, excluindo apenas prestações sociais, subsídio de férias e protecção complementar; pagamento até ao dia 10 do mês seguinte; fórmula S/H; 50 %/75 %; 20 % nocturno; 2 h/40 h/200 h; 75 % descanso semanal.

**Incerto**: regra de arredondamento (não existe); tributação "em separado" dos subsídios anuais (sem base legal — por omissão somar ao mês); layout do template do mapa mensal (requer login); tratamento de indemnizações na base INSS; número exacto da Lei do OGE 2025 (18/24, via CABRI); valores do abono de família do DP 95/26 (fontes divergem 2 400 vs 6 000).
