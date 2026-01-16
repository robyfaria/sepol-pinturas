# SPEC — Regras de negócio (SEPOL - Pinturas)

Este documento resume as regras de negócio **identificadas no código do repositório** (UI Streamlit, queries SQL e funções auxiliares). Ele descreve o comportamento esperado do sistema de controle de obras e financeiro.

## 1) Autenticação e perfis
- O acesso ao sistema exige login com **usuário e senha**; sessões não autenticadas ficam bloqueadas até o login ser válido. A validação de senha ocorre no banco usando `crypt`, e usuários inativos não conseguem autenticar. 【F:utils/functions.py†L70-L157】
- Cada usuário possui **perfil** (ex.: `ADMIN` ou `OPERACAO`). O perfil controla menus e acesso a áreas sensíveis (Financeiro/Configuração apenas para `ADMIN`). 【F:app.py†L18-L66】
- O logout limpa a sessão e força novo login. 【F:utils/functions.py†L159-L166】

## 2) Navegação e permissões
- O menu lateral exibe **HOME, CADASTROS, OBRAS** para todos os perfis; **FINANCEIRO e CONFIG** aparecem apenas para usuários `ADMIN`. 【F:app.py†L34-L63】

## 3) Cadastros
### 3.1 Clientes
- **Nome é obrigatório** para criar/editar clientes. Sem nome, o salvamento é bloqueado com aviso. 【F:app.py†L200-L226】
- Campos opcionais: **telefone** e **endereço**; podem ser salvos como nulos. 【F:app.py†L206-L224】
- Clientes podem ser **ativados/inativados** via botão; o status controla visibilidade (filtro de ativos). 【F:app.py†L235-L259】
- No banco, novos clientes são criados como **ativos** e com `origem = 'PROPRIO'`. 【F:sql/query.sql†L35-L53】

### 3.2 Profissionais (Pessoas)
- **Nome é obrigatório** para criar/editar profissionais. 【F:app.py†L287-L320】
- Tipos de profissional aceitos: **PINTOR, AJUDANTE, TERCEIRO**. 【F:app.py†L268-L277】
- Campos opcionais: telefone, diária base, observação; diária base é salva apenas quando > 0. 【F:app.py†L279-L307】
- Profissionais também podem ser **ativados/inativados**. 【F:app.py†L332-L356】

## 4) Obras
- Uma obra sempre pertence a um **cliente** e só pode ser criada se existir ao menos um cliente cadastrado. 【F:app.py†L383-L400】
- **Título da obra é obrigatório** para salvar. 【F:app.py†L446-L470】
- Status disponíveis: **AGUARDANDO, INICIADO, PAUSADO, CANCELADO, CONCLUIDO**. 【F:app.py†L412-L419】
- Obras possuem atributo **ativo** para arquivar/ocultar; o status é o principal indicador de andamento. 【F:app.py†L367-L372】【F:app.py†L432-L440】
- É possível **editar**, **arquivar** e **reativar** obras a partir da lista. 【F:app.py†L520-L621】
- Há **mudança rápida de status** (INICIADO/PAUSADO/CONCLUIDO) diretamente na listagem; a troca só ocorre se o novo status for diferente do atual. 【F:app.py†L542-L588】

## 5) Home / Dashboard
- A Home mostra KPIs do dia e alertas financeiros quando a view `home_hoje_kpis` existe; falhas não bloqueiam o acesso. 【F:app.py†L73-L107】
- Exibe **alocações do dia** via view `alocacoes_hoje`, agrupadas por tipo. 【F:app.py†L113-L136】
- Exibe **pagamentos previstos para sexta** com total e detalhes. 【F:app.py†L144-L175】

## 6) Financeiro (somente ADMIN)
- Fluxo financeiro é **sequencial**: 1) gerar pagamentos da semana → 2) pagar pendentes → 3) estornar (apenas pagos). 【F:app.py†L624-L633】
- **Geração semanal**: usa a segunda-feira como referência e **não reabre pagamentos já pagos**. 【F:app.py†L641-L659】
- **Pagamentos pendentes** são exibidos por profissional; cada pagamento mostra tipo, referência e valor. 【F:app.py†L672-L726】
- O pagamento é marcado como **PAGO** com data informada pelo usuário. 【F:app.py†L663-L727】
- **Estorno** é permitido apenas para pagamentos pagos nos últimos 30 dias e **exige motivo**. Ao estornar, o pagamento volta para **ABERTO**. 【F:app.py†L736-L807】

## 7) Configurações (somente ADMIN)
- Admins podem **criar usuários** com perfil (`ADMIN` ou `OPERACAO`) e senha inicial **mínimo 6 caracteres**. 【F:app.py†L814-L857】
- Usuários podem ser **ativados/inativados**. 【F:app.py†L878-L909】
- É possível **resetar senha** com confirmação; senhas devem ter no mínimo 6 caracteres e precisam coincidir. 【F:app.py†L916-L965】
- A configuração exibe **auditoria** com os últimos 200 registros. 【F:app.py†L988-L1001】

## 8) Consultas e integrações com o banco
- O sistema usa **queries nomeadas** em `sql/query.sql` para CRUD e relatórios. Isso inclui: usuários, clientes, pessoas, obras, KPIs e financeiro. 【F:utils/functions.py†L18-L66】【F:sql/query.sql†L1-L89】
- Algumas regras financeiras dependem de **views/funções do banco** (`home_hoje_kpis`, `alocacoes_hoje`, `pagamentos_para_sexta`, `fn_gerar_pagamentos_semana`, `fn_marcar_pagamento_pago`, `fn_estornar_pagamento`). 【F:sql/query.sql†L69-L88】

---

> Observação: este SPEC descreve o comportamento observado no código atual; regras futuras devem ser adicionadas quando novas telas, entidades ou funções forem introduzidas.
