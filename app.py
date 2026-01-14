import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

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
            rows = cur.fetchall()
        return pd.DataFrame(rows)
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
# LOGIN SIMPLES
# ======================================================
if "usuario" not in st.session_state:
    st.session_state["usuario"] = None

if not st.session_state["usuario"]:
    st.title("🔐 DEV SEPOL - Login")
    user = st.text_input("Usuário")
    pwd = st.text_input("Senha", type="password")
    if st.button("Entrar", type="primary"):
        df = safe_df(
            "select * from public.usuarios_app where usuario=%s and ativo=true;",
            (user,),
        )
        if df.empty:
            st.error("Usuário inválido.")
        else:
            # MVP: sem hash (você pode melhorar depois)
            if pwd != df.iloc[0]["senha_hash"]:
                st.error("Senha inválida.")
            else:
                st.session_state["usuario"] = user
                st.rerun()
    st.stop()

usuario = st.session_state["usuario"]

# ======================================================
# NAVEGAÇÃO
# ======================================================
def nav(dest):
    st.session_state["menu"] = dest

if "menu" not in st.session_state:
    st.session_state["menu"] = "HOJE"

# ======================================================
# SIDEBAR
# ======================================================
with st.sidebar:
    st.markdown(f"👤 **Usuário:** {usuario}")
    st.divider()
    st.selectbox(
        "Menu",
        ["HOJE", "OBRAS", "PROFISSIONAIS", "APONTAMENTOS", "FINANCEIRO", "ADMIN"],
        key="menu",
    )
    st.divider()
    if st.button("Sair"):
        st.session_state["usuario"] = None
        st.rerun()

menu = st.session_state["menu"]

st.title("🏗️ SEPOL - Controle de Obras")

# ======================================================
# HOJE (PROVA DE VALOR)
# ======================================================
if menu == "HOJE":
    st.subheader("📅 Planejamento de Hoje")

    df = safe_df("select * from public.alocacoes_hoje;")
    if df.empty:
        st.info("Nenhuma alocação para hoje.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("💰 Pagamentos Pendentes")
    dfp = safe_df("select * from public.pagamentos_pendentes;")
    st.dataframe(dfp, use_container_width=True, hide_index=True)

# ======================================================
# PROFISSIONAIS
# ======================================================
if menu == "PROFISSIONAIS":
    st.subheader("👷 Profissionais")

    df = safe_df("select * from public.pessoas order by nome;")

    with st.expander("➕ Novo profissional"):
        nome = st.text_input("Nome")
        tipo = st.selectbox("Tipo", ["PINTOR", "AJUDANTE", "TERCEIRO"])
        tel = st.text_input("Telefone")
        diaria = st.number_input("Diária base", min_value=0.0, step=50.0)
        if st.button("Salvar", type="primary"):
            exec_sql(
                """
                insert into public.pessoas
                (nome,tipo,telefone,diaria_base,ativo)
                values (%s,%s,%s,%s,true)
                """,
                (nome, tipo, tel or None, diaria),
            )
            st.success("Profissional cadastrado.")
            st.rerun()

    st.divider()
    st.dataframe(df, use_container_width=True, hide_index=True)

# ======================================================
# OBRAS / ORÇAMENTOS / FASES
# ======================================================
if menu == "OBRAS":
    st.subheader("🏗️ Obras")

    df_obras = safe_df("""
        select o.*, c.nome as cliente
        from public.obras o
        join public.clientes c on c.id=o.cliente_id
        order by o.id desc;
    """)

    obra_id = st.selectbox(
        "Selecione uma obra",
        df_obras["id"].tolist() if not df_obras.empty else [],
        format_func=lambda x: df_obras.loc[df_obras["id"] == x, "titulo"].iloc[0]
        if not df_obras.empty else "",
    )

    if obra_id:
        st.markdown("### 📑 Orçamentos")

        df_orc = safe_df(
            "select * from public.orcamentos where obra_id=%s order by versao;",
            (obra_id,),
        )
        st.dataframe(df_orc, use_container_width=True, hide_index=True)

        with st.expander("➕ Novo orçamento"):
            versao = st.number_input("Versão", min_value=1, step=1)
            titulo = st.text_input("Título")
            if st.button("Criar orçamento", type="primary"):
                exec_sql(
                    """
                    insert into public.orcamentos
                    (obra_id,versao,titulo,status)
                    values (%s,%s,%s,'RASCUNHO')
                    """,
                    (obra_id, versao, titulo),
                )
                st.success("Orçamento criado.")
                st.rerun()

# ======================================================
# APONTAMENTOS
# ======================================================
if menu == "APONTAMENTOS":
    st.subheader("📝 Apontamentos")

    pessoas = safe_df("select id,nome from public.pessoas where ativo=true order by nome;")
    obras = safe_df("select id,titulo from public.obras where ativo=true order by titulo;")

    if pessoas.empty or obras.empty:
        st.warning("Cadastre profissionais e obras primeiro.")
        st.stop()

    pessoa_id = st.selectbox("Profissional", pessoas["id"], format_func=lambda x: pessoas.loc[pessoas["id"]==x,"nome"].iloc[0])
    obra_id = st.selectbox("Obra", obras["id"], format_func=lambda x: obras.loc[obras["id"]==x,"titulo"].iloc[0])
    data_ap = st.date_input("Data", value=date.today())
    tipo = st.selectbox("Tipo do dia", ["NORMAL","FERIADO","SABADO","DOMINGO"])
    valor = st.number_input("Valor base", min_value=0.0, step=50.0)
    desconto = st.number_input("Desconto", min_value=0.0, step=10.0)

    if st.button("Salvar apontamento", type="primary"):
        try:
            exec_sql(
                """
                insert into public.apontamentos
                (obra_id,pessoa_id,data,tipo_dia,valor_base,desconto_valor)
                values (%s,%s,%s,%s,%s,%s)
                """,
                (obra_id,pessoa_id,data_ap,tipo,valor,desconto),
            )
            st.success("Apontamento salvo.")
            st.rerun()
        except Exception as e:
            st.error("Erro ao salvar (provável duplicidade).")
            st.exception(e)

    st.divider()
    df = safe_df("""
        select a.id, a.data, p.nome pessoa, o.titulo obra,
               a.tipo_dia, a.valor_final
        from public.apontamentos a
        join public.pessoas p on p.id=a.pessoa_id
        join public.obras o on o.id=a.obra_id
        order by a.data desc limit 50;
    """)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ======================================================
# FINANCEIRO
# ======================================================
if menu == "FINANCEIRO":
    st.subheader("💰 Financeiro")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Gerar pagamentos da semana")
        segunda = st.date_input("Segunda-feira", value=monday(date.today()))
        if st.button("Gerar pagamentos", type="primary"):
            exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
            st.success("Pagamentos gerados.")
            st.rerun()

    with col2:
        st.markdown("### Pendentes")
        dfp = safe_df("select * from public.pagamentos_pendentes;")
        st.dataframe(dfp, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### Pagar / Estornar")

    dfp = safe_df("select * from public.pagamentos_pendentes;")
    if not dfp.empty:
        pid = st.selectbox("Pagamento", dfp["id"])
        data_pg = st.date_input("Data pagamento", value=date.today())

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Marcar como PAGO", type="primary"):
                exec_sql(
                    "select public.fn_marcar_pagamento_pago(%s,%s,%s);",
                    (int(pid), usuario, data_pg),
                )
                st.success("Pagamento realizado.")
                st.rerun()

        with c2:
            motivo = st.text_input("Motivo estorno")
            if st.button("Estornar"):
                exec_sql(
                    "select public.fn_estornar_pagamento(%s,%s,%s);",
                    (int(pid), usuario, motivo),
                )
                st.success("Pagamento estornado.")
                st.rerun()

    st.divider()
    st.markdown("### Histórico (últimos 30 dias)")
    dfh = safe_df("select * from public.pagamentos_pagos_30d;")
    st.dataframe(dfh, use_container_width=True, hide_index=True)

# ======================================================
# ADMIN
# ======================================================
if menu == "ADMIN":
    st.subheader("⚙️ Administração")

    st.markdown("### Usuários")
    dfu = safe_df("select usuario, perfil, ativo from public.usuarios_app order by usuario;")
    st.dataframe(dfu, use_container_width=True, hide_index=True)

    with st.expander("➕ Novo usuário"):
        u = st.text_input("Usuário")
        s = st.text_input("Senha")
        perfil = st.selectbox("Perfil", ["ADMIN","OPERACAO"])
        if st.button("Criar usuário", type="primary"):
            exec_sql(
                """
                insert into public.usuarios_app
                (usuario,senha_hash,perfil,ativo)
                values (%s,%s,%s,true)
                """,
                (u,s,perfil),
            )
            st.success("Usuário criado.")
            st.rerun()

    st.divider()
    st.markdown("### Auditoria (últimos 200)")
    dfa = safe_df("select * from public.auditoria order by criado_em desc limit 200;")
    st.dataframe(dfa, use_container_width=True, hide_index=True)
