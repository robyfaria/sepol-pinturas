-- =========================
-- HOME
-- =========================

-- name: q_home_kpis_safe
select * from public.home_hoje_kpis;

-- name: q_home_kpis_fallback
select
  current_date as hoje,
  0::int as fases_em_andamento,
  0::int as recebimentos_vencidos_qtd,
  0::numeric as recebimentos_pendentes_total,
  0::numeric as pagar_na_sexta_total,
  0::numeric as extras_pendentes_total;


-- =========================
-- CADASTROS - CLIENTES
-- =========================

-- name: q_clientes_ativos
select id, nome, telefone, endereco, ativo
from public.clientes
where ativo=true
order by nome;

-- name: q_clientes_all
select id, nome, telefone, endereco, ativo
from public.clientes
order by nome;

-- name: q_cliente_by_id
select id, nome, telefone, endereco, ativo
from public.clientes
where id=%s;

-- name: ins_cliente
insert into public.clientes (nome, telefone, endereco, origem, ativo)
values (%s,%s,%s,'PROPRIO',true);

-- name: upd_cliente
update public.clientes
set nome=%s, telefone=%s, endereco=%s
where id=%s;

-- name: set_cliente_ativo
update public.clientes
set ativo=%s
where id=%s;


-- =========================
-- CADASTROS - PROFISSIONAIS (pessoas)
-- =========================

-- name: q_profissionais_all
select id, nome, tipo, telefone, ativo
from public.pessoas
order by nome;

-- name: q_profissionais_ativos
select id, nome, tipo, telefone
from public.pessoas
where ativo=true
order by nome;

-- name: q_prof_by_id
select id, nome, tipo, telefone, ativo
from public.pessoas
where id=%s;

-- name: ins_prof
insert into public.pessoas (nome, tipo, telefone, ativo)
values (%s,%s,%s,true);

-- name: upd_prof
update public.pessoas
set nome=%s, tipo=%s, telefone=%s
where id=%s;

-- name: set_prof_ativo
update public.pessoas
set ativo=%s
where id=%s;


-- =========================
-- OBRAS
-- =========================

-- name: q_obras_ativas
select o.id, o.titulo, o.status, o.ativo, c.nome as cliente_nome
from public.obras o
join public.clientes c on c.id=o.cliente_id
where o.ativo=true
order by o.id desc;

-- name: q_obra_by_id
select id, cliente_id, titulo, endereco_obra, status, ativo
from public.obras
where id=%s;

-- name: ins_obra
insert into public.obras (cliente_id, titulo, endereco_obra, status, ativo)
values (%s,%s,%s,%s,true);

-- name: upd_obra
update public.obras
set cliente_id=%s, titulo=%s, endereco_obra=%s, status=%s
where id=%s;

-- name: set_obra_ativo
update public.obras
set ativo=%s
where id=%s;


-- =========================
-- ORÇAMENTOS
-- =========================

-- name: q_orcamentos_da_obra
select id, titulo, status, valor_total, desconto_valor, valor_total_final, criado_em, aprovado_em
from public.orcamentos
where obra_id=%s
order by id desc;

-- name: ins_orcamento
insert into public.orcamentos (obra_id, titulo, status)
values (%s,%s,'RASCUNHO');

-- name: set_orc_status
update public.orcamentos
set status=%s
where id=%s;

-- name: set_orc_desconto
update public.orcamentos
set desconto_valor=%s
where id=%s;

-- name: call_recalc_orc
select public.fn_recalcular_orcamento(%s);

-- name: set_orc_emitido
update public.orcamentos
set status='EMITIDO'
where id=%s;

-- name: set_orc_rascunho
update public.orcamentos
set status='RASCUNHO'
where id=%s;

-- name: set_orc_aprovado
update public.orcamentos
set status='APROVADO', aprovado_em=current_date
where id=%s;


-- =========================
-- FASES
-- =========================

-- name: q_fases_do_orcamento
select id, ordem, nome_fase, valor_fase, status
from public.obra_fases
where orcamento_id=%s
order by ordem;

-- name: ins_fase
insert into public.obra_fases (orcamento_id, obra_id, nome_fase, ordem, status, valor_fase)
values (%s,%s,%s,%s,%s,0);


-- =========================
-- SERVIÇOS (catálogo + vínculo)
-- =========================

-- name: q_servicos_catalogo
select id, nome, unidade, ativo
from public.servicos
where ativo=true
order by nome;

-- name: ins_servico_catalogo
insert into public.servicos (nome, unidade, ativo)
values (%s,%s,true);

-- name: q_servicos_da_fase
select
  ofs.id,
  s.nome,
  s.unidade,
  ofs.quantidade,
  ofs.valor_unit,
  ofs.valor_total
from public.orcamento_fase_servicos ofs
join public.servicos s on s.id=ofs.servico_id
where ofs.orcamento_id=%s and ofs.obra_fase_id=%s
order by s.nome;

-- name: upsert_serv_fase
insert into public.orcamento_fase_servicos
  (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit, valor_total)
values
  (%s,%s,%s,%s,%s, round(%s * %s, 2))
on conflict (orcamento_id, obra_fase_id, servico_id)
do update set
  quantidade=excluded.quantidade,
  valor_unit=excluded.valor_unit,
  valor_total=excluded.valor_total;


-- =========================
-- RECEBIMENTOS
-- =========================

-- name: q_recebimentos_do_orcamento
select
  r.id, r.status, r.valor_base, r.acrescimo, r.valor_total, r.vencimento_em, r.pago_em,
  f.ordem, f.nome_fase
from public.recebimentos r
join public.obra_fases f on f.id=r.obra_fase_id
where r.orcamento_id=%s
order by f.ordem;

-- name: upsert_recebimento
insert into public.recebimentos
  (obra_fase_id, orcamento_id, status, valor_base, acrescimo, vencimento_em, observacao)
values
  (%s,%s,'ABERTO',%s,%s,%s,%s)
on conflict (orcamento_id, obra_fase_id)
do update set
  status='ABERTO',
  valor_base=excluded.valor_base,
  acrescimo=excluded.acrescimo,
  vencimento_em=excluded.vencimento_em,
  observacao=excluded.observacao;

-- name: q_recebimentos_ultimos
select
  r.id, r.status, r.valor_total, r.vencimento_em, r.pago_em,
  o.id as orcamento_id,
  ob.titulo as obra,
  c.nome as cliente,
  f.ordem, f.nome_fase
from public.recebimentos r
join public.obra_fases f on f.id=r.obra_fase_id
join public.orcamentos o on o.id=r.orcamento_id
join public.obras ob on ob.id=o.obra_id
join public.clientes c on c.id=ob.cliente_id
order by r.id desc
limit 200;


-- =========================
-- FINANCEIRO - PAGAMENTOS
-- =========================

-- name: call_gerar_pag_semana
select public.fn_gerar_pagamentos_semana(%s);

-- name: q_pagamentos_pendentes
select * from public.pagamentos_pendentes limit 500;

-- name: q_pagamentos_pagos_30d
select * from public.pagamentos_pagos_30d limit 500;

-- name: call_marcar_pago
select public.fn_marcar_pagamento_pago(%s,%s,%s);

-- name: call_estornar
select public.fn_estornar_pagamento(%s,%s,%s);


-- =========================
-- SEED QUERIES (DEV)
-- =========================

-- name: ins_cliente_seed
insert into public.clientes (nome, telefone, endereco, origem, ativo)
values ('Cliente Seed', null, 'Rua Teste, 123', 'PROPRIO', true)
on conflict do nothing;

-- name: get_cliente_seed
select id from public.clientes where nome='Cliente Seed' order by id desc limit 1;

-- name: ins_prof_seed
insert into public.pessoas (nome, tipo, telefone, ativo)
values
  ('Pintor Seed', 'PINTOR', null, true),
  ('Ajudante Seed', 'AJUDANTE', null, true)
on conflict do nothing;

-- name: get_pintor_seed
select id from public.pessoas where nome='Pintor Seed' order by id desc limit 1;

-- name: get_ajudante_seed
select id from public.pessoas where nome='Ajudante Seed' order by id desc limit 1;

-- name: ins_obra_seed
insert into public.obras (cliente_id, titulo, endereco_obra, status, ativo)
values (%s, 'Obra Seed', 'Rua da Obra, 45', 'INICIADO', true)
on conflict do nothing;

-- name: get_obra_seed
select id from public.obras where titulo='Obra Seed' order by id desc limit 1;

-- name: ins_orc_seed
insert into public.orcamentos (obra_id, titulo, status)
values (%s, 'Orçamento Seed', 'RASCUNHO');

-- name: get_orc_seed
select id from public.orcamentos where obra_id=%s order by id desc limit 1;

-- name: ins_fases_seed
insert into public.obra_fases (orcamento_id, obra_id, nome_fase, ordem, status, valor_fase)
values
  (%s, %s, 'PREPARAÇÃO E APLICAÇÃO', 1, 'AGUARDANDO', 0),
  (%s, %s, 'ACABAMENTO FINAL',       2, 'AGUARDANDO', 0);

-- name: ins_servicos_seed
insert into public.servicos (nome, unidade, ativo)
values
  ('Pintura interna', 'm2', true),
  ('Massa corrida',  'm2', true)
on conflict do nothing;

-- name: get_serv_pintura
select id from public.servicos where nome='Pintura interna' order by id desc limit 1;

-- name: get_serv_massa
select id from public.servicos where nome='Massa corrida' order by id desc limit 1;

-- name: ins_vinculos_seed
insert into public.orcamento_fase_servicos
  (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit, valor_total)
values
  (%s, %s, %s, 100, 25, 2500),
  (%s, %s, %s, 80,  18, 1440),
  (%s, %s, %s, 120, 22, 2640);

-- name: ins_receb_seed
insert into public.recebimentos
  (obra_fase_id, orcamento_id, status, valor_base, acrescimo, vencimento_em, observacao)
values
  (%s, %s, 'ABERTO', 2500, 0, current_date + 7,  'Recebimento Fase 1'),
  (%s, %s, 'ABERTO', 2640, 0, current_date + 14, 'Recebimento Fase 2')
on conflict do nothing;

-- name: ins_apont_seed
insert into public.apontamentos
  (obra_id, orcamento_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
values
  (%s,%s,%s,%s,%s,'NORMAL',200,0,'Seed'),
  (%s,%s,%s,%s,%s,'NORMAL',200,0,'Seed'),
  (%s,%s,%s,%s,%s,'NORMAL',120,0,'Seed');
