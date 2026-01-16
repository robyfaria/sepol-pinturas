set statement_timeout = '15min';

begin;

-- =========================================================
-- RESET TOTAL
-- =========================================================
drop schema if exists public cascade;
create schema public;

grant usage on schema public to postgres, anon, authenticated, service_role;
grant all on schema public to postgres, service_role;

alter default privileges in schema public grant all on tables    to postgres, service_role;
alter default privileges in schema public grant all on sequences to postgres, service_role;
alter default privileges in schema public grant all on functions to postgres, service_role;

alter default privileges in schema public grant select, insert, update, delete on tables to authenticated;
alter default privileges in schema public grant select on tables to anon;

-- =========================================================
-- EXTENSÕES
-- =========================================================
create extension if not exists pgcrypto;

-- =========================================================
-- 1) USUÁRIOS DO APP (liga com auth.users)
-- =========================================================
create table public.usuarios_app (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid not null unique, -- = auth.users.id
  usuario text not null unique,      -- nome amigável (ex: "Robson")
  perfil text not null default 'OPERACAO' check (perfil in ('ADMIN','OPERACAO')),
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

create index idx_usuarios_app_auth_user on public.usuarios_app(auth_user_id);
create index idx_usuarios_app_perfil on public.usuarios_app(perfil);

-- =========================================================
-- 2) AUDITORIA (logs)
-- =========================================================
create table public.auditoria (
  id bigserial primary key,
  usuario text,
  entidade text not null,
  entidade_id text,
  acao text not null,
  antes_json jsonb,
  depois_json jsonb,
  criado_em timestamptz not null default now()
);

create index idx_auditoria_entidade on public.auditoria(entidade);
create index idx_auditoria_data on public.auditoria(criado_em);

-- =========================================================
-- 3) FUNÇÕES DE PERFIL (base das políticas)
-- =========================================================
create or replace function public.fn_user_perfil()
returns text
language sql
stable
security definer
set search_path = public
as $$
  select u.perfil
  from public.usuarios_app u
  where u.auth_user_id = auth.uid()
    and u.ativo = true
  limit 1
$$;

create or replace function public.fn_is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.fn_user_perfil() = 'ADMIN'
$$;

create or replace function public.fn_is_operacao()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.fn_user_perfil() = 'OPERACAO'
$$;

-- =========================================================
-- 4) CADASTROS (sem indicações no DEV refactor)
-- =========================================================
create table public.clientes (
  id bigserial primary key,
  nome text not null,
  telefone text,
  endereco text,
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

create table public.pessoas (
  id bigserial primary key,
  nome text not null,
  tipo text not null check (tipo in ('PINTOR','AJUDANTE','TERCEIRO')),
  telefone text,
  diaria_base numeric(12,2),
  observacao text,
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

-- =========================================================
-- 5) OBRAS / ORÇAMENTOS / FASES
-- =========================================================
create table public.obras (
  id bigserial primary key,
  cliente_id bigint not null references public.clientes(id) on update cascade on delete restrict,
  titulo text not null,
  endereco_obra text,
  status text not null default 'AGUARDANDO'
    check (status in ('AGUARDANDO','INICIADO','PAUSADO','CANCELADO','CONCLUIDO')),
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

create index idx_obras_cliente on public.obras(cliente_id);
create index idx_obras_status on public.obras(status);
create index idx_obras_ativo on public.obras(ativo);

create table public.orcamentos (
  id bigserial primary key,
  obra_id bigint not null references public.obras(id) on update cascade on delete cascade,
  versao integer not null default 1,
  titulo text not null default 'Orçamento',
  status text not null default 'RASCUNHO'
    check (status in ('RASCUNHO','EMITIDO','APROVADO','REPROVADO','CANCELADO')),
  observacao text,
  valor_total numeric(12,2) not null default 0,
  desconto_valor numeric(12,2) not null default 0,
  valor_total_final numeric(12,2) not null default 0,
  criado_em timestamptz not null default now(),
  aprovado_em date,
  cancelado_em date,
  unique (obra_id, versao)
);

create index idx_orcamentos_obra on public.orcamentos(obra_id);
create index idx_orcamentos_status on public.orcamentos(status);

-- 1 APROVADO por obra
create unique index ux_orcamento_aprovado_por_obra
on public.orcamentos (obra_id)
where status='APROVADO';

create table public.obra_fases (
  id bigserial primary key,
  obra_id bigint not null references public.obras(id) on update cascade on delete cascade,
  orcamento_id bigint not null references public.orcamentos(id) on update cascade on delete cascade,
  nome_fase text not null,
  ordem int not null default 1 check (ordem>=1),
  status text not null default 'AGUARDANDO'
    check (status in ('AGUARDANDO','INICIADO','PAUSADO','CONCLUIDO','CANCELADO')),
  valor_fase numeric(12,2) not null default 0 check (valor_fase>=0),
  criado_em timestamptz not null default now(),
  constraint obra_fases_uniq unique (orcamento_id, ordem)
);

create index idx_fases_orcamento on public.obra_fases(orcamento_id);
create index idx_fases_obra on public.obra_fases(obra_id);

-- =========================================================
-- 6) SERVIÇOS (catálogo) + itens por fase
-- =========================================================
create table public.servicos (
  id bigserial primary key,
  nome text not null unique,
  unidade text not null default 'UN' check (unidade in ('UN','M2','ML','H','DIA')),
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

create table public.orcamento_fase_servicos (
  id bigserial primary key,
  orcamento_id bigint not null references public.orcamentos(id) on update cascade on delete cascade,
  obra_fase_id bigint not null references public.obra_fases(id) on update cascade on delete cascade,
  servico_id bigint not null references public.servicos(id) on update cascade on delete restrict,
  quantidade numeric(12,2) not null default 1 check (quantidade>0),
  valor_unit numeric(12,2) not null default 0 check (valor_unit>=0),
  valor_total numeric(12,2) not null default 0 check (valor_total>=0),
  observacao text,
  criado_em timestamptz not null default now(),
  constraint ofs_uniq unique (obra_fase_id, servico_id)
);

create index idx_ofs_orc on public.orcamento_fase_servicos(orcamento_id);
create index idx_ofs_fase on public.orcamento_fase_servicos(obra_fase_id);

-- total = quantidade * valor_unit
create or replace function public.fn_ofs_calc_total()
returns trigger language plpgsql as $$
begin
  new.valor_total := round(coalesce(new.quantidade,0) * coalesce(new.valor_unit,0), 2);
  return new;
end;
$$;

drop trigger if exists trg_ofs_calc_total on public.orcamento_fase_servicos;
create trigger trg_ofs_calc_total
before insert or update of quantidade, valor_unit
on public.orcamento_fase_servicos
for each row execute function public.fn_ofs_calc_total();

-- =========================================================
-- 7) ALOCAÇÕES (planejamento diário)
-- =========================================================
create table public.alocacoes (
  id bigserial primary key,
  data date not null,
  pessoa_id bigint not null references public.pessoas(id) on update cascade on delete restrict,
  obra_id bigint not null references public.obras(id) on update cascade on delete restrict,
  orcamento_id bigint references public.orcamentos(id) on update cascade on delete set null,
  obra_fase_id bigint references public.obra_fases(id) on update cascade on delete set null,
  periodo text not null default 'INTEGRAL' check (periodo in ('INTEGRAL','MEIO')),
  tipo text not null default 'INTERNO' check (tipo in ('INTERNO','EXTERNO')),
  observacao text,
  criado_em timestamptz not null default now()
);

create index idx_alocacoes_data on public.alocacoes(data);
create index idx_alocacoes_pessoa on public.alocacoes(pessoa_id);
create index idx_alocacoes_obra on public.alocacoes(obra_id);

-- =========================================================
-- 8) APONTAMENTOS (produção)
-- =========================================================
create table public.apontamentos (
  id bigserial primary key,
  obra_id bigint not null references public.obras(id) on update cascade on delete restrict,
  orcamento_id bigint not null references public.orcamentos(id) on update cascade on delete cascade,
  obra_fase_id bigint references public.obra_fases(id) on update cascade on delete set null,
  pessoa_id bigint not null references public.pessoas(id) on update cascade on delete restrict,
  data date not null,
  tipo_dia text not null default 'NORMAL' check (tipo_dia in ('NORMAL','FERIADO','SABADO','DOMINGO')),
  valor_base numeric(12,2) not null default 0,
  acrescimo_pct numeric(6,4) not null default 0,
  desconto_valor numeric(12,2) not null default 0,
  valor_final numeric(12,2) not null default 0,
  observacao text,
  criado_em timestamptz not null default now(),
  constraint apont_uniq unique (obra_id, pessoa_id, data, orcamento_id)
);

create index idx_apont_data on public.apontamentos(data);
create index idx_apont_pessoa on public.apontamentos(pessoa_id);
create index idx_apont_orc on public.apontamentos(orcamento_id);

-- cálculo de valores (sábado 25%, domingo/feriado 100%)
create or replace function public.fn_apontamento_calcula_valores()
returns trigger language plpgsql as $$
declare
  pct numeric(6,4);
  bruto numeric(12,2);
begin
  pct := case new.tipo_dia
    when 'SABADO'  then 0.25
    when 'DOMINGO' then 1.00
    when 'FERIADO' then 1.00
    else 0.00
  end;

  new.acrescimo_pct := pct;
  bruto := round(coalesce(new.valor_base,0) * (1 + pct), 2);
  new.valor_final := greatest(0, round(bruto - coalesce(new.desconto_valor,0), 2));
  return new;
end;
$$;

drop trigger if exists trg_apontamento_calcula_valores on public.apontamentos;
create trigger trg_apontamento_calcula_valores
before insert or update of tipo_dia, valor_base, desconto_valor
on public.apontamentos
for each row execute function public.fn_apontamento_calcula_valores();

-- Guard: apontamento só em orçamento APROVADO
create or replace function public.fn_guard_apontamento_orcamento_aprovado()
returns trigger language plpgsql as $$
declare
  v_status text;
begin
  select status into v_status from public.orcamentos where id = new.orcamento_id;
  if v_status is null then
    raise exception 'Orçamento % não encontrado', new.orcamento_id;
  end if;

  if v_status <> 'APROVADO' then
    raise exception 'Só é permitido lançar apontamento em orçamento APROVADO. Status atual: %', v_status;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_guard_ap_orcamento on public.apontamentos;
create trigger trg_guard_ap_orcamento
before insert or update of orcamento_id
on public.apontamentos
for each row execute function public.fn_guard_apontamento_orcamento_aprovado();

-- =========================================================
-- 9) RECEBIMENTOS (ADMIN) — por fase
-- =========================================================
create table public.recebimentos (
  id bigserial primary key,
  orcamento_id bigint not null references public.orcamentos(id) on update cascade on delete cascade,
  obra_fase_id bigint not null references public.obra_fases(id) on update cascade on delete cascade,
  valor_previsto numeric(12,2) not null,
  acrescimo numeric(12,2) not null default 0,
  valor_total numeric(12,2) generated always as (valor_previsto + acrescimo) stored,
  vencimento date,
  status text not null default 'ABERTO' check (status in ('ABERTO','VENCIDO','PAGO','CANCELADO')),
  recebido_em date,
  criado_em timestamptz not null default now(),
  unique (obra_fase_id)
);

create index idx_receb_orc on public.recebimentos(orcamento_id);
create index idx_receb_status on public.recebimentos(status);

-- =========================================================
-- 10) PAGAMENTOS (ADMIN) + ITENS
-- =========================================================
create table public.pagamentos (
  id bigserial primary key,
  pessoa_id bigint not null references public.pessoas(id) on update cascade on delete restrict,
  tipo text not null check (tipo in ('SEMANAL','POR_FASE','EXTRA')),
  status text not null default 'ABERTO' check (status in ('ABERTO','PAGO','CANCELADO')),
  valor_total numeric(12,2) not null default 0,
  referencia_inicio date,
  referencia_fim date,
  obra_fase_id bigint references public.obra_fases(id) on update cascade on delete set null,
  pago_em date,
  criado_em timestamptz not null default now(),
  observacao text,
  constraint pagamentos_ref_chk check (
    (tipo in ('SEMANAL','EXTRA') and referencia_inicio is not null and referencia_fim is not null and obra_fase_id is null)
    or
    (tipo='POR_FASE' and obra_fase_id is not null and referencia_inicio is null and referencia_fim is null)
  )
);

create index idx_pag_status on public.pagamentos(status);
create index idx_pag_ref on public.pagamentos(referencia_inicio, referencia_fim);

-- unique NULL-safe
create unique index ux_pagamentos_chave
on public.pagamentos (pessoa_id, tipo, referencia_inicio, referencia_fim, (coalesce(obra_fase_id,0)));

create table public.pagamento_itens (
  id bigserial primary key,
  pagamento_id bigint not null references public.pagamentos(id) on update cascade on delete cascade,
  apontamento_id bigint references public.apontamentos(id) on update cascade on delete set null,
  descricao text not null,
  valor numeric(12,2) not null default 0 check (valor>=0)
);

create index idx_pi_pag on public.pagamento_itens(pagamento_id);

-- =========================================================
-- 11) FUNÇÃO: RECALCULAR ORÇAMENTO (fases + total + desconto)
-- =========================================================
create or replace function public.fn_recalcular_orcamento(p_orcamento_id bigint)
returns void language plpgsql as $$
declare
  v_total numeric(12,2);
  v_desc  numeric(12,2);
begin
  update public.obra_fases f
  set valor_fase = coalesce((
      select round(sum(ofs.valor_total),2)
      from public.orcamento_fase_servicos ofs
      where ofs.obra_fase_id = f.id
        and ofs.orcamento_id = p_orcamento_id
  ), 0)
  where f.orcamento_id = p_orcamento_id;

  select coalesce(round(sum(f.valor_fase),2),0)
    into v_total
  from public.obra_fases f
  where f.orcamento_id = p_orcamento_id;

  select coalesce(desconto_valor,0)
    into v_desc
  from public.orcamentos
  where id = p_orcamento_id;

  update public.orcamentos
  set valor_total = v_total,
      valor_total_final = greatest(0, round(v_total - greatest(0,v_desc),2))
  where id = p_orcamento_id;
end;
$$;

-- =========================================================
-- 12) RLS (simples, explícito e debugável)
-- =========================================================
alter table public.usuarios_app enable row level security;
alter table public.auditoria enable row level security;

alter table public.clientes enable row level security;
alter table public.pessoas enable row level security;
alter table public.obras enable row level security;
alter table public.orcamentos enable row level security;
alter table public.obra_fases enable row level security;
alter table public.servicos enable row level security;
alter table public.orcamento_fase_servicos enable row level security;
alter table public.alocacoes enable row level security;
alter table public.apontamentos enable row level security;

alter table public.recebimentos enable row level security;
alter table public.pagamentos enable row level security;
alter table public.pagamento_itens enable row level security;

-- --------- CONFIG (ADMIN only) ----------
create policy usuarios_app_admin_select
on public.usuarios_app for select
using (public.fn_is_admin());

create policy usuarios_app_admin_write
on public.usuarios_app for insert
with check (public.fn_is_admin());

create policy usuarios_app_admin_update
on public.usuarios_app for update
using (public.fn_is_admin())
with check (public.fn_is_admin());

create policy usuarios_app_admin_delete
on public.usuarios_app for delete
using (public.fn_is_admin());

create policy auditoria_admin_select
on public.auditoria for select
using (public.fn_is_admin());

create policy auditoria_admin_write
on public.auditoria for insert
with check (public.fn_is_admin());

-- --------- OPERACIONAL (ADMIN + OPERACAO) ----------
-- clientes
create policy clientes_sel on public.clientes for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy clientes_ins on public.clientes for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy clientes_upd on public.clientes for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy clientes_del on public.clientes for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- pessoas
create policy pessoas_sel on public.pessoas for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy pessoas_ins on public.pessoas for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy pessoas_upd on public.pessoas for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy pessoas_del on public.pessoas for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- obras
create policy obras_sel on public.obras for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy obras_ins on public.obras for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy obras_upd on public.obras for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy obras_del on public.obras for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- orcamentos
create policy orc_sel on public.orcamentos for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy orc_ins on public.orcamentos for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy orc_upd on public.orcamentos for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy orc_del on public.orcamentos for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- fases
create policy fases_sel on public.obra_fases for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy fases_ins on public.obra_fases for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy fases_upd on public.obra_fases for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy fases_del on public.obra_fases for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- serviços catálogo
create policy serv_sel on public.servicos for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy serv_ins on public.servicos for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy serv_upd on public.servicos for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy serv_del on public.servicos for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- serviços por fase
create policy ofs_sel on public.orcamento_fase_servicos for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy ofs_ins on public.orcamento_fase_servicos for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy ofs_upd on public.orcamento_fase_servicos for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy ofs_del on public.orcamento_fase_servicos for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- alocações
create policy aloc_sel on public.alocacoes for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy aloc_ins on public.alocacoes for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy aloc_upd on public.alocacoes for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy aloc_del on public.alocacoes for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- apontamentos
create policy ap_sel on public.apontamentos for select
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy ap_ins on public.apontamentos for insert
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy ap_upd on public.apontamentos for update
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'))
with check (public.fn_user_perfil() in ('ADMIN','OPERACAO'));
create policy ap_del on public.apontamentos for delete
using (public.fn_user_perfil() in ('ADMIN','OPERACAO'));

-- --------- FINANCEIRO (ADMIN only) ----------
create policy receb_admin_sel on public.recebimentos for select
using (public.fn_is_admin());
create policy receb_admin_ins on public.recebimentos for insert
with check (public.fn_is_admin());
create policy receb_admin_upd on public.recebimentos for update
using (public.fn_is_admin()) with check (public.fn_is_admin());
create policy receb_admin_del on public.recebimentos for delete
using (public.fn_is_admin());

create policy pag_admin_sel on public.pagamentos for select
using (public.fn_is_admin());
create policy pag_admin_ins on public.pagamentos for insert
with check (public.fn_is_admin());
create policy pag_admin_upd on public.pagamentos for update
using (public.fn_is_admin()) with check (public.fn_is_admin());
create policy pag_admin_del on public.pagamentos for delete
using (public.fn_is_admin());

create policy pi_admin_sel on public.pagamento_itens for select
using (public.fn_is_admin());
create policy pi_admin_ins on public.pagamento_itens for insert
with check (public.fn_is_admin());
create policy pi_admin_upd on public.pagamento_itens for update
using (public.fn_is_admin()) with check (public.fn_is_admin());
create policy pi_admin_del on public.pagamento_itens for delete
using (public.fn_is_admin());

commit;

insert into public.usuarios_app (auth_user_id, usuario, perfil, ativo)
values ('UUID_DO_AUTH_USER', 'Admin', 'ADMIN', true);
