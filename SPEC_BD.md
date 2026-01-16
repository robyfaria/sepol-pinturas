# Especificação do Banco de Dados (Atual)

Este documento descreve o estado atual do banco conforme os scripts `sql/000_core.sql` e `sql/001_add_scripts.sql`.

## Extensões

- **pgcrypto**: utilizada para `gen_random_uuid` e hashing de senhas (`crypt`, `gen_salt`).

## Tabelas e relacionamentos

### Autenticação e auditoria

- **public.usuarios_app**
  - Login simples do app, com `usuario` único, `senha_hash`, `perfil` (`ADMIN`/`OPERACAO`), `ativo`, `ultimo_login_em` e `criado_em`.
  - Índices por `ativo` e `perfil`.
- **public.auditoria**
  - Armazena logs de ações (CRUD, login, reset de senha, mudança de status) com campos `entidade`, `entidade_id`, `acao`, `antes_json`, `depois_json` e dados de contexto.
  - Índices por `entidade` e data (`criado_em`).

### Cadastros básicos

- **public.clientes**
  - Clientes com `nome`, `telefone`, `endereco`, `ativo` e `criado_em`.
  - Índice por `ativo`.
- **public.pessoas**
  - Profissionais com `tipo` (`PINTOR`, `AJUDANTE`, `TERCEIRO`), diária base, observações e status.
  - Índices por `ativo` e `tipo`.

### Obras e orçamentos

- **public.obras**
  - Vincula-se a `clientes` e mantém `status` (`AGUARDANDO`, `INICIADO`, `PAUSADO`, `CANCELADO`, `CONCLUIDO`).
  - Índices por `status` e `ativo`.
- **public.orcamentos**
  - Vinculado à obra, possui `versao`, `status` (`RASCUNHO`, `EMITIDO`, `APROVADO`, `REPROVADO`, `CANCELADO`), valores (`valor_total`, `desconto_valor`, `valor_total_final`) e datas de aprovação/cancelamento.
  - Unicidade por `(obra_id, versao)` e apenas um orçamento `APROVADO` por obra.
- **public.obra_fases**
  - Fases da obra por orçamento, com `ordem`, `status` (`AGUARDANDO`, `INICIADO`, `PAUSADO`, `CONCLUIDO`, `CANCELADO`) e `valor_fase`.
  - Unicidade por `(orcamento_id, ordem)`.
- **public.servicos**
  - Serviços disponíveis e unidade (`UN`, `M2`, `ML`, `H`, `DIA`).
  - Unicidade por `nome`.
- **public.orcamento_fase_servicos**
  - Itens de serviço por fase com `quantidade`, `valor_unit` e `valor_total` calculado.
  - Unicidade por `(obra_fase_id, servico_id)`.

### Planejamento e apontamentos

- **public.alocacoes**
  - Alocação diária de pessoas em obra/fase, com `tipo` (`INTERNO`, `EXTERNO`).
  - Unicidade por `(data, pessoa_id)`.
- **public.apontamentos**
  - Lançamentos de produção por pessoa e obra, apenas para orçamento `APROVADO`.
  - Cálculo automático de acréscimo (sábado/domingo/feriado) e `valor_final`.
  - Unicidade por `(obra_id, pessoa_id, data)`.

### Financeiro

- **public.recebimentos**
  - Recebimentos por fase do orçamento, com `valor_total` gerado e `status` (`ABERTO`, `VENCIDO`, `PAGO`, `CANCELADO`).
  - Unicidade por `obra_fase_id`.
- **public.pagamentos**
  - Pagamentos a profissionais por tipo (`SEMANAL`, `POR_FASE`, `EXTRA`) e status (`ABERTO`, `PAGO`, `CANCELADO`).
  - Regras de referência via `pagamentos_ref_chk` e unicidade composta para evitar duplicatas.
- **public.pagamento_itens**
  - Itens do pagamento (normalmente originados dos apontamentos).

## Funções principais

- **Contexto de auditoria**: `public.fn_ctx_get` lê valores de `current_setting` (ex.: `app.usuario`, `app.perfil`, `app.ip`).
- **Auth**:
  - `public.fn_hash_senha` gera hash de senha.
  - `public.fn_login` valida usuário/senha, atualiza último login e registra auditoria.
  - `public.fn_usuario_criar`, `public.fn_usuario_reset_senha`, `public.fn_usuario_set_ativo` para administração de usuários com auditoria.
- **Cálculo automático**:
  - `public.fn_apontamento_calcula_valores` calcula acréscimo e valor final de apontamentos.
  - `public.fn_ofs_calc_total` calcula `valor_total` do item de serviço por fase.
- **Recalcular orçamento**:
  - `public.fn_recalcular_orcamento` soma serviços por fase e atualiza totais do orçamento.
- **Pagamentos**:
  - `public.fn_gerar_pagamentos_semana` gera pagamentos semanais e extras a partir dos apontamentos.
  - `public.fn_marcar_pagamento_pago` e `public.fn_estornar_pagamento` registram mudança de status com auditoria.
- **Auditoria genérica**:
  - `public.fn_audit_trigger` grava logs de `INSERT/UPDATE/DELETE`.

## Triggers

- **Apontamentos**:
  - `trg_apontamento_calcula_valores` (antes de insert/update) calcula valores.
  - `trg_guard_ap_orcamento` bloqueia apontamentos em orçamentos não aprovados.
- **Orçamento x Fases**:
  - `trg_ofs_calc_total` recalcula total do item de serviço.
- **Auditoria**:
  - Triggers `after insert/update/delete` em `clientes`, `pessoas`, `obras`, `orcamentos`, `obra_fases`, `servicos`, `orcamento_fase_servicos`.

## Views

- **public.pagamentos_pendentes**: lista pagamentos em aberto com dados de pessoas.
- **public.pagamentos_extras_pendentes**: extras pendentes por data.
- **public.pagamentos_pagos_30d**: pagamentos pagos nos últimos 30 dias.
- **public.alocacoes_hoje**: alocações do dia.
- **public.servicos_por_fase**: serviços detalhados por fase.
- **public.pagamentos_para_sexta**: pagamentos que vencem na próxima sexta.
- **public.home_hoje_kpis**: indicadores agregados para o dashboard.

## Seed / Dados iniciais (DEV)

O script `sql/001_add_scripts.sql` insere dados de desenvolvimento:

- Usuários `admin` (perfil `ADMIN`) e `operacao` (perfil `OPERACAO`).
- Dois clientes de teste e quatro pessoas (pintores, ajudante e terceiro).
- Uma obra de teste com orçamento aprovado, fase única, serviços, itens de orçamento, recebimentos, alocações e apontamentos.

> Observação: as senhas de seed são temporárias e devem ser alteradas após o primeiro login.
