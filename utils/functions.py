import os
import re
from io import BytesIO
from datetime import date, timedelta

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

import streamlit as st


# =========================================================
# DB
# =========================================================
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        st.secrets["DATABASE_URL"],
        cursor_factory=RealDictCursor,
        connect_timeout=10,
    )

def _ensure_conn_alive(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("select 1;")
        return conn
    except Exception:
        return get_conn()

def query_df(sql, params=None):
    conn = _ensure_conn_alive(get_conn())
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
        return pd.DataFrame(rows)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

def query_one(sql, params=None):
    df = query_df(sql, params)
    if df.empty:
        return None
    return dict(df.iloc[0])

def exec_sql(sql, params=None):
    conn = _ensure_conn_alive(get_conn())
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    except psycopg2.InterfaceError:
        # conexão morreu: recria e tenta 1x
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# =========================================================
# SQL Registry (queries.sql)
# =========================================================
@st.cache_resource
def load_queries(path="sql/queries.sql"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"--\s*name:\s*(\S+)\s*\n"
    parts = re.split(pattern, content)

    # parts: [before, name1, body1, name2, body2...]
    queries = {}
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip()
        queries[name] = body

    return queries

def q(name: str) -> str:
    queries = load_queries()
    if name not in queries:
        raise KeyError(f"Query não encontrada no queries.sql: {name}")
    return queries[name]


# =========================================================
# Helpers 60+
# =========================================================
def brl(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())

def badge_status_orc(stt: str) -> str:
    mp = {
        "RASCUNHO": "🟡 RASCUNHO",
        "EMITIDO": "🔵 EMITIDO",
        "APROVADO": "🟢 APROVADO",
        "REPROVADO": "🔴 REPROVADO",
        "CANCELADO": "⚫ CANCELADO",
    }
    return mp.get(stt, stt)

def safe_df(sql, params=None, fallback_name=None):
    try:
        return query_df(sql, params)
    except Exception as e:
        # fallback opcional
        if fallback_name:
            try:
                return query_df(q(fallback_name))
            except Exception:
                pass
        st.error("Falha ao consultar o banco.")
        st.code(getattr(e, "pgerror", None) or str(e))
        st.stop()


# =========================================================
# Seed (30 segundos)
# =========================================================
def seed_quick_30s():
    """
    Cria dados mínimos para testar o fluxo completo:
    Cliente → Obra → Orçamento → Fases → Serviços → Recebimentos → Apontamentos → Pagamentos
    """
    # 1) Cliente
    exec_sql("""
        insert into public.clientes (nome, telefone, endereco, origem, ativo)
        values ('Cliente Seed', null, 'Rua Teste, 123', 'PROPRIO', true)
        on conflict do nothing;
    """)
    cli = query_one("select id from public.clientes where nome='Cliente Seed' limit 1;")
    cliente_id = int(cli["id"])

    # 2) Profissionais
    exec_sql("""
        insert into public.pessoas (nome, tipo, telefone, ativo)
        values
          ('Pintor Seed', 'PINTOR', null, true),
          ('Ajudante Seed', 'AJUDANTE', null, true)
        on conflict do nothing;
    """)
    pintor = query_one("select id from public.pessoas where nome='Pintor Seed' limit 1;")
    ajud = query_one("select id from public.pessoas where nome='Ajudante Seed' limit 1;")
    pintor_id = int(pintor["id"])
    ajud_id = int(ajud["id"])

    # 3) Obra
    exec_sql("""
        insert into public.obras (cliente_id, titulo, endereco_obra, status, ativo)
        values (%s, 'Obra Seed', 'Rua da Obra, 45', 'INICIADO', true)
        on conflict do nothing;
    """, (cliente_id,))
    obra = query_one("select id from public.obras where titulo='Obra Seed' order by id desc limit 1;")
    obra_id = int(obra["id"])

    # 4) Orçamento (cria e aprova para liberar apontamento/financeiro)
    exec_sql("""
        insert into public.orcamentos (obra_id, titulo, status)
        values (%s, 'Orçamento Seed', 'RASCUNHO')
        returning id;
    """, (obra_id,))
    orc = query_one("select id from public.orcamentos where obra_id=%s order by id desc limit 1;", (obra_id,))
    orc_id = int(orc["id"])

    # 5) Fases
    exec_sql("""
        insert into public.obra_fases (orcamento_id, obra_id, nome_fase, ordem, status, valor_fase)
        values
          (%s, %s, 'PREPARAÇÃO E APLICAÇÃO', 1, 'AGUARDANDO', 0),
          (%s, %s, 'ACABAMENTO FINAL',       2, 'AGUARDANDO', 0);
    """, (orc_id, obra_id, orc_id, obra_id))

    fases = query_df("select id, ordem from public.obra_fases where orcamento_id=%s order by ordem;", (orc_id,))
    fase1 = int(fases.iloc[0]["id"])
    fase2 = int(fases.iloc[1]["id"])

    # 6) Serviços catálogo
    exec_sql("""
        insert into public.servicos (nome, unidade, ativo)
        values
          ('Pintura interna', 'm2', true),
          ('Massa corrida',  'm2', true)
        on conflict do nothing;
    """)
    s1 = query_one("select id from public.servicos where nome='Pintura interna' limit 1;")
    s2 = query_one("select id from public.servicos where nome='Massa corrida' limit 1;")
    s1_id = int(s1["id"])
    s2_id = int(s2["id"])

    # 7) Vínculo serviços por fase
    exec_sql("""
        insert into public.orcamento_fase_servicos
          (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit, valor_total)
        values
          (%s, %s, %s, 100, 25, 2500),
          (%s, %s, %s, 80,  18, 1440),
          (%s, %s, %s, 120, 22, 2640);
    """, (orc_id, fase1, s1_id, orc_id, fase1, s2_id, orc_id, fase2, s1_id))

    # 8) Recalcular totais
    exec_sql("select public.fn_recalcular_orcamento(%s);", (orc_id,))

    # 9) Emitir e aprovar (para liberar apontamentos)
    exec_sql("update public.orcamentos set status='EMITIDO' where id=%s;", (orc_id,))
    exec_sql("update public.orcamentos set status='APROVADO', aprovado_em=current_date where id=%s;", (orc_id,))

    # 10) Recebimentos (um por fase)
    exec_sql("""
        insert into public.recebimentos
          (obra_fase_id, orcamento_id, status, valor_base, acrescimo, vencimento_em, observacao)
        values
          (%s, %s, 'ABERTO', 2500, 0, current_date + 7, 'Recebimento Fase 1'),
          (%s, %s, 'ABERTO', 2640, 0, current_date + 14, 'Recebimento Fase 2')
        on conflict do nothing;
    """, (fase1, orc_id, fase2, orc_id))

    # 11) Apontamentos (semana corrente)
    hoje = date.today()
    seg = monday_of_week(hoje)
    # 2 dias para pintor + 1 dia ajudante
    exec_sql("""
        insert into public.apontamentos
          (obra_id, orcamento_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
        values
          (%s,%s,%s,%s,%s,'NORMAL',200,0,'Seed'),
          (%s,%s,%s,%s,%s,'NORMAL',200,0,'Seed'),
          (%s,%s,%s,%s,%s,'NORMAL',120,0,'Seed');
    """, (
        obra_id, orc_id, fase1, pintor_id, seg,
        obra_id, orc_id, fase1, pintor_id, seg + timedelta(days=1),
        obra_id, orc_id, fase1, ajud_id,   seg
    ))

    # 12) Gerar pagamentos semana
    exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (seg,))

    return {"obra_id": obra_id, "orcamento_id": orc_id, "segunda": str(seg)}


# =========================================================
# Renderização (telas) — ficam aqui, app.py fica limpo
# =========================================================
def tela_home():
    st.subheader("HOME")

    # tenta view, se não existir usa fallback
    try:
        kpi = query_df(q("q_home_kpis_safe"))
    except Exception:
        kpi = query_df(q("q_home_kpis_fallback"))

    r = dict(kpi.iloc[0])

    c1, c2, c3 = st.columns(3)
    c1.metric("Hoje", str(r.get("hoje")))
    c2.metric("A receber (total)", brl(r.get("recebimentos_pendentes_total", 0)))
    c3.metric("A pagar (total)", brl(r.get("pagar_na_sexta_total", 0)))

    st.divider()
    st.markdown("### Seed rápido (DEV)")
    if st.button("⚡ Criar Seed (30s)", type="primary", use_container_width=True):
        out = seed_quick_30s()
        st.success(f"Seed pronto ✅ Obra #{out['obra_id']} • Orçamento #{out['orcamento_id']} • Semana {out['segunda']}")
        st.rerun()
