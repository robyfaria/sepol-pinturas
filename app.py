import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

st.set_page_config(page_title="SEPOL - Controle de Obras (MVP)", layout="wide")

@st.cache_resource
def get_conn():
    return psycopg2.connect(
        st.secrets["DATABASE_URL"],
        cursor_factory=RealDictCursor,
        connect_timeout=10,
    )

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
    return d + timedelta((4 - d.weekday()) % 7)  # Friday=4

st.title("SEPOL - Controle de Obras (MVP)")
menu = st.sidebar.radio("Menu", ["Apontamentos", "Gerar Pagamentos", "Pagar"])

# Carregar opções (com fallback se tabelas ainda não existem)
try:
    df_pessoas = query_df("select id, nome from public.pessoas where ativo = true order by nome;")
    df_obras = query_df("select id, titulo from public.obras order by id desc;")
except Exception as e:
    st.error("Conectou no banco, mas as tabelas ainda não existem (ou SQL do schema não foi executado).")
    st.exception(e)
    st.stop()

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
        try:
            exec_sql(
                """
                insert into public.apontamentos
                  (obra_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
                values
                  (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (obra_id, obra_fase_id, pessoa_id, data_ap, tipo_dia, valor_base, desconto, obs),
            )
            st.success("Apontamento salvo! (acréscimos e valor_final são calculados automaticamente)")
            st.rerun()
        except psycopg2.errors.UniqueViolation:
            st.warning("Já existe apontamento para essa pessoa nesse dia nessa obra. Se precisar corrigir, edite o registro.")
        except Exception as e:
            st.error("Erro ao salvar apontamento.")
            st.exception(e)

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

    usuario = st.text_input("Usuário (para auditoria)", value="admin")

    segunda = st.date_input("Segunda-feira da semana", value=date.today() - timedelta(days=date.today().weekday()))
    sexta = segunda + timedelta(days=4)
    st.info(f"Semana (Seg–Sex): {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")

    if st.button("Gerar pagamentos desta semana", type="primary"):
        exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
        st.success("Pagamentos gerados/atualizados!")
        st.rerun()

    st.divider()
    st.subheader("Pagamentos ABERTOS da semana + extras (sáb/dom)")
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
    st.subheader("Pagar (modo simples)")

    usuario = st.text_input("Usuário", value="admin")
    data_pg = st.date_input("Data do pagamento", value=date.today())

    # tenta carregar a view
    df_sexta = query_df("select * from public.pagamentos_para_sexta;")
    st.caption("Pagamentos para a próxima sexta")

    if df_sexta.empty:
        st.info("Nada para pagar na próxima sexta.")
    else:
        for _, row in df_sexta.iterrows():
            col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
            with col1:
                st.write(f"**{row['pessoa_nome']}**  •  {row['tipo']}")
            with col2:
                st.write(f"R$ {float(row['valor_total']):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with col3:
                st.write(str(row.get("sexta", "")))
            with col4:
                if st.button("Pagar", key=f"pagar_{row['id']}", type="primary"):
                    exec_sql("select public.fn_marcar_pagamento_pago(%s, %s, %s);", (int(row["id"]), usuario, data_pg))
                    st.success(f"Pago! ({row['pessoa_nome']})")
                    st.rerun()

    st.divider()
    st.caption("Extras pendentes (sábado/domingo)")
    df_extra = query_df("select * from public.pagamentos_extras_pendentes;")

    if df_extra.empty:
        st.info("Sem extras pendentes.")
    else:
        for _, row in df_extra.iterrows():
            col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
            with col1:
                st.write(f"**{row['pessoa_nome']}**  •  EXTRA")
            with col2:
                st.write(f"R$ {float(row['valor_total']):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with col3:
                st.write(str(row.get("data_extra", "")))
            with col4:
                if st.button("Pagar", key=f"pagar_extra_{row['id']}", type="primary"):
                    exec_sql("select public.fn_marcar_pagamento_pago(%s, %s, %s);", (int(row["id"]), usuario, data_pg))
                    st.success(f"Pago extra! ({row['pessoa_nome']})")
                    st.rerun()

