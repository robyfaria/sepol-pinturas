-- 001_add_scripts.sql
-- Seed rapido (30s) para DEV
-- Rode depois do 000_core.sql.
-- IMPORTANTE: troque as senhas apos o primeiro login.

begin;

-- =========================
-- Usuarios do app (ADMIN / OPERACAO)
-- =========================
with novos(usuario, senha, perfil) as (
  values
    ('admin',    'admin2026',    'ADMIN'),
    ('operacao', 'operacao2026', 'OPERACAO')
)
insert into public.usuarios_app (usuario, senha_hash, perfil, ativo)
select n.usuario, crypt(n.senha, gen_salt('bf')), n.perfil, true
from novos n
on conflict (usuario) do nothing;

-- =========================
-- Cadastros base
-- =========================
-- Clientes
insert into public.clientes (nome, telefone, endereco, ativo)
values
  ('Cliente Teste 01', '11999990001', 'Rua A, 100', true),
  ('Cliente Teste 02', '11999990002', 'Rua B, 200', true)
on conflict do nothing;

-- Profissionais
insert into public.pessoas (nome, tipo, telefone, diaria_base, observacao, ativo)
values
  ('Joao Pintor',   'PINTOR',    '11988880001', 180, null, true),
  ('Maria Pintora', 'PINTOR',    '11988880002', 200, null, true),
  ('Pedro Ajudante','AJUDANTE',  '11988880003', 140, null, true),
  ('Terceiro Z',    'TERCEIRO',  '11988880004', 0,   'Empreita quando precisar', true)
;

-- Obra + Orcamento + Fases (um fluxo completo)
do $$
declare
  v_cliente_id bigint;
  v_obra_id bigint;
  v_orc_id bigint;
  v_f1 bigint;
  v_srv1 bigint;
  v_srv2 bigint;
begin
  select id into v_cliente_id from public.clientes order by id asc limit 1;

  insert into public.obras (cliente_id, titulo, endereco_obra, status, ativo)
  values (v_cliente_id, 'Obra Teste - Apartamento', 'Av. Central, 123', 'INICIADO', true)
  returning id into v_obra_id;

  insert into public.orcamentos (obra_id, versao, titulo, status)
  values (v_obra_id, 1, 'Orcamento V1', 'APROVADO')
  returning id into v_orc_id;

  insert into public.obra_fases (obra_id, orcamento_id, nome_fase, ordem, status)
  values
    (v_obra_id, v_orc_id, 'Preparacao e Aplicacao', 1, 'AGUARDANDO')
  returning id into v_f1;

  -- o returning acima pega so o primeiro id; buscar os dois
  select id into v_f1 from public.obra_fases where orcamento_id=v_orc_id and ordem=1;

  insert into public.servicos (nome, unidade, ativo)
  values
    ('Pintura parede interna', 'M2', true)
    ,('Lixamento',             'M2', true)
  on conflict (nome) do nothing;

  select id into v_srv1 from public.servicos where nome='Pintura parede interna';
  select id into v_srv2 from public.servicos where nome='Lixamento';

  insert into public.orcamento_fase_servicos (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit, observacao)
  values
    (v_orc_id, v_f1, v_srv2, 80,  6, null)
    ,(v_orc_id, v_f1, v_srv1, 80, 18, null)
  on conflict do nothing;

  -- Recalcula totais (fases + orcamento)
  perform public.fn_recalcular_orcamento(v_orc_id);

  -- Recebimentos por fase (previsto = valor_fase)
  insert into public.recebimentos (orcamento_id, obra_fase_id, valor_previsto, acrescimo, vencimento, status)
  select v_orc_id, f.id, f.valor_fase, 0, current_date + (f.ordem*7), 'ABERTO'
  from public.obra_fases f
  where f.orcamento_id=v_orc_id
  on conflict (obra_fase_id) do nothing;

  -- Alocacoes (hoje) - 2 profissionais
  insert into public.alocacoes (data, pessoa_id, obra_id, orcamento_id, obra_fase_id, tipo, observacao)
  select current_date, p.id, v_obra_id, v_orc_id, v_f1, 'INTERNO', 'Seed - alocacao'
  from public.pessoas p
  where p.tipo in ('PINTOR','AJUDANTE')
  order by p.id
  limit 1
  on conflict (data, pessoa_id) do nothing;

  -- Apontamentos (hoje) - usa diaria_base dos profissionais
  insert into public.apontamentos (obra_id, orcamento_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
  select v_obra_id, v_orc_id, v_f1, p.id, current_date, 'NORMAL', coalesce(p.diaria_base,0), 0, 'Seed'
  from public.pessoas p
  where p.tipo in ('PINTOR','AJUDANTE')
  order by p.id
  limit 1
  on conflict (obra_id, pessoa_id, data) do nothing;

end $$;

commit;
