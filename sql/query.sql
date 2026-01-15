-- sql/query.sql
-- Padrao: cada query tem um nome. O loader do app encontra por "-- name: <nome>".

-- =========================
-- LOGIN / CONFIG
-- =========================

-- name: q_login_user
select id, usuario, senha_hash, perfil, ativo
from public.usuarios_app
where usuario = %(usuario)s
limit 1;

-- name: q_auditoria_ultimos
select id, usuario, entidade, entidade_id, acao, criado_em
from public.auditoria
order by criado_em desc
limit %(limite)s;

-- name: q_users
select id, usuario, perfil, ativo, criado_em
from public.usuarios_app
order by usuario;

-- name: i_user
insert into public.usuarios_app (usuario, senha_hash, perfil, ativo)
values (%(usuario)s, crypt(%(senha)s, gen_salt('bf')), %(perfil)s, true);

-- name: u_user_reset_senha
update public.usuarios_app
set senha_hash = crypt(%(senha)s, gen_salt('bf'))
where id = %(id)s;

-- name: u_user_set_ativo
update public.usuarios_app
set ativo = %(ativo)s
where id = %(id)s;

-- =========================
-- CADASTROS
-- =========================

-- name: q_clientes
select id, nome, telefone, endereco, ativo, criado_em
from public.clientes
order by nome;

-- name: i_cliente
insert into public.clientes (nome, telefone, endereco, origem, indicacao_id, ativo)
values (%(nome)s, %(telefone)s, %(endereco)s, 'PROPRIO', null, true);

-- name: u_cliente
update public.clientes
set nome=%(nome)s, telefone=%(telefone)s, endereco=%(endereco)s
where id=%(id)s;

-- name: u_cliente_set_ativo
update public.clientes set ativo=%(ativo)s where id=%(id)s;

-- name: q_pessoas
select id, nome, tipo, telefone, diaria_base, observacao, ativo, criado_em
from public.pessoas
order by nome;

-- name: i_pessoa
insert into public.pessoas (nome, tipo, telefone, diaria_base, observacao, ativo)
values (%(nome)s, %(tipo)s, %(telefone)s, %(diaria_base)s, %(observacao)s, true);

-- name: u_pessoa
update public.pessoas
set nome=%(nome)s, tipo=%(tipo)s, telefone=%(telefone)s,
    diaria_base=%(diaria_base)s, observacao=%(observacao)s
where id=%(id)s;

-- name: u_pessoa_set_ativo
update public.pessoas set ativo=%(ativo)s where id=%(id)s;

-- =========================
-- OBRAS / ORCAMENTOS (basico)
-- =========================

-- name: q_obras
select o.id, o.cliente_id, o.titulo, o.status, o.ativo, o.criado_em,
       c.nome as cliente_nome
from public.obras o
join public.clientes c on c.id=o.cliente_id
where o.ativo=true
order by o.id desc
limit 300;

-- name: i_obra
insert into public.obras (cliente_id, titulo, endereco_obra, status, ativo)
values (%(cliente_id)s, %(titulo)s, %(endereco_obra)s, %(status)s, true);

-- name: u_obra
update public.obras
set cliente_id=%(cliente_id)s, titulo=%(titulo)s, endereco_obra=%(endereco_obra)s, status=%(status)s
where id=%(id)s;

-- =========================
-- HOME / FINANCEIRO
-- =========================

-- name: q_home_kpis
select * from public.home_hoje_kpis;

-- name: q_alocacoes_hoje
select * from public.alocacoes_hoje;

-- name: q_pagamentos_para_sexta
select * from public.pagamentos_para_sexta;

-- name: q_pagamentos_pendentes
select * from public.pagamentos_pendentes order by pessoa_nome, tipo, referencia_inicio;

-- name: q_pagamentos_pagos_30d
select * from public.pagamentos_pagos_30d order by pago_em desc, id desc;

-- name: call_gerar_pagamentos_semana
select public.fn_gerar_pagamentos_semana(%(segunda)s);

-- name: call_marcar_pagamento_pago
select public.fn_marcar_pagamento_pago(%(pagamento_id)s, %(usuario)s, %(data_pg)s);

-- name: call_estornar_pagamento
select public.fn_estornar_pagamento(%(pagamento_id)s, %(usuario)s, %(motivo)s);

