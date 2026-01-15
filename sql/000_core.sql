-- sepol-pinturas/sql/000_core.sql
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
-- USUÁRIOS DO APP (login simples)
-- =========================================================
create table public.usuarios_app (
  id uuid primary key default gen_random_uuid(),
  usuario text not null unique,
  senha_hash text not null, -- crypt(plain, gen_salt('bf'))
  perfil text not null default 'OPERACAO'
    check (perfil in ('ADMIN','OPERACAO')),
  ativo boolean not null default true,
  ultimo_login_em timestamptz,
  criado_em timestamptz not null default now()
);

create index idx_usuarios_app_ativo on public.usuarios_app(ativo);
create index idx_usuarios_app_perfil on public.usuarios_app(perfil);

-- =========================================================
-- AUDITORIA (logs para tela Configurações)
-- =========================================================
create table public.auditoria (
  id bigserial primary key,
  usuario text,
  perfil text,
  ip text,
  entidade text not null,
  entidade_id text,
  acao text not null, -- CREATE / UPDATE / DELETE / STATUS_CHANGE / LOGIN / RESET_SENHA etc
  antes_json jsonb,
  depois_json jsonb,
  criado_em timestamptz not null default now()
);

create index idx_auditoria_entidade on public.auditoria(entidade);
create index idx_auditoria_data on public.auditoria(criado_em desc);

-- =========================================================
-- CONTEXTO DE USUÁRIO (para auditoria via trigger)
-- (o app pode fazer: select set_config('app.usuario','joao',true); set_config('app.perfil','ADMIN',true);
--  e opcionalmente set_config('app.ip','...',true); em cada request)
-- =========================================================
create or replace function public.fn_ctx_get(p_key text)
returns text
language sql
as $$
  select nullif(current_setting(p_key, true), '');
$$;

-- =========================================================
-- FUNÇÕES DE AUTH
-- =========================================================
create or replace function public.fn_hash_senha(p_senha text)
returns text
language sql
as $$
  select crypt(p_senha, gen_salt('bf'));
$$;

-- valida login e devolve perfil (ou null)
create or replace function public.fn_login(p_usuario text, p_senha text)
returns table(ok boolean, perfil text, msg text)
language plpgsql
as $$
declare
  v_hash text;
  v_perfil text;
  v_ativo boolean;
begin
  select senha_hash, perfil, ativo
    into v_hash, v_perfil, v_ativo
  from public.usuarios_app
  where usuario = p_usuario;

  if v_hash is null then
    return query select false, null::text, 'Usuário não encontrado';
    return;
  end if;

  if not v_ativo then
    return query select false, null::text, 'Usuário inativo';
    return;
  end if;

  if crypt(p_senha, v_hash) <> v_hash then
    insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
    values (p_usuario, null, public.fn_ctx_get('app.ip'), 'usuarios_app', null, 'LOGIN_FALHA', null, jsonb_build_object('motivo','senha_incorreta'));
    return query select false, null::text, 'Senha inválida';
    return;
  end if;

  update public.usuarios_app set ultimo_login_em = now() where usuario = p_usuario;

  insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
  values (p_usuario, v_perfil, public.fn_ctx_get('app.ip'), 'usuarios_app', null, 'LOGIN_OK', null, jsonb_build_object('usuario',p_usuario,'perfil',v_perfil));

  return query select true, v_perfil, 'OK';
end;
$$;

-- criar usuário (para tela Configurações - ADMIN)
create or replace function public.fn_usuario_criar(
  p_admin_usuario text,
  p_usuario text,
  p_senha text,
  p_perfil text default 'OPERACAO'
)
returns void
language plpgsql
as $$
begin
  if p_perfil not in ('ADMIN','OPERACAO') then
    raise exception 'Perfil inválido: %', p_perfil;
  end if;

  insert into public.usuarios_app(usuario, senha_hash, perfil, ativo)
  values (p_usuario, public.fn_hash_senha(p_senha), p_perfil, true);

  insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
  values (p_admin_usuario, 'ADMIN', public.fn_ctx_get('app.ip'), 'usuarios_app', p_usuario, 'CREATE', null,
          jsonb_build_object('usuario',p_usuario,'perfil',p_perfil,'ativo',true));
end;
$$;

-- reset de senha (ADMIN)
create or replace function public.fn_usuario_reset_senha(
  p_admin_usuario text,
  p_usuario text,
  p_nova_senha text
)
returns void
language plpgsql
as $$
declare
  v_antes jsonb;
  v_depois jsonb;
begin
  select to_jsonb(u) into v_antes from public.usuarios_app u where u.usuario = p_usuario;
  if v_antes is null then
    raise exception 'Usuário não encontrado: %', p_usuario;
  end if;

  update public.usuarios_app
  set senha_hash = public.fn_hash_senha(p_nova_senha)
  where usuario = p_usuario;

  select to_jsonb(u) into v_depois from public.usuarios_app u where u.usuario = p_usuario;

  insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
  values (p_admin_usuario, 'ADMIN', public.fn_ctx_get('app.ip'), 'usuarios_app', p_usuario, 'RESET_SENHA', v_antes, v_depois);
end;
$$;

-- ativar/inativar (ADMIN)
create or replace function public.fn_usuario_set_ativo(
  p_admin_usuario text,
  p_usuario text,
  p_ativo boolean
)
returns void
language plpgsql
as $$
declare
  v_antes jsonb;
  v_depois jsonb;
begin
  select to_jsonb(u) into v_antes from public.usuarios_app u where u.usuario = p_usuario;
  if v_antes is null then
    raise exception 'Usuário não encontrado: %', p_usuario;
  end if;

  update public.usuarios_app set ativo = p_ativo where usuario = p_usuario;

  select to_jsonb(u) into v_depois from public.usuarios_app u where u.usuario = p_usuario;

  insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
  values (p_admin_usuario, 'ADMIN', public.fn_ctx_get('app.ip'), 'usuarios_app', p_usuario, 'STATUS_CHANGE', v_antes, v_depois);
end;
$$;

-- =========================================================
-- CADASTROS (sem indicação)
-- =========================================================
create table public.clientes (
  id bigserial primary key,
  nome text not null,
  telefone text,
  endereco text,
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

create index idx_clientes_ativo on public.clientes(ativo);

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

create index idx_pessoas_ativo on public.pessoas(ativo);
create index idx_pessoas_tipo  on public.pessoas(tipo);

-- =========================================================
-- OBRAS / ORÇAMENTOS / FASES / SERVIÇOS
-- =========================================================
create table public.obras (
  id bigserial primary key,
  cliente_id bigint not null references public.clientes(id),
  titulo text not null,
  endereco_obra text,
  status text not null default 'AGUARDANDO'
    check (status in ('AGUARDANDO','INICIADO','PAUSADO','CANCELADO','CONCLUIDO')),
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

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
  criado_em timestamptz not null default now(),
  aprovado_em date,
  cancelado_em date,

  valor_total numeric(12,2) not null default 0,
  desconto_valor numeric(12,2) not null default 0,
  valor_total_final numeric(12,2) not null default 0,

  unique (obra_id, versao)
);

create index idx_orcamentos_obra on public.orcamentos(obra_id);
create index idx_orcamentos_status on public.orcamentos(status);

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

create table public.servicos (
  id bigserial primary key,
  nome text not null,
  unidade text not null default 'UN' check (unidade in ('UN','M2','ML','H','DIA')),
  ativo boolean not null default true,
  criado_em timestamptz not null default now(),
  constraint servicos_nome_uniq unique (nome)
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

-- =========================================================
-- PLANEJAMENTO (alocação diária)
-- =========================================================
create table public.alocacoes (
  id bigserial primary key,
  data date not null,
  pessoa_id bigint not null references public.pessoas(id),
  obra_id bigint not null references public.obras(id),
  orcamento_id bigint references public.orcamentos(id),
  obra_fase_id bigint references public.obra_fases(id),
  tipo text not null default 'INTERNO' check (tipo in ('INTERNO','EXTERNO')),
  observacao text,
  criado_em timestamptz not null default now(),
  unique (data, pessoa_id)
);

create index idx_alocacoes_data on public.alocacoes(data);

-- =========================================================
-- APONTAMENTOS (somente em orçamento APROVADO)
-- =========================================================
create table public.apontamentos (
  id bigserial primary key,
  obra_id bigint not null references public.obras(id),
  orcamento_id bigint not null references public.orcamentos(id) on update cascade on delete cascade,
  obra_fase_id bigint references public.obra_fases(id),
  pessoa_id bigint not null references public.pessoas(id),
  data date not null,
  tipo_dia text not null default 'NORMAL'
    check (tipo_dia in ('NORMAL','FERIADO','SABADO','DOMINGO')),
  valor_base numeric(12,2) not null default 0,
  acrescimo_pct numeric(6,4) not null default 0,
  desconto_valor numeric(12,2) not null default 0,
  valor_final numeric(12,2) not null default 0,
  observacao text,
  criado_em timestamptz not null default now(),
  constraint apontamentos_uniq unique (obra_id, pessoa_id, data)
);

create index idx_apontamentos_data on public.apontamentos(data);
create index idx_apontamentos_pessoa on public.apontamentos(pessoa_id);
create index idx_apontamentos_orcamento on public.apontamentos(orcamento_id);

-- =========================================================
-- RECEBIMENTOS (Cliente) por fase
-- =========================================================
create table public.recebimentos (
  id bigserial primary key,
  orcamento_id bigint not null references public.orcamentos(id) on update cascade on delete cascade,
  obra_fase_id bigint not null references public.obra_fases(id) on update cascade on delete cascade,
  valor_previsto numeric(12,2) not null,
  acrescimo numeric(12,2) not null default 0,
  valor_total numeric(12,2) generated always as (valor_previsto + acrescimo) stored,
  vencimento date,
  status text not null default 'ABERTO'
    check (status in ('ABERTO','VENCIDO','PAGO','CANCELADO')),
  recebido_em date,
  criado_em timestamptz not null default now(),
  unique (obra_fase_id)
);

create index idx_receb_orcamento on public.recebimentos(orcamento_id);

-- =========================================================
-- PAGAMENTOS
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

create index idx_pagamentos_status on public.pagamentos(status);
create index idx_pagamentos_ref on public.pagamentos(referencia_inicio, referencia_fim);

create unique index ux_pagamentos_chave
on public.pagamentos (pessoa_id, tipo, referencia_inicio, referencia_fim, (coalesce(obra_fase_id,0)));

create table public.pagamento_itens (
  id bigserial primary key,
  pagamento_id bigint not null references public.pagamentos(id) on delete cascade,
  apontamento_id bigint references public.apontamentos(id),
  descricao text not null,
  valor numeric(12,2) not null default 0
);

-- =========================================================
-- TRIGGERS DE CÁLCULO
-- =========================================================
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

  -- se valor_base vier 0 e existir diaria_base do profissional, usa como default
  if coalesce(new.valor_base,0) = 0 then
    select coalesce(diaria_base,0) into new.valor_base from public.pessoas where id = new.pessoa_id;
  end if;

  new.acrescimo_pct := pct;
  bruto := round(coalesce(new.valor_base,0) * (1 + pct), 2);
  new.valor_final := greatest(0, round(bruto - coalesce(new.desconto_valor,0), 2));
  return new;
end;
$$;

drop trigger if exists trg_apontamento_calcula_valores on public.apontamentos;
create trigger trg_apontamento_calcula_valores
before insert or update on public.apontamentos
for each row execute function public.fn_apontamento_calcula_valores();

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
-- RECALCULAR ORÇAMENTO (fases + total + desconto)
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
-- GERAR PAGAMENTOS (NUNCA reabre PAGO)
-- =========================================================
create or replace function public.fn_gerar_pagamentos_semana(p_data_segunda date)
returns void
language plpgsql
as $$
declare
  v_seg date := p_data_segunda;
  v_sex date := p_data_segunda + 4;
  v_dom date := p_data_segunda + 6;

  r record;
  v_pag_id bigint;
  v_status text;
begin
  -- SEMANAL (SEG-SEX) + FERIADO
  for r in
    select a.pessoa_id, sum(a.valor_final) as total
    from public.apontamentos a
    where a.data between v_seg and v_sex
      and a.tipo_dia in ('NORMAL','FERIADO')
    group by a.pessoa_id
    having sum(a.valor_final) > 0
  loop
    insert into public.pagamentos (pessoa_id, tipo, status, valor_total, referencia_inicio, referencia_fim, obra_fase_id)
    values (r.pessoa_id, 'SEMANAL', 'ABERTO', 0, v_seg, v_sex, null)
    on conflict (pessoa_id, tipo, referencia_inicio, referencia_fim, (coalesce(obra_fase_id,0)))
    do update set status = excluded.status
    where public.pagamentos.status <> 'PAGO'
    returning id into v_pag_id;

    if v_pag_id is null then
      continue;
    end if;

    select status into v_status from public.pagamentos where id = v_pag_id;
    if v_status = 'PAGO' then
      continue;
    end if;

    delete from public.pagamento_itens where pagamento_id = v_pag_id;

    insert into public.pagamento_itens (pagamento_id, apontamento_id, descricao, valor)
    select
      v_pag_id,
      a.id,
      'Diária ' || to_char(a.data,'DD/MM/YYYY') || ' (' || a.tipo_dia || ')',
      a.valor_final
    from public.apontamentos a
    where a.pessoa_id = r.pessoa_id
      and a.data between v_seg and v_sex
      and a.tipo_dia in ('NORMAL','FERIADO');

    update public.pagamentos p
    set valor_total = coalesce((select round(sum(pi.valor),2) from public.pagamento_itens pi where pi.pagamento_id=p.id),0)
    where p.id = v_pag_id;
  end loop;

  -- EXTRAS (SÁB/DOM) por dia
  for r in
    select a.pessoa_id, a.data as dia_extra, sum(a.valor_final) as total
    from public.apontamentos a
    where a.data between v_seg and v_dom
      and a.tipo_dia in ('SABADO','DOMINGO')
    group by a.pessoa_id, a.data
    having sum(a.valor_final) > 0
  loop
    insert into public.pagamentos (pessoa_id, tipo, status, valor_total, referencia_inicio, referencia_fim, obra_fase_id)
    values (r.pessoa_id, 'EXTRA', 'ABERTO', 0, r.dia_extra, r.dia_extra, null)
    on conflict (pessoa_id, tipo, referencia_inicio, referencia_fim, (coalesce(obra_fase_id,0)))
    do update set status = excluded.status
    where public.pagamentos.status <> 'PAGO'
    returning id into v_pag_id;

    if v_pag_id is null then
      continue;
    end if;

    select status into v_status from public.pagamentos where id = v_pag_id;
    if v_status = 'PAGO' then
      continue;
    end if;

    delete from public.pagamento_itens where pagamento_id = v_pag_id;

    insert into public.pagamento_itens (pagamento_id, apontamento_id, descricao, valor)
    select
      v_pag_id,
      a.id,
      'Extra ' || to_char(a.data,'DD/MM/YYYY') || ' (' || a.tipo_dia || ')',
      a.valor_final
    from public.apontamentos a
    where a.pessoa_id = r.pessoa_id
      and a.data = r.dia_extra
      and a.tipo_dia in ('SABADO','DOMINGO');

    update public.pagamentos p
    set valor_total = coalesce((select round(sum(pi.valor),2) from public.pagamento_itens pi where pi.pagamento_id=p.id),0)
    where p.id = v_pag_id;
  end loop;
end;
$$;

-- =========================================================
-- MARCAR PAGO / ESTORNAR (com auditoria)
-- =========================================================
create or replace function public.fn_marcar_pagamento_pago(
  p_pagamento_id bigint,
  p_usuario text,
  p_data date default current_date
)
returns void language plpgsql as $$
declare
  v_antes jsonb;
  v_depois jsonb;
begin
  select to_jsonb(p) into v_antes from public.pagamentos p where p.id = p_pagamento_id;
  if v_antes is null then raise exception 'Pagamento % não encontrado', p_pagamento_id; end if;

  if (v_antes->>'status') = 'PAGO' then return; end if;

  update public.pagamentos set status='PAGO', pago_em=p_data where id=p_pagamento_id;

  select to_jsonb(p) into v_depois from public.pagamentos p where p.id = p_pagamento_id;

  insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
  values (p_usuario, public.fn_ctx_get('app.perfil'), public.fn_ctx_get('app.ip'),
          'pagamentos', p_pagamento_id::text, 'STATUS_CHANGE', v_antes, v_depois);
end;
$$;

create or replace function public.fn_estornar_pagamento(
  p_pagamento_id bigint,
  p_usuario text,
  p_motivo text
)
returns void language plpgsql as $$
declare
  v_antes jsonb;
  v_depois jsonb;
begin
  select to_jsonb(p) into v_antes from public.pagamentos p where p.id = p_pagamento_id;
  if v_antes is null then raise exception 'Pagamento % não encontrado', p_pagamento_id; end if;

  if (v_antes->>'status') <> 'PAGO' then
    raise exception 'Só é possível estornar pagamento PAGO. Status atual: %', (v_antes->>'status');
  end if;

  update public.pagamentos
  set status='ABERTO',
      pago_em=null,
      observacao = trim(both from coalesce(observacao,'') || ' | ESTORNO: ' || coalesce(p_motivo,'(sem motivo)'))
  where id=p_pagamento_id;

  select to_jsonb(p) into v_depois from public.pagamentos p where p.id = p_pagamento_id;

  insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
  values (p_usuario, public.fn_ctx_get('app.perfil'), public.fn_ctx_get('app.ip'),
          'pagamentos', p_pagamento_id::text, 'ESTORNO', v_antes, v_depois);
end;
$$;

-- =========================================================
-- AUDITORIA GENÉRICA POR TRIGGER (CRUD)
-- (bom para clientes, pessoas, obras, orçamentos, fases, serviços, etc)
-- =========================================================
create or replace function public.fn_audit_trigger()
returns trigger
language plpgsql
as $$
declare
  v_usuario text := public.fn_ctx_get('app.usuario');
  v_perfil text := public.fn_ctx_get('app.perfil');
  v_ip text := public.fn_ctx_get('app.ip');
  v_ent text := TG_TABLE_NAME;
  v_id text;
  v_acao text;
  v_antes jsonb;
  v_depois jsonb;
begin
  if TG_OP = 'INSERT' then
    v_acao := 'CREATE';
    v_antes := null;
    v_depois := to_jsonb(NEW);
    v_id := coalesce((to_jsonb(NEW)->>'id'), null);
  elsif TG_OP = 'UPDATE' then
    v_acao := 'UPDATE';
    v_antes := to_jsonb(OLD);
    v_depois := to_jsonb(NEW);
    v_id := coalesce((to_jsonb(NEW)->>'id'), (to_jsonb(OLD)->>'id'), null);
  else
    v_acao := 'DELETE';
    v_antes := to_jsonb(OLD);
    v_depois := null;
    v_id := coalesce((to_jsonb(OLD)->>'id'), null);
  end if;

  insert into public.auditoria(usuario, perfil, ip, entidade, entidade_id, acao, antes_json, depois_json)
  values (v_usuario, v_perfil, v_ip, v_ent, v_id, v_acao, v_antes, v_depois);

  return coalesce(NEW, OLD);
end;
$$;

-- aplica triggers (CRUD) nos principais objetos
drop trigger if exists trg_aud_clientes on public.clientes;
create trigger trg_aud_clientes after insert or update or delete on public.clientes
for each row execute function public.fn_audit_trigger();

drop trigger if exists trg_aud_pessoas on public.pessoas;
create trigger trg_aud_pessoas after insert or update or delete on public.pessoas
for each row execute function public.fn_audit_trigger();

drop trigger if exists trg_aud_obras on public.obras;
create trigger trg_aud_obras after insert or update or delete on public.obras
for each row execute function public.fn_audit_trigger();

drop trigger if exists trg_aud_orcamentos on public.orcamentos;
create trigger trg_aud_orcamentos after insert or update or delete on public.orcamentos
for each row execute function public.fn_audit_trigger();

drop trigger if exists trg_aud_fases on public.obra_fases;
create trigger trg_aud_fases after insert or update or delete on public.obra_fases
for each row execute function public.fn_audit_trigger();

drop trigger if exists trg_aud_servicos on public.servicos;
create trigger trg_aud_servicos after insert or update or delete on public.servicos
for each row execute function public.fn_audit_trigger();

drop trigger if exists trg_aud_ofs on public.orcamento_fase_servicos;
create trigger trg_aud_ofs after insert or update or delete on public.orcamento_fase_servicos
for each row execute function public.fn_audit_trigger();

-- =========================================================
-- VIEWS (base para HOME / FINANCEIRO / OBRAS)
-- =========================================================
create or replace view public.pagamentos_pendentes as
select p.id, pe.nome pessoa_nome, pe.tipo pessoa_tipo, p.tipo, p.status, p.valor_total,
       p.referencia_inicio, p.referencia_fim, p.pago_em, p.criado_em
from public.pagamentos p
join public.pessoas pe on pe.id=p.pessoa_id
where p.status='ABERTO'
order by pe.nome, p.tipo, p.referencia_inicio nulls last;

create or replace view public.pagamentos_extras_pendentes as
select p.id, pe.nome pessoa_nome, p.valor_total, p.referencia_inicio as data_extra, p.criado_em
from public.pagamentos p
join public.pessoas pe on pe.id=p.pessoa_id
where p.status='ABERTO' and p.tipo='EXTRA'
order by p.referencia_inicio, pe.nome;

create or replace view public.pagamentos_pagos_30d as
select p.id, pe.nome pessoa_nome, p.tipo, p.valor_total, p.pago_em, p.referencia_inicio, p.referencia_fim
from public.pagamentos p
join public.pessoas pe on pe.id=p.pessoa_id
where p.status='PAGO'
  and p.pago_em >= (current_date - 30)
order by p.pago_em desc, p.id desc;

create or replace view public.alocacoes_hoje as
select a.data, p.nome profissional, o.titulo obra, a.tipo, a.observacao
from public.alocacoes a
join public.pessoas p on p.id=a.pessoa_id
join public.obras o on o.id=a.obra_id
where a.data=current_date
order by profissional;

create or replace view public.servicos_por_fase as
select
  ofs.id,
  ofs.orcamento_id,
  ofs.obra_fase_id,
  f.ordem,
  f.nome_fase,
  s.nome as servico,
  s.unidade,
  ofs.quantidade,
  ofs.valor_unit,
  ofs.valor_total,
  ofs.observacao
from public.orcamento_fase_servicos ofs
join public.obra_fases f on f.id=ofs.obra_fase_id
join public.servicos s on s.id=ofs.servico_id
order by ofs.orcamento_id desc, f.ordem asc, s.nome asc;

create or replace view public.pagamentos_para_sexta as
with params as (
  select (current_date + ((5 - extract(dow from current_date)::int + 7) % 7))::date as sexta_alvo
)
select
  p.id,
  pe.nome as pessoa_nome,
  p.tipo,
  p.status,
  p.valor_total,
  pr.sexta_alvo as sexta,
  p.referencia_inicio,
  p.referencia_fim,
  p.criado_em
from public.pagamentos p
join public.pessoas pe on pe.id = p.pessoa_id
cross join params pr
where p.status = 'ABERTO'
  and (
    (p.tipo = 'SEMANAL' and p.referencia_fim = pr.sexta_alvo)
    or
    (p.tipo = 'EXTRA' and p.referencia_inicio = pr.sexta_alvo)
  )
order by pe.nome, p.tipo, p.id;

create or replace view public.home_hoje_kpis as
with params as (
  select
    current_date as hoje,
    (current_date + ((5 - extract(dow from current_date)::int + 7) % 7))::date as sexta_alvo
)
select
  pr.hoje,
  pr.sexta_alvo as sexta,
  (select count(*) from public.obra_fases f where f.status in ('INICIADO','PAUSADO')) as fases_em_andamento,
  (select count(*) from public.recebimentos r where r.status in ('ABERTO','VENCIDO') and r.vencimento is not null and r.vencimento < pr.hoje) as recebimentos_vencidos_qtd,
  (select coalesce(round(sum(r.valor_total),2),0) from public.recebimentos r where r.status in ('ABERTO','VENCIDO')) as recebimentos_pendentes_total,
  (select coalesce(round(sum(p.valor_total),2),0)
   from public.pagamentos p
   where p.status='ABERTO'
     and ((p.tipo='SEMANAL' and p.referencia_fim=pr.sexta_alvo) or (p.tipo='EXTRA' and p.referencia_inicio=pr.sexta_alvo))
  ) as pagar_na_sexta_total,
  (select coalesce(round(sum(p.valor_total),2),0) from public.pagamentos p where p.status='ABERTO' and p.tipo='EXTRA') as extras_pendentes_total
from params pr;

commit;

-- =========================================================
-- NOTA: CRIAR PRIMEIRO ADMIN (rode UMA vez após o core)
-- Exemplo:
-- insert into public.usuarios_app (usuario, senha_hash, perfil, ativo)
-- values ('admin', public.fn_hash_senha('admin2026'), 'ADMIN', true);
-- =========================================================
