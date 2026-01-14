# ======================================================
# SEPOL - V1.1 Cadastros Estáveis
# ======================================================
import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date

# ======================================================
# CONFIG
# ======================================================
st.set_page_config("DEV SEPOL - Controle de Obras", layout="wide")

# ======================================================
# DB
# ======================================================
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        st.secrets["DATABASE_URL"],
        cursor_factory=RealDictCursor,
        connect_timeout=10,
    )

def query_df(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return pd.DataFrame(cur.fetchall())
    except Exception:
        conn.rollback()
        raise

def exec_sql(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def safe_df(sql, params=None):
    try:
        return query_df(sql, params)
    except Exception as e:
        st.error("Falha ao consultar o banco. Verifique se você rodou o SQL completo (tabelas + views + functions).")
        st.exception(e)
        st.stop()

def brl(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())

# ======================================================
# Helpers
# ======================================================
def clear(keys):
    for k in keys:
        st.session_state[k] = ""

def set_edit(key, val):
    st.session_state[key] = val

def cancel_edit(key, clear_keys=None):
    st.session_state[key] = None
    if clear_keys:
        clear(clear_keys)
    st.rerun()

# ======================================================
# LOGIN
# ======================================================
if "usuario" not in st.session_state:
    st.session_state["usuario"] = None

if not st.session_state["usuario"]:
    st.title("🔐 Login")
    u = st.text_input("Usuário")
    s = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        df = safe_df("select * from public.usuarios_app where usuario=%s and ativo=true;", (u,))
        if df.empty or s != df.iloc[0]["senha_hash"]:
            st.error("Usuário ou senha inválidos.")
        else:
            st.session_state["usuario"] = u
            st.rerun()
    st.stop()

# ======================================================
# MENU
# ======================================================
if "menu" not in st.session_state:
    st.session_state["menu"] = "PROFISSIONAIS"

with st.sidebar:
    st.markdown(f"👤 {st.session_state['usuario']}")
    st.selectbox(
        "Menu",
        ["PROFISSIONAIS", "CLIENTES", "OBRAS"],
        key="menu",
    )
    if st.button("Sair"):
        st.session_state["usuario"] = None
        st.rerun()

menu = st.session_state["menu"]
st.title("🏗️ SEPOL - Cadastros")

# ======================================================
# PROFISSIONAIS
# ======================================================
if menu == "PROFISSIONAIS":
    st.subheader("👷 Profissionais")

    if "edit_prof" not in st.session_state:
        st.session_state["edit_prof"] = None

    edit_id = st.session_state["edit_prof"]
    row = None
    if edit_id:
        df = safe_df("select * from public.pessoas where id=%s;", (edit_id,))
        if not df.empty:
            row = df.iloc[0]

    nome = st.text_input("Nome", value=row["nome"] if row is not None else "", key="p_nome")
    tipo = st.selectbox("Tipo", ["PINTOR","AJUDANTE","TERCEIRO"],
                        index=["PINTOR","AJUDANTE","TERCEIRO"].index(row["tipo"]) if row is not None else 0,
                        key="p_tipo")
    tel  = st.text_input("Telefone", value=row["telefone"] or "" if row is not None else "", key="p_tel")

    c1, c2 = st.columns(2)
    with c1:
        if not edit_id:
            if st.button("Salvar", type="primary"):
                exec_sql("insert into public.pessoas (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                         (nome, tipo, tel or None))
                clear(["p_nome","p_tel"])
                st.success("Profissional cadastrado.")
                st.rerun()
        else:
            if st.button("Salvar alteração", type="primary"):
                exec_sql("update public.pessoas set nome=%s,tipo=%s,telefone=%s where id=%s;",
                         (nome,tipo,tel or None,int(edit_id)))
                cancel_edit("edit_prof", ["p_nome","p_tel"])

    with c2:
        if edit_id:
            if st.button("Cancelar edição"):
                cancel_edit("edit_prof", ["p_nome","p_tel"])

    st.divider()
    df = safe_df("select * from public.pessoas order by nome;")

    for _, r in df.iterrows():
        cA, cB, cC = st.columns([5,2,2])
        with cA:
            st.write(f"**{r['nome']}** — {r['tipo']}")
        with cB:
            st.write("ATIVO" if r["ativo"] else "INATIVO")
        with cC:
            if st.button("Editar", key=f"p_edit_{r['id']}"):
                set_edit("edit_prof", int(r["id"]))
                st.rerun()
            if r["ativo"]:
                if st.button("Inativar", key=f"p_inat_{r['id']}"):
                    exec_sql("update public.pessoas set ativo=false where id=%s;", (int(r["id"]),))
                    st.rerun()
            else:
                if st.button("Ativar", key=f"p_at_{r['id']}"):
                    exec_sql("update public.pessoas set ativo=true where id=%s;", (int(r["id"]),))
                    st.rerun()

# ======================================================
# CLIENTES + INDICAÇÕES
# ======================================================
if menu == "CLIENTES":
    st.subheader("👥 Clientes & Indicações")

    if "edit_cliente" not in st.session_state:
        st.session_state["edit_cliente"] = None

    # ---------- Indicações rápidas ----------
    with st.expander("➕ Nova indicação"):
        ind_nome = st.text_input("Nome da indicação", key="ind_nome")
        ind_tipo = st.selectbox("Tipo", ["ARQUITETO","ENGENHEIRO","LOJA","OUTRO"], key="ind_tipo")
        ind_tel  = st.text_input("Telefone", key="ind_tel")

        if st.button("Salvar indicação"):
            exec_sql(
                "insert into public.indicacoes (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                (ind_nome, ind_tipo, ind_tel or None),
            )
            clear(["ind_nome","ind_tel"])
            st.success("Indicação cadastrada.")
            st.rerun()

    df_ind = safe_df("select id,nome from public.indicacoes where ativo=true order by nome;")

    # ---------- Cliente ----------
    edit_id = st.session_state["edit_cliente"]
    row = None
    if edit_id:
        df = safe_df("select * from public.clientes where id=%s;", (edit_id,))
        if not df.empty:
            row = df.iloc[0]

    st.markdown("### 🧾 Cliente")

    nome = st.text_input("Nome", value=row["nome"] if row is not None else "", key="c_nome")
    tel  = st.text_input("Telefone", value=row["telefone"] or "" if row is not None else "", key="c_tel")
    end  = st.text_input("Endereço", value=row["endereco"] or "" if row is not None else "", key="c_end")

    origem = st.selectbox(
        "Origem",
        ["PROPRIO","INDICADO"],
        index=["PROPRIO","INDICADO"].index(row["origem"]) if row is not None else 0,
        key="c_origem"
    )

    indicacao_id = None
    if origem == "INDICADO":
        ids = df_ind["id"].tolist()
        if not ids:
            st.warning("Cadastre uma indicação primeiro.")
        else:
            indicacao_id = st.selectbox(
                "Quem indicou",
                ids,
                format_func=lambda x: df_ind.loc[df_ind["id"]==x,"nome"].iloc[0],
                key="c_ind"
            )

    c1, c2 = st.columns(2)
    with c1:
        if not edit_id:
            if st.button("Salvar cliente", type="primary"):
                exec_sql(
                    """
                    insert into public.clientes
                    (nome,telefone,endereco,origem,indicacao_id,ativo)
                    values (%s,%s,%s,%s,%s,true)
                    """,
                    (nome, tel or None, end or None, origem, indicacao_id),
                )
                clear(["c_nome","c_tel","c_end"])
                st.success("Cliente cadastrado.")
                st.rerun()
        else:
            if st.button("Salvar alteração", type="primary"):
                exec_sql(
                    """
                    update public.clientes
                    set nome=%s, telefone=%s, endereco=%s, origem=%s, indicacao_id=%s
                    where id=%s;
                    """,
                    (nome, tel or None, end or None, origem, indicacao_id, int(edit_id)),
                )
                cancel_edit("edit_cliente", ["c_nome","c_tel","c_end"])

    with c2:
        if edit_id:
            if st.button("Cancelar edição"):
                cancel_edit("edit_cliente", ["c_nome","c_tel","c_end"])

    st.divider()
    st.markdown("### 📋 Lista de clientes")

    df = safe_df("""
        select c.id, c.nome, c.telefone, c.origem,
               i.nome as indicacao, c.ativo
        from public.clientes c
        left join public.indicacoes i on i.id=c.indicacao_id
        order by c.nome;
    """)

    for _, r in df.iterrows():
        colA, colB, colC = st.columns([6,2,2])
        with colA:
            st.write(f"**{r['nome']}** — {r['origem']} — {r['indicacao'] or ''}")
        with colB:
            st.write("ATIVO" if r["ativo"] else "INATIVO")
        with colC:
            if st.button("Editar", key=f"c_edit_{r['id']}"):
                set_edit("edit_cliente", int(r["id"]))
                st.rerun()
            if r["ativo"]:
                if st.button("Inativar", key=f"c_inat_{r['id']}"):
                    exec_sql("update public.clientes set ativo=false where id=%s;", (int(r["id"]),))
                    st.rerun()
            else:
                if st.button("Ativar", key=f"c_at_{r['id']}"):
                    exec_sql("update public.clientes set ativo=true where id=%s;", (int(r["id"]),))
                    st.rerun()

# ======================================================
# OBRAS
# ======================================================
if menu == "OBRAS":
    st.subheader("🏗️ Obras")

    if "edit_obra" not in st.session_state:
        st.session_state["edit_obra"] = None

    df_cli = safe_df("select id,nome from public.clientes where ativo=true order by nome;")

    # ---------- Cliente rápido ----------
    with st.expander("➕ Cliente rápido"):
        rc_nome = st.text_input("Nome cliente", key="rc_nome")
        rc_tel  = st.text_input("Telefone", key="rc_tel")
        if st.button("Criar cliente"):
            exec_sql(
                "insert into public.clientes (nome,telefone,origem,ativo) values (%s,%s,'PROPRIO',true);",
                (rc_nome, rc_tel or None),
            )
            clear(["rc_nome","rc_tel"])
            st.success("Cliente criado.")
            st.rerun()

    edit_id = st.session_state["edit_obra"]
    row = None
    if edit_id:
        df = safe_df("select * from public.obras where id=%s;", (edit_id,))
        if not df.empty:
            row = df.iloc[0]

    st.markdown("### 🧱 Obra")

    cli_ids = df_cli["id"].tolist()
    if not cli_ids:
        st.warning("Cadastre pelo menos um cliente.")
        st.stop()

    cliente_id = st.selectbox(
        "Cliente",
        cli_ids,
        index=cli_ids.index(row["cliente_id"]) if row is not None else 0,
        format_func=lambda x: df_cli.loc[df_cli["id"]==x,"nome"].iloc[0],
        key="o_cli"
    )

    titulo = st.text_input("Título da obra", value=row["titulo"] if row is not None else "", key="o_tit")
    endereco = st.text_input("Endereço", value=row["endereco_obra"] or "" if row is not None else "", key="o_end")
    status = st.selectbox(
        "Status",
        ["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"],
        index=["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"].index(row["status"]) if row is not None else 0,
        key="o_status"
    )

    c1, c2 = st.columns(2)
    with c1:
        if not edit_id:
            if st.button("Salvar obra", type="primary"):
                exec_sql(
                    """
                    insert into public.obras
                    (cliente_id,titulo,endereco_obra,status,ativo)
                    values (%s,%s,%s,%s,true)
                    """,
                    (cliente_id,titulo,endereco or None,status),
                )
                clear(["o_tit","o_end"])
                st.success("Obra cadastrada.")
                st.rerun()
        else:
            if st.button("Salvar alteração", type="primary"):
                exec_sql(
                    """
                    update public.obras
                    set cliente_id=%s, titulo=%s, endereco_obra=%s, status=%s
                    where id=%s;
                    """,
                    (cliente_id,titulo,endereco or None,status,int(edit_id)),
                )
                cancel_edit("edit_obra", ["o_tit","o_end"])

    with c2:
        if edit_id:
            if st.button("Cancelar edição"):
                cancel_edit("edit_obra", ["o_tit","o_end"])

    st.divider()
    st.markdown("### 📋 Lista de obras")

    df = safe_df("""
        select o.id, o.titulo, o.status, o.ativo, c.nome cliente
        from public.obras o
        join public.clientes c on c.id=o.cliente_id
        order by o.id desc;
    """)

    for _, r in df.iterrows():
        colA, colB, colC = st.columns([6,2,2])
        with colA:
            st.write(f"**{r['titulo']}** — {r['cliente']}")
        with colB:
            st.write(r["status"])
        with colC:
            if st.button("Editar", key=f"o_edit_{r['id']}"):
                set_edit("edit_obra", int(r["id"]))
                st.rerun()
            if r["ativo"]:
                if st.button("Inativar", key=f"o_inat_{r['id']}"):
                    exec_sql("update public.obras set ativo=false where id=%s;", (int(r["id"]),))
                    st.rerun()
            else:
                if st.button("Ativar", key=f"o_at_{r['id']}"):
                    exec_sql("update public.obras set ativo=true where id=%s;", (int(r["id"]),))
                    st.rerun()
