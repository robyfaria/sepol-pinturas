-- name: q_clientes_ativos
select id, nome, telefone, endereco
from public.clientes
where ativo=true
order by nome;

-- name: q_profissionais_ativos
select id, nome, tipo, telefone
from public.pessoas
where ativo=true
order by nome;

-- name: q_obras_ativas
select o.id, o.titulo, o.status, c.nome as cliente_nome
from public.obras o
join public.clientes c on c.id=o.cliente_id
where o.ativo=true
order by o.id desc;

-- name: q_orcamentos_da_obra
select id, titulo, status, valor_total, desconto_valor, valor_total_final, criado_em, aprovado_em
from public.orcamentos
where obra_id=%s
order by id desc;

-- name: q_orcamento_aprovado_da_obra
select id
from public.orcamentos
where obra_id=%s and status='APROVADO'
limit 1;

-- name: q_fases_do_orcamento
select id, ordem, nome_fase, valor_fase, status
from public.obra_fases
where orcamento_id=%s
order by ordem;

-- name: q_servicos_catalogo
select id, nome, unidade, ativo
from public.servicos
where ativo=true
order by nome;

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

-- name: q_recebimentos_do_orcamento
select
  r.id, r.status, r.valor_base, r.acrescimo, r.valor_total, r.vencimento_em, r.pago_em,
  f.ordem, f.nome_fase
from public.recebimentos r
join public.obra_fases f on f.id=r.obra_fase_id
where r.orcamento_id=%s
order by f.ordem;

-- name: q_pagamentos_pendentes
select *
from public.pagamentos_pendentes
limit 500;

-- name: q_pagamentos_pagos_30d
select *
from public.pagamentos_pagos_30d
limit 500;

-- name: q_home_kpis_safe
-- (se a view existir) use na HOME
select * from public.home_hoje_kpis;

-- name: q_home_kpis_fallback
-- fallback se view não existir
select
  current_date as hoje,
  0::int as fases_em_andamento,
  0::int as recebimentos_vencidos_qtd,
  0::numeric as recebimentos_pendentes_total,
  0::numeric as pagar_na_sexta_total,
  0::numeric as extras_pendentes_total;
