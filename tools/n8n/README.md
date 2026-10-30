# n8n da prospecção

Fluxo de teste do contrato entre o n8n e o módulo `kututa_prospect` (ver `docs/fases/fase-8-kututa_prospect.md`, §6).

- **Onde corre:** na VPS de produção, **só para testes** (`/opt/kututa/n8n`, limite de 640 MiB, sem endereço público).
  No arranque real passa para uma VPS separada.
- **Acesso:** túnel SSH e depois http://localhost:5678 no navegador:

      ssh -L 5678:127.0.0.1:5678 deploy@167.233.145.77

- **Credenciais no n8n** (nunca no git):
  - «Odoo Kututa (n8n Prospecção)»: Header Auth, nome `Authorization`, valor `bearer <chave de API>` do utilizador
    técnico `n8n-prospect@kututa.ao` (âmbito `rpc`). A chave gera-se no servidor e fica num ficheiro com permissões 600.
  - «Google Places API»: Header Auth, nome `X-Goog-Api-Key`. Chave restringida na consola Google ao Places API (New) e
    ao IP da VPS, com quota diária.
- **Fluxo `kututa-prospeccao-teste.json`:** lê as consultas activas, entrega dois candidatos fictícios («TESTE …») e
  mostra o resultado de cada entrada (criado, duplicado, excluído, rejeitado). O ramo do Google Places vem desligado.
