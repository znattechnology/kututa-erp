# Fase 5e: Secretaria Express, propinas (`edu_fees`)

**Estado:** concluída a 2026-10-21. Testes: 11 no `edu_fees`. A bateria dos 21 módulos tem 258 testes e 0 falhas. Instalado na base `kututa_demo`: 8 facturas AGT (série FT26DEMOSEDE), um pagamento ao balcão, 3 devedores com a matrícula irregular e uma multa.

**Fonte:** as regras do secPed (`tuition-generation`, `invoice`, `payment`, `overdue`, `financial-standing` e `billing-config` services), levantadas por um agente. As divergências estão no fim.

## O que faz
- **Planos de propinas:** por ano lectivo e âmbito. O plano da turma prevalece sobre o da classe, este sobre o do curso e este sobre o geral; com dois planos no mesmo nível, vale o mais recente.
  - Taxas: matrícula, propina, exame, serviço a pedido, cartão e outras.
  - Periodicidade: única, mensal, trimestral ou anual, com prestações e dia de vencimento (1–28).
  - Valor com IVA incluído.
  - IVA por omissão: isento M21 (ensino, art. 12.º, n.º 1, al. l) do CIVA); 14% no cartão e nos outros bens.
- **Cada cobrança é uma factura do Odoo:**
  - publicada logo, por isso o `l10n_ao_edi` dá-lhe a série e o número AGT e envia-a;
  - linha «Propina — Outubro 2026»;
  - chave de geração única por empresa.
- **Geração:**
  - ao confirmar a matrícula e no cron diário;
  - mês a mês até ao mês corrente, sem nunca facturar um mês futuro e sem duplicar;
  - quem entra a meio do ano começa no mês da matrícula, mas a matrícula cobra-se sempre;
  - escola sem propina: só as outras taxas.
- **Adquirente** (DP 71/25, art. 10.º): o aluno com NIF, senão o encarregado principal com NIF, senão o aluno.
- **Bolsas:**
  - tipos: integral, parcial, mérito, carência, Estado, institucional;
  - só se aplicam à propina, se estiverem em vigor na data de vencimento, e vale a mais vantajosa (sem acumular);
  - o desconto fica na factura emitida;
  - a bolsa integral regista a cobrança, mas não emite factura;
  - aprovação por outro utilizador, e alterar uma bolsa aprovada volta a pedir aprovação (o secPed não o exigia nas alterações).
- **Multas por atraso:**
  - percentagem mensal ou valor fixo, depois da tolerância, com tecto;
  - **facturadas à parte**, de forma incremental: só se factura a diferença para o total devido. O secPed não emitia documento fiscal da multa.
  - IVA por omissão: não sujeito (M02). Confirmar com o contabilista.
- **Pagamento ao balcão:**
  - imputado às facturas em aberto, da mais antiga para a mais recente, com um pagamento por adquirente;
  - o excedente fica como crédito para as próximas facturas;
  - o recibo (RC) é tratado pelo `l10n_ao_edi`.
- **Serviço a pedido:** uma factura, sem duplicar quando se repete a referência do pedido.
- **Situação financeira:**
  - dívida vencida = em aberto com vencimento anterior a hoje menos a tolerância (8 dias);
  - isentos: bolseiros do Estado e menores de 15 anos;
  - modo **avisar** ou **bloquear**, aplicado à rematrícula, aos documentos e aos exames (os devedores bloqueados não são convocados);
  - matrícula **irregular** automática com dívida, que volta a activa quando paga (o secPed nunca a marcava);
  - lista de devedores.
- **Permissões:** a Secretaria passa a ter o grupo de facturação do Odoo.

## Divergências do secPed corrigidas
| secPed | Kututa |
|---|---|
| Multa somada à conta, sem factura | Factura de multa, incremental |
| Estado «irregular» nunca usado | Automático, com a dívida |
| Bloqueio de documentos e exames definido mas não ligado | Ligado aos documentos e à convocatória dos exames |
| Alterações de bolsas sem aprovação | Voltam a exigir aprovação |
| Sem código AGT de isenção | M21 no ensino, M02 nas multas, 14% no cartão e bens |
| Excedente numa carteira própria | Crédito do adquirente na contabilidade |

## Por decidir ou fazer
- **Comparticipada:** comporta-se como a propina mensal; o subsídio do Estado regista-se como bolsa do Estado.
- **Desistência ou transferência:** as facturas emitidas mantêm-se como dívida (como no secPed); a anulação, com nota de crédito, faz-se à mão.
- **Referência Multicaixa e conciliação bancária automática:** gateway EMIS ainda sem contrato.
- **Portal do encarregado:** facturas e pagamentos online, na fase 6.
