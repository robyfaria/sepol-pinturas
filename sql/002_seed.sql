set statement_timeout = '5min';

begin;

-- =========================================================
-- SEED RÁPIDO (30s) - DEV
-- =========================================================

-- Limpa dados (ordem segura por FK)
truncate table
  public.pagamento_itens,
  public.pagamentos,
  public.recebimentos,
  public.apontamentos,
  public.alocacoes,
  public.orcamento_fase_servicos,
  public.servicos,
  public.obra_fases,
  public.orcamentos,
  public.obras,
  public.pessoas,
  public.clientes
restart identity cascade;

-- -------------------------
-- Clientes
-- -------------------------
insert into public.clientes (nome, telefone, endereco, ativo) values
('Cliente A (Apê 101)', '11999990001', 'Rua A, 101', true),
('Cliente B (Casa)',    '11999990002', 'Rua B, 202', true),
('Cliente C (Loja)',    null,          'Av. C, 303', true);

-- -------------------------
-- Profissionais
-- -------------------------
insert into public.pessoas (nome, tipo, telefone, diaria_base, observacao, ativo) values
('João Pintor',     'PINTOR',    '11988880001', 180, null, true),
('Carlos Pintor',   'PINTOR',    '11988880002', 200, null, true),
('Pedro Ajudante',  'AJUDANTE',  '11988880003', 120, null, true),
('Marcos Terceiro', 'TERCEIRO',  null,          250, 'Empreita quando precisar', true);

-- -------------------------
-- Obras
-- -------------------------
insert into public.obras (cliente_id, titulo, endereco_obra, status, ativo)
select c.id, 'Obra 1 - Cliente A', 'Rua A, 101', 'AGUARDANDO', true from public.clientes c where c.nome like 'Cliente A%';

insert into public.obras (cliente_id, titulo, endereco_obra, status, ativo)
select c.id, 'Obra 2 - Cliente B', 'Rua B, 202', 'INICIADO', true from public.clientes c where c.nome like 'Cliente B%';

-- -------------------------
-- Orçamentos (1 por obra)
-- -------------------------
-- Obra 1: RASCUNHO
insert into public.orcamentos (obra_id, versao, titulo, status, observacao)
select o.id, 1, 'Orçamento V1', 'RASCUNHO', 'Seed DEV' from public.obras o where o.titulo like 'Obra 1%';

-- Obra 2: APROVADO (para permitir apontamentos)
insert into public.orcamentos (obra_id, versao, titulo, status, observacao, aprovado_em)
select o.id, 1, 'Orçamento V1', 'APROVADO', 'Seed DEV', current_date
from public.obras o where o.titulo like 'Obra 2%';

-- -------------------------
-- Fases (ligadas ao orçamento)
-- -------------------------
-- Obra 1 (RASCUNHO)
insert into public.obra_fases (obra_id, orcamento_id, nome_fase, ordem, status)
select o.id, b.id, 'PREPARAÇÃO E APLICAÇÃO', 1, 'AGUARDANDO'
from public.obras o
join public.orcamentos b on b.obra_id=o.id
where o.titulo like 'Obra 1%' and b.versao=1;

insert into public.obra_fases (obra_id, orcamento_id, nome_fase, ordem, status)
select o.id, b.id, 'ACABAMENTO FINAL', 2, 'AGUARDANDO'
from public.obras o
join public.orcamentos b on b.obra_id=o.id
where o.titulo like 'Obra 1%' and b.versao=1;

-- Obra 2 (APROVADO)
insert into public.obra_fases (obra_id, orcamento_id, nome_fase, ordem, status)
select o.id, b.id, 'PREPARAÇÃO E APLICAÇÃO', 1, 'INICIADO'
from public.obras o
join public.orcamentos b on b.obra_id=o.id
where o.titulo like 'Obra 2%' and b.versao=1;

insert into public.obra_fases (obra_id, orcamento_id, nome_fase, ordem, status)
select o.id, b.id, 'ACABAMENTO INTERMEDIÁRIO', 2, 'AGUARDANDO'
from public.obras o
join public.orcamentos b on b.obra_id=o.id
where o.titulo like 'Obra 2%' and b.versao=1;

-- -------------------------
-- Catálogo de Serviços
-- -------------------------
insert into public.servicos (nome, unidade, ativo) values
('Lixar parede', 'M2', true),
('Aplicar massa', 'M2', true),
('Pintura interna', 'M2', true),
('Pintura externa', 'M2', true),
('Proteção e limpeza', 'UN', true);

-- -------------------------
-- Serviços por fase (somente para Obra 2)
-- -------------------------
-- Fase 1 - Obra 2
insert into public.orcamento_fase_servicos (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit, observacao)
select
  f.orcamento_id,
  f.id,
  s.id,
  100,
  6.50,
  null
from public.obra_fases f
join public.obras o on o.id=f.obra_id
join public.servicos s on s.nome='Lixar parede'
where o.titulo like 'Obra 2%' and f.ordem=1;

insert into public.orcamento_fase_servicos (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit)
select
  f.orcamento_id,
  f.id,
  s.id,
  100,
  9.00
from public.obra_fases f
join public.obras o on o.id=f.obra_id
join public.servicos s on s.nome='Aplicar massa'
where o.titulo like 'Obra 2%' and f.ordem=1;

insert into public.orcamento_fase_servicos (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit)
select
  f.orcamento_id,
  f.id,
  s.id,
  100,
  12.00
from public.obra_fases f
join public.obras o on o.id=f.obra_id
join public.servicos s on s.nome='Pintura interna'
where o.titulo like 'Obra 2%' and f.ordem=1;

-- Recalcula fase + orçamento (obra 2)
select public.fn_recalcular_orcamento(b.id)
from public.orcamentos b
join public.obras o on o.id=b.obra_id
where o.titulo like 'Obra 2%' and b.versao=1;

-- -------------------------
-- Alocações de hoje (Obra 2)
-- -------------------------
insert into public.alocacoes (data, pessoa_id, obra_id, orcamento_id, obra_fase_id, periodo, tipo, observacao)
select
  current_date,
  p.id,
  o.id,
  b.id,
  f.id,
  'INTEGRAL',
  'INTERNO',
  'Seed: alocado hoje'
from public.pessoas p
join public.obras o on o.titulo like 'Obra 2%'
join public.orcamentos b on b.obra_id=o.id and b.status='APROVADO'
join public.obra_fases f on f.orcamento_id=b.id and f.ordem=1
where p.nome in ('João Pintor','Pedro Ajudante');

-- -------------------------
-- Apontamentos de hoje (Obra 2) - permitido pois orçamento APROVADO
-- -------------------------
insert into public.apontamentos (obra_id, orcamento_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
select
  o.id,
  b.id,
  f.id,
  p.id,
  current_date,
  'NORMAL',
  coalesce(p.diaria_base, 0),
  0,
  'Seed: apontamento hoje'
from public.pessoas p
join public.obras o on o.titulo like 'Obra 2%'
join public.orcamentos b on b.obra_id=o.id and b.status='APROVADO'
join public.obra_fases f on f.orcamento_id=b.id and f.ordem=1
where p.nome in ('João Pintor','Pedro Ajudante');

-- -------------------------
-- Financeiro (somente para ADMIN ver depois)
-- (feito aqui via SQL editor; no app, RLS ADMIN-only)
-- -------------------------
insert into public.recebimentos (orcamento_id, obra_fase_id, valor_previsto, acrescimo, vencimento, status)
select
  b.id,
  f.id,
  f.valor_fase,
  0,
  current_date + 7,
  'ABERTO'
from public.orcamentos b
join public.obras o on o.id=b.obra_id
join public.obra_fases f on f.orcamento_id=b.id and f.ordem=1
where o.titulo like 'Obra 2%' and b.status='APROVADO'
on conflict (obra_fase_id) do nothing;

-- ---------------------------------------------------------
-- IMPORTANTE:
-- usuarios_app NÃO dá pra seedar sem saber os UUIDs do Auth.
-- Depois que criar os usuários no painel Auth, rode:
-- insert into public.usuarios_app (auth_user_id, usuario, perfil, ativo)
-- values ('UUID_DO_AUTH_USER', 'Admin', 'ADMIN', true);
-- ---------------------------------------------------------

commit;
