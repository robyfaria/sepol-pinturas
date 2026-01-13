import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta
import socket

st.set_page_config(page_title="SEPOL - Teste DB", layout="wide")

# -----------------------------
# DB Helpers
# -----------------------------
@st.cache_resource
def get_conn():
    url = st.secrets["DATABASE_URL"]
    return psycopg2.connect(url, cursor_factory=RealDictCursor, connect_timeout=10)

st.title("Teste de conexão Supabase")

# Debug 1: DNS resolve?
host = "db.liwsnxcajoglokxfvqld.supabase.co"
try:
    ip = socket.gethostbyname(host)
    st.success(f"DNS OK: {host} -> {ip}")
except Exception as e:
    st.error("DNS falhou no Streamlit Cloud (não conseguiu resolver o host).")
    st.exception(e)
    st.stop()

# Debug 2: conecta e faz SELECT now()
try:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("select now() as agora;")
        row = cur.fetchone()
    st.success("Conexão OK ✅")
    st.write(row)
except Exception as e:
    st.error("Falha ao conectar no Postgres.")
    st.exception(e)
    st.stop()

def query_df(sql, params=None):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
    return pd.DataFrame(rows)

def exec_sql(sql, params=None):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
    conn.commit()

def next_friday(d: date) -> date:
    # Monday=0 ... Sunday=6  | Friday=4
    return d + timedelta((4 - d.weekday()) % 7)

# -----------------------------
# UI
# -----------------------------
st.title("SEPOL - Controle de Obras (MVP)")

menu = st.sidebar.radio("Menu", ["Apontamentos", "Gerar Pagamentos", "Pagar"])

# Helper: carregar opções
df_pessoas = query_df("select id, nome from public.pessoas where ativo = true order by nome;")
df_obras = query_df("select id, titulo from public.obras order by id desc;")

# -----------------------------
# 1) Apontamentos
# -----------------------------
if menu == "Apontamentos":
    st.subheader("Apontamentos (lançar trabalho)")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        obra_id = st.selectbox(
            "Obra",
            options=df_obras["id"].tolist() if not df_obras.empty else [],
            format_func=lambda x: df_obras.loc[df_obras["id"] == x, "titulo"].iloc[0] if not df_obras.empty else str(x),
        )

    # Fases da obra (opcional)
    df_fases = pd.DataFrame()
    if obra_id:
        df_fases = query_df(
            "select id, ordem, nome_fase from public.obra_fases where obra_id=%s order by ordem;",
            (obra_id,),
        )

    with col2:
        obra_fase_id = st.selectbox(
            "Fase (opcional)",
            options=[None] + (df_fases["id"].tolist() if not df_fases.empty else []),
            format_func=lambda x: "—" if x is None else (
                f"{int(df_fases.loc[df_fases['id']==x, 'ordem'].iloc[0])} - {df_fases.loc[df_fases['id']==x, 'nome_fase'].iloc[0]}"
            ),
        )

    with col3:
        pessoa_id = st.selectbox(
            "Pessoa",
            options=df_pessoas["id"].tolist() if not df_pessoas.empty else [],
            format_func=lambda x: df_pessoas.loc[df_pessoas["id"] == x, "nome"].iloc[0] if not df_pessoas.empty else str(x),
        )

    with col4:
        data_ap = st.date_input("Data", value=date.today())

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        tipo_dia = st.selectbox("Tipo do dia", ["NORMAL", "FERIADO", "SABADO", "DOMINGO"])
    with col6:
        valor_base = st.number_input("Valor base (R$)", min_value=0.0, step=10.0, value=0.0)
    with col7:
        desconto = st.number_input("Desconto (R$)", min_value=0.0, step=10.0, value=0.0)
    with col8:
        obs = st.text_input("Observação (opcional)", value="")

    if st.button("Salvar apontamento", type="primary"):
        exec_sql(
            """
            insert into public.apontamentos
              (obra_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
            values
              (%s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (obra_id, obra_fase_id, pessoa_id, data_ap, tipo_dia, valor_base, desconto, obs),
        )
        st.success("Apontamento salvo! (acréscimos e valor_final calculados automaticamente)")
        st.rerun()

    st.divider()
    st.subheader("Apontamentos recentes")
    df_recent = query_df(
        """
        select a.id, a.data, p.nome as pessoa, a.tipo_dia, a.valor_base, a.acrescimo_pct, a.desconto_valor, a.valor_final,
               o.titulo as obra, coalesce(ofa.nome_fase,'') as fase
        from public.apontamentos a
        join public.pessoas p on p.id = a.pessoa_id
        join public.obras o on o.id = a.obra_id
        left join public.obra_fases ofa on ofa.id = a.obra_fase_id
        order by a.data desc, a.id desc
        limit 100;
        """
    )
    st.dataframe(df_recent, use_container_width=True)

# -----------------------------
# 2) Gerar Pagamentos
# -----------------------------
elif menu == "Gerar Pagamentos":
    st.subheader("Gerar Pagamentos (semanal + extras)")

    # usuário simples (MVP) pra auditoria
    usuario = st.text_input("Usuário (para auditoria)", value="admin")

    # escolher a segunda-feira
    col1, col2 = st.columns(2)
    with col1:
        segunda = st.date_input("Segunda-feira da semana", value=date.today() - timedelta(days=date.today().weekday()))
    with col2:
        sexta = segunda + timedelta(days=4)
        st.metric("Semana (Seg–Sex)", f"{segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")

    if st.button("Gerar pagamentos desta semana", type="primary"):
        exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
        st.success("Pagamentos gerados/atualizados!")
        st.rerun()

    st.divider()
    st.subheader("Pagamentos gerados (ABERTOS) desta semana + extras (sáb/dom)")
    df_pg = query_df(
        """
        select p.id, pe.nome as pessoa, p.tipo, p.status, p.valor_total, p.referencia_inicio, p.referencia_fim
        from public.pagamentos p
        join public.pessoas pe on pe.id = p.pessoa_id
        where p.status='ABERTO'
          and (
            (p.tipo='SEMANAL' and p.referencia_inicio=%s and p.referencia_fim=%s)
            or
            (p.tipo='EXTRA' and p.referencia_inicio between %s and %s)
          )
        order by pe.nome, p.tipo, p.referencia_inicio;
        """,
        (segunda, sexta, segunda, segunda + timedelta(days=6)),
    )
    st.dataframe(df_pg, use_container_width=True)

# -----------------------------
# 3) Pagar
# -----------------------------
else:
    st.subheader("Pagar (pendentes)")
    usuario = st.text_input("Usuário (para auditoria)", value="admin")
    data_pg = st.date_input("Data do pagamento", value=date.today())

    tab1, tab2 = st.tabs(["Para a próxima sexta", "Todos pendentes"])

    with tab1:
        df_sexta = query_df("select * from public.pagamentos_para_sexta;")
        st.dataframe(df_sexta, use_container_width=True)

        if not df_sexta.empty:
            ids = df_sexta["id"].tolist()
            selecionados = st.multiselect("Selecione pagamentos para marcar como PAGO", ids)
            if st.button("Marcar selecionados como PAGO", type="primary"):
                for pid in selecionados:
                    exec_sql("select public.fn_marcar_pagamento_pago(%s, %s, %s);", (pid, usuario, data_pg))
                st.success("Pagamentos marcados como PAGO!")
                st.rerun()

    with tab2:
        df_pend = query_df("select * from public.pagamentos_pendentes;")
        st.dataframe(df_pend, use_container_width=True)

        if not df_pend.empty:
            ids2 = df_pend["id"].tolist()
            selecionados2 = st.multiselect("Selecione pagamentos para marcar como PAGO", ids2)
            if st.button("Marcar pendentes selecionados como PAGO"):
                for pid in selecionados2:
                    exec_sql("select public.fn_marcar_pagamento_pago(%s, %s, %s);", (pid, usuario, data_pg))
                st.success("Pagamentos marcados como PAGO!")
                st.rerun()
