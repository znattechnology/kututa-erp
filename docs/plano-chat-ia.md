# Plano: chat do site com IA (módulo `kututa_ai_chat`)

Escrito a 30/10/2026. **Aprovado a 30/10/2026:** modelo Claude Opus 5.5; na fase 1 a proposta fica em rascunho até a equipa aprovar.

## Objectivo

O chat de kututa.ao atende o visitante numa conversa normal, em português de Angola, e conduz o processo até à proposta:

1. responde às perguntas;
2. qualifica o cliente;
3. regista-o no CRM;
4. marca a demonstração;
5. monta o orçamento com a tabela de preços da Vímeo.

Quando é preciso, passa a conversa a uma pessoa. O módulo existe só para a Vímeo: só se instala na base `kututa` e nunca nas bases dos clientes.

## Como funciona (implementado)

```
Visitante escreve no chat do site
        │  o widget do bot pede o passo seguinte (/chatbot/step/trigger) e mostra «a escrever…»
        ▼
chatbot.script.step do tipo «Conversa com IA» (kututa_ia): fica sempre no mesmo passo
        │
        ▼
kututa.ia.agente._responder: Claude (API da Anthropic) com as instruções e a base de conhecimento
(em cache) + o histórico da conversa guardado no canal + ferramentas
        │
        ├─ registar_contacto ─► crm.lead ligada à conversa
        ├─ consultar_precos ─► produtos KUT-* da Vímeo
        ├─ propor_orcamento ─► sale.order em RASCUNHO + actividade «Aprovar proposta»
        ├─ marcar_demonstracao ─► calendar.event «por confirmar» + actividade
        └─ passar_para_humano ─► operador online entra na conversa, ou aviso à equipa
        ▼
resposta publicada como «Assistente Kututa»
```

- **Sem fila.** A resposta é pedida dentro do passo do bot: o próprio widget do Odoo espera por ela e mostra «a escrever…». Assim encaixa no fluxo nativo do chat, e o Odoo pára o bot quando entra um operador humano. A produção tem 4 workers, por isso os poucos segundos de cada resposta não bloqueiam o site.
- **Histórico.** A conversa fica no canal (`kututa_ia_historico`), no formato da API, e só é acrescentada, nunca editada. Os blocos de raciocínio do Opus 5.5 têm de voltar exactamente como vieram.
- **Configuração.** O bot é o chatbot «Assistente Kututa» (`kututa_ai_chat.chatbot_kututa_ia`), com um só passo de IA. A primeira mensagem já leva o aviso de que é um assistente automático e de que a conversa fica registada.

## Ferramentas da IA

Todas são validadas no servidor. A IA pede; é o código que decide o que pode ser gravado.

| Ferramenta | O que faz | Limites |
|---|---|---|
| `registar_contacto` | Cria ou actualiza a oportunidade no CRM: nome, e-mail, telefone, empresa, NIF, sector, número de utilizadores, trabalhadores ou alunos, sistema actual e necessidades. | Só a oportunidade desta conversa. Nunca lê dados de outros clientes. |
| `consultar_precos` | Devolve os planos e serviços da tabela da Vímeo para um segmento: empresas, escolas ou ensino superior. | Só os produtos `KUT-*` da empresa Vímeo. A IA não pode inventar preços. |
| `propor_orcamento` | Cria um orçamento (`sale.order`) em rascunho para o cliente, com os produtos e quantidades da tabela. Exemplo: o plano Negócio com 10 meses de pagamento anual mais a implementação. | Preços sempre do Odoo, nunca do texto da IA. Sem descontos. **Fica em rascunho.** Cria uma actividade «Aprovar proposta» para a equipa. |
| `marcar_demonstracao` | Propõe horários livres da agenda da equipa e cria a reunião «por confirmar» (presencial ou online). | Só dentro do horário de trabalho. A confirmação chega ao cliente por e-mail depois de a equipa aceitar. |
| `passar_para_humano` | Chama um operador online. Se não houver ninguém, avisa o visitante e deixa uma actividade urgente no CRM. | Usado quando o cliente pede uma pessoa, pede desconto ou faz uma pergunta fora da base de conhecimento. |

**Fase 1: a proposta nunca sai sozinha.** A equipa aprova o rascunho com um clique e o Odoo envia o link para o cliente aceitar e assinar online. O envio automático fica para mais tarde, quando a equipa confiar nas propostas.

## Base de conhecimento e comportamento

- **Prompt de sistema fixo,** sempre em cache, com:
  - o que é o Kututa ERP e os módulos, a partir do site, do manual de marca e da secção de perguntas frequentes;
  - os prazos da AGT (DP 71/25, DE 683/25, 01/01/2027);
  - as escolas e o ensino superior;
  - as condições comerciais de `docs/comercial/tabela-precos.md`, sem os números, que vêm da ferramenta;
  - os contactos;
  - as regras de conduta.
- **Regras de conduta:**
  - português de Angola, frases curtas, sem jargão;
  - linguagem neutra, sem deduzir o género do visitante pelo nome;
  - diz logo no início que é um assistente automático;
  - nunca promete prazos de implementação nem faz descontos;
  - não pede dados sensíveis (palavras-passe, dados bancários);
  - não fala de concorrentes de forma depreciativa;
  - quando não sabe, passa a conversa a uma pessoa.
- **Aviso de privacidade** na primeira mensagem (Lei 22/11, de Protecção de Dados Pessoais): a conversa é tratada por um serviço de IA externo e fica guardada no CRM da Vímeo.
- **Defesa contra manipulação.** O texto do visitante é tratado como dados e nunca como instruções. As ferramentas só fazem o que está na tabela acima, por isso nenhuma mensagem do visitante consegue dar descontos, ler outros clientes ou enviar uma proposta.

## Modelo e custo

Preços da API por milhão de tokens, consultados a 30/10/2026. A cache do prompt de sistema reduz muito o custo de cada resposta.

| Modelo | Entrada | Saída | Custo estimado por conversa (≈10 mensagens) |
|---|---|---|---|
| Claude Opus 5.5 (o mais capaz) | 4 USD | 20 USD | ≈ 0,35 USD ≈ 320 Kz |
| Claude Sonnet 5.5 | 2 USD | 10 USD | ≈ 0,18 USD ≈ 165 Kz |
| Claude Haiku 5.5 (o mais rápido e barato) | 0,10 USD | 0,50 USD | ≈ 0,01 USD ≈ 10 Kz |

A estimativa assume:
- um prompt de sistema de cerca de 17 000 tokens, escrito na cache uma vez e lido da cache nas mensagens seguintes;
- cerca de 3 000 tokens novos de conversa por mensagem;
- cerca de 500 tokens de resposta por mensagem.

Com 200 conversas por mês, o custo fica em cerca de 64 000 Kz com o Opus, 33 000 Kz com o Sonnet ou 2 000 Kz com o Haiku. Uma única venda do plano Negócio, com 350 000 Kz de implementação, paga anos de chat.

Configuração proposta:
- o modelo, o esforço (`low` para conversa) e o número máximo de mensagens por conversa ficam em parâmetros de sistema, para se poderem mudar sem programar;
- `fallbacks: "default"` activo, para a IA não ficar sem resposta se uma pergunta for recusada pelos filtros de segurança do modelo.

## Segurança e limites

- **Chave da API:** fica no ficheiro `.env` da VPS (`/opt/kututa/app/.env`, chmod 600, `ANTHROPIC_API_KEY=`), que o compose passa ao container como variável de ambiente. Nunca vai para o git nem para a base de dados.
- **Limites por conversa:** no máximo 30 respostas da IA (`kututa_ia.max_respostas`), até 6 chamadas à API por mensagem e mensagens do visitante cortadas aos 4 000 caracteres. **Por fazer:** um limite de conversas por IP; para já, a protecção contra abusos é o tecto de gasto na consola da Anthropic.
- **Tecto de gasto mensal** definido na consola da Anthropic.
- **Registo de cada pedido:** tokens de entrada, de saída e da cache, e o custo em USD, em **Live Chat › Relatórios › Custos do chat com IA**.
- **Se a API falhar:** o visitante recebe «Neste momento não consigo responder…», com o telefone da equipa, e fica uma actividade no CRM. A conversa nunca fica sem resposta.

## Fases

| Fase | Entregável | Esforço |
|---|---|---|
| 1 | Módulo, fila com cron, conversa com a base de conhecimento, `registar_contacto`, `passar_para_humano`, limites, registo de custos, testes com a API simulada | 1 a 2 dias |
| 2 | `consultar_precos` e `propor_orcamento` com rascunho e actividade de aprovação | 1 dia |
| 3 | `marcar_demonstracao` com a agenda da equipa | 1 dia |
| 4 | Afinação com conversas reais: perguntas novas na base de conhecimento, revisão semanal das conversas | contínuo |
| Mais tarde | Envio automático da proposta, se for decidido | — |

**Antes de abrir ao público,** testa-se na base local com conversas-tipo: uma loja, uma empresa média, um colégio, uma universidade, um visitante que pede desconto e um que tenta manipular a IA. Depois abre-se em kututa.ao.

## O que é preciso decidir ou fornecer

1. **Chave da API da Anthropic**, criada em console.anthropic.com por quem gere a conta. A chave vai directamente para o ficheiro da VPS e nunca passa pelo chat.
2. **Modelo:** Opus 5.5, Sonnet 5.5 ou Haiku 5.5.
3. **Horário e operadores** para passar a pessoas: quem atende e em que horas.
4. **Tecto de gasto mensal** na consola da Anthropic.
5. **Confirmar a regra da fase 1:** a proposta fica em rascunho até alguém da equipa a aprovar.
