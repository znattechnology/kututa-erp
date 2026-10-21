# Fase 5g: Secretaria Express, perfis e acessos (`edu_roles`)

**Estado:** concluída a 2026-10-21. Testes: 3 no `edu_roles`. A bateria dos 22 módulos tem 261 testes e 0 falhas. Instalado na base `kututa_demo`, com um utilizador por perfil (secretaria, tesouraria, professor).

**Objectivo:** cada perfil vê só o que lhe pertence na parte académica, como os papéis do secPed.

## Perfis
| Kututa | secPed | Grupo | Vê |
|---|---|---|---|
| Professor | TEACHER | `edu_core.group_edu_teacher` | «A minha docência» (as minhas aulas, turmas, avaliações, horário, vigilâncias), Pedagógico e Avaliação das suas turmas |
| Secretaria | ADMIN_SERVICOS | `edu_core.group_edu_user` | Alunos, encarregados, turmas, matrículas, candidaturas, transferências, exames, arquivo e documentos; lê as bolsas. **Não factura nem recebe** |
| Tesouraria | ADMIN_FINANCAS | `edu_fees.group_edu_finance` (novo; implica a facturação do `account`) | Propinas: planos, facturas, pagamentos, serviços, bolsas, multas, devedores; e o menu «Alunos» (só leitura), o mesmo da Secretaria |
| Direcção | SCHOOL_ADMIN | `edu_core.group_edu_manager` (implica Secretaria e Tesouraria) | Tudo o que a Secretaria e a Tesouraria vêem, mais a configuração académica; «A minha docência» só se também for professor |
| RH, contabilidade | — | grupos do Odoo (`hr`, `account`) | As aplicações respectivas |
| Alunos e encarregados | STUDENT, GUARDIAN | portal | Fase 6 (`edu_portal`) |

## `edu_roles`
- Depende de `edu_fees` e `spreadsheet_dashboard`; `auto_install`.
- `views/edu_teaching_views.xml`: secção «A minha docência» com acções filtradas por `uid` (o professor é o `hr.employee` ligado ao utilizador).
- `data/menu_groups.xml`: `group_ids` em 64 menus da suite, por perfil. Esconde também as aplicações que não são do perfil: Definições e Painéis só para administradores, Funcionários para o RH e a Direcção, Contactos para quem gere parceiros.
- O menu raiz passa a chamar-se **Secretaria Express** (antes «Matrículas»), porque agrupa toda a suite e é visto por todos os perfis.

## Alterações no `edu_fees`
- A Secretaria deixa de implicar a facturação; os assistentes de pagamento e de serviço passam para a Tesouraria.
- Os botões «Receber pagamento», «Cobrar serviço» e o contador de facturas na ficha do aluno só aparecem à Tesouraria.

## Testes
- Teste de fumo: cada perfil abre a lista e a ficha de todos os menus `edu.*` que vê, com os campos das vistas (incluindo as sub-listas).
- Perfil público dos funcionários: a Secretaria e os professores lêem os campos de professor sem acesso ao RH (`hr.employee.public`).
- Menus visíveis por perfil, tal como na interface (um menu só conta se todos os ascendentes forem visíveis; o `_visible_menu_ids` do Odoo devolve folhas com o pai escondido).
- Acessos: a Secretaria não cria facturas; a Tesouraria não lê candidaturas nem aulas; o professor não lê candidaturas, só cria aulas das suas turmas e «As minhas turmas» devolve só as suas.

## Por fazer
- Permissões finas dentro da Secretaria (por exemplo, quem emite documentos oficiais ou quem anula matrículas), se a Vovó Eva precisar.
- Coordenador de curso e director de turma como perfis próprios (hoje são campos e regras de registo).
