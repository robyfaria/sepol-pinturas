begin;

-- ======================================================
-- 1) VINCULAR usuarios_app AO auth.users
-- ======================================================
alter table public.usuarios_app
add column if not exists auth_user_id uuid unique;

create index if not exists idx_usuarios_app_auth
on public.usuarios_app(auth_user_id);


-- ======================================================
-- 2) FUNÇÕES UTILITÁRIAS DE PERFIL
-- ======================================================

-- Retorna perfil do usuário logado
create or replace function public.fn_user_perfil()
returns text
language sql
stable
security definer
as $$
  select u.perfil
  from public.usuarios_app u
  where u.auth_user_id = auth.uid()
    and u.ativo = true
  limit 1
$$;

-- Retorna true se for ADMIN
create or replace function public.fn_user_is_admin()
returns boolean
language sql
stable
security definer
as $$
  select coalesce(public.fn_user_perfil() = 'ADMIN', false)
$$;


-- ======================================================
-- 3) HABILITAR RLS NAS TABELAS PRINCIPAIS
-- ======================================================

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

alter table public.pagamentos enable row level security;
alter table public.pagamento_itens enable row level security;
alter table public.recebimentos enable row level security;


-- ======================================================
-- 4) POLÍTICAS - TABELAS OPERACIONAIS
-- ADMIN + OPERACAO
-- ======================================================

do $$
declare
  t text;
begin
  foreach t in array array[
    'clientes','pessoas','obras','orcamentos','obra_fases',
    'servicos','orcamento_fase_servicos','alocacoes','apontamentos'
  ]
  loop
    execute format('
      create policy %I_select on public.%I
      for select
      using ( public.fn_user_perfil() in (''ADMIN'',''OPERACAO'') );
    ', t||'_sel', t);

    execute format('
      create policy %I_write on public.%I
      for insert, update, delete
      using ( public.fn_user_perfil() in (''ADMIN'',''OPERACAO'') );
    ', t||'_wrt', t);
  end loop;
end$$;


-- ======================================================
-- 5) POLÍTICAS - FINANCEIRO (SOMENTE ADMIN)
-- ======================================================

do $$
declare
  t text;
begin
  foreach t in array array[
    'pagamentos','pagamento_itens','recebimentos'
  ]
  loop
    execute format('
      create policy %I_admin_only on public.%I
      for all
      using ( public.fn_user_is_admin() );
    ', t||'_adm', t);
  end loop;
end$$;


-- ======================================================
-- 6) POLÍTICAS - CONFIGURAÇÕES (SOMENTE ADMIN)
-- ======================================================

create policy usuarios_admin_only
on public.usuarios_app
for all
using ( public.fn_user_is_admin() );

create policy auditoria_admin_only
on public.auditoria
for all
using ( public.fn_user_is_admin() );


commit;
