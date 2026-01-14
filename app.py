import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

# =========================
# Config
# =========================
st.set_page_config(page_title="(DEV) SEPOL - Pinturas", layout="wide")

# =========================
# DB
# =========================
@st.cache_resource
def get_conn():
    # Use DATABASE_URL via pooler (transaction pooler)
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

def brl(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday=0

# =========================
# Header / User
# =========================
st.title("SEPOL - Controle de Obras (modo simples)")

with st.sidebar:
    st.header("Acesso")
    usuario = st.text_input("Usuário", value="admin")
    st.caption("Dica: use um nome simples, ex.: 'esposa' ou 'pintor'.")

    st.divider()
    menu = st.radio("Menu", ["HOJE", "Apontamentos", "Gerar Pagamentos", "Pagar", "Cadastros (mínimo)"])

# =========================
# Guardrails: checar views essenciais (sem travar tudo)
# =========================
def safe_query(sql, params=None):
    try:
        return query_df(sql, params)
    except Exception as e:
        st.error("Falha ao consultar o banco. Verifique se você rodou o SQL completo (tabelas + views + functions).")
        st.exception(e)
        st.stop()

# =========================
# HOME HOJE
# =========================
if menu == "HOJE":
    st.subheader("Resumo de hoje")

    kpi = safe_query("select * from public.home_hoje_kpis;")
    if kpi.empty:
        st.info("Sem dados ainda. Cadastre pelo menos 1 cliente/obra e registre apontamentos.")
    else:
        row = kpi.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Hoje", str(row["hoje"]))
        c2.metric("Sexta-alvo", str(row["sexta"]))
        c3.metric("Fases em andamento", int(row["fases_em_andamento"]))
        c4.metric("Recebimentos vencidos", int(row["recebimentos_vencidos_qtd"]))
        c5.metric("A receber (total)", brl(row["recebimentos_pendentes_total"]))

        c6, c7 = st.columns(2)
        c6.metric("Pagar na sexta (total)", brl(row["pagar_na_sexta_total"]))
        c7.metric("Extras pendentes (total)", brl(row["extras_pendentes_total"]))

    st.divider()
    
    # =========================
    # Painel "HOJE eu preciso fazer" (modo 60+)
    # =========================
    st.markdown("## HOJE eu preciso fazer")

    hoje = date.today()
    segunda = monday_of_week(hoje)
    sexta = segunda + timedelta(days=4)

    # 1) Apontamentos de hoje
    df_ap_hoje = safe_query("select count(*) as qtd from public.apontamentos where data = current_date;")
    qtd_ap_hoje = int(df_ap_hoje.iloc[0]["qtd"]) if not df_ap_hoje.empty else 0

    # 2) Pagamentos semanais da semana atual (se existe, já foi gerado)
    df_pg_sem = safe_query(
        """
        select count(*) as qtd
        from public.pagamentos
        where tipo='SEMANAL'
          and referencia_inicio=%s
          and referencia_fim=%s;
        """,
        (segunda, sexta),
    )
    qtd_pg_sem = int(df_pg_sem.iloc[0]["qtd"]) if not df_pg_sem.empty else 0

    # 3) Pendências para sexta
    df_para_sexta = safe_query("select count(*) as qtd from public.pagamentos_para_sexta;")
    qtd_para_sexta = int(df_para_sexta.iloc[0]["qtd"]) if not df_para_sexta.empty else 0

    # 4) Extras pendentes
    df_extras = safe_query("select count(*) as qtd from public.pagamentos_extras_pendentes;")
    qtd_extras = int(df_extras.iloc[0]["qtd"]) if not df_extras.empty else 0

    def badge(ok: bool):
        return "✅" if ok else "⚠️"

    colX, colY = st.columns([2, 3])

    with colX:
        st.markdown(f"### {badge(qtd_ap_hoje > 0)} 1) Lançar apontamentos (hoje)")
        st.caption(f"Hoje: {hoje.strftime('%d/%m/%Y')} • Apontamentos lançados: {qtd_ap_hoje}")
        if st.button("Ir para Apontamentos", type="primary", use_container_width=True, key="todo_go_ap"):
            st.session_state["__menu_jump"] = "Apontamentos"
            st.rerun()

        st.markdown(f"### {badge(qtd_pg_sem > 0)} 2) Gerar pagamentos da semana")
        st.caption(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')} • Gerado: {qtd_pg_sem}")
        if st.button("Ir para Gerar Pagamentos", use_container_width=True, key="todo_go_gp"):
            st.session_state["__menu_jump"] = "Gerar Pagamentos"
            st.rerun()

    with colY:
        st.markdown(f"### {badge(qtd_para_sexta == 0)} 3) Pagar na sexta")
        if qtd_para_sexta == 0:
            st.success("Nada pendente para a próxima sexta.")
        else:
            st.warning(f"Pendências para sexta: {qtd_para_sexta} pagamento(s).")
        if st.button("Ir para Pagar", use_container_width=True, key="todo_go_pay1"):
            st.session_state["__menu_jump"] = "Pagar"
            st.rerun()

        st.markdown(f"### {badge(qtd_extras == 0)} 4) Pagar extras (sábado/domingo)")
        if qtd_extras == 0:
            st.success("Sem extras pendentes.")
        else:
            st.warning(f"Extras pendentes: {qtd_extras} pagamento(s).")
        if st.button("Ir para Pagar (extras)", use_container_width=True, key="todo_go_pay2"):
            st.session_state["__menu_jump"] = "Pagar"
            st.rerun()

    st.divider()

    # =========================
    # AÇÕES RÁPIDAS
    # =========================
    st.markdown("### Ações rápidas")
    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("1) Lançar Apontamento", type="primary", use_container_width=True, key="go_apont"):
            st.session_state["__menu_jump"] = "Apontamentos"
            st.rerun()
    with a2:
        if st.button("2) Gerar Pagamentos", use_container_width=True, key="go_gerar"):
            st.session_state["__menu_jump"] = "Gerar Pagamentos"
            st.rerun()
    with a3:
        if st.button("3) Pagar (sexta e extras)", use_container_width=True, key="go_pagar"):
            st.session_state["__menu_jump"] = "Pagar"
            st.rerun()

    st.divider()

    # Listas curtas da home (bem “modo idoso”)
    colA, colB = st.columns(2)

    with colA:
        st.markdown("### Fases em andamento")
        df_and = safe_query("select * from public.home_hoje_fases_em_andamento limit 50;")
        if df_and.empty:
            st.info("Nenhuma fase em andamento.")
        else:
            st.dataframe(df_and, use_container_width=True, hide_index=True)

    with colB:
        st.markdown("### Recebimentos pendentes")
        df_rec = safe_query("select * from public.home_hoje_recebimentos_pendentes limit 50;")
        if df_rec.empty:
            st.info("Nenhum recebimento pendente.")
        else:
            st.dataframe(df_rec, use_container_width=True, hide_index=True)

    st.divider()

    st.markdown("### Pagamentos para a próxima sexta")
    df_sexta = safe_query("select * from public.home_hoje_pagamentos_para_sexta;")
    if df_sexta.empty:
        st.info("Nada para pagar na sexta-alvo.")
    else:
        st.dataframe(df_sexta, use_container_width=True, hide_index=True)

# Jump helper
if "__menu_jump" in st.session_state:
    menu = st.session_state.pop("__menu_jump")

# =========================
# CADASTROS (mínimo, para testar rápido)
# =========================
if menu == "Cadastros (mínimo)":
    st.subheader("Cadastros mínimos (para iniciar)")

    tab1, tab2, tab3 = st.tabs(["Pessoas", "Clientes", "Obras"])

    with tab1:
        st.markdown("#### Pessoas (pintores, ajudante, terceiros)")
        nome = st.text_input("Nome", key="p_nome")
        tipo = st.selectbox("Tipo", ["PINTOR", "AJUDANTE", "TERCEIRO"], key="p_tipo")
        tel = st.text_input("Telefone (opcional)", key="p_tel")

        if st.button("Salvar pessoa", type="primary", key="btn_save_pessoa"):
            if not nome.strip():
                st.warning("Informe o nome.")
            else:
                exec_sql(
                    "insert into public.pessoas (nome, tipo, telefone, ativo) values (%s,%s,%s,true);",
                    (nome.strip(), tipo, tel.strip() or None),
                )
                st.success("Pessoa cadastrada!")
                st.rerun()

        st.divider()
        df = safe_query("select id, nome, tipo, telefone, ativo, criado_em from public.pessoas order by id desc limit 100;")
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("#### Clientes")
        nome = st.text_input("Nome do cliente", key="c_nome")
        tel = st.text_input("Telefone (opcional)", key="c_tel")
        end = st.text_input("Endereço (opcional)", key="c_end")
        origem = st.selectbox("Origem", ["PROPRIO", "INDICADO"], key="c_origem")

        # Indicadores
        df_ind = safe_query("select id, nome from public.indicadores where ativo=true order by nome;")
        indicador_id = None
        if origem == "INDICADO":
            indicador_id = st.selectbox(
                "Indicador",
                options=df_ind["id"].tolist() if not df_ind.empty else [],
                format_func=lambda x: df_ind.loc[df_ind["id"] == x, "nome"].iloc[0] if not df_ind.empty else str(x),
                key="c_ind"
            )

        if st.button("Salvar cliente", type="primary", key="btn_save_cliente"):
            if not nome.strip():
                st.warning("Informe o nome.")
            elif origem == "INDICADO" and not indicador_id:
                st.warning("Selecione um indicador.")
            else:
                exec_sql(
                    """
                    insert into public.clientes (nome, telefone, endereco, origem, indicador_id, ativo)
                    values (%s,%s,%s,%s,%s,true);
                    """,
                    (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicador_id),
                )
                st.success("Cliente cadastrado!")
                st.rerun()

        st.divider()
        df = safe_query("select id, nome, telefone, origem, indicador_id, ativo, criado_em from public.clientes order by id desc limit 100;")
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab3:
        st.markdown("#### Obras")
        df_cli = safe_query("select id, nome from public.clientes where ativo=true order by nome;")
        if df_cli.empty:
            st.info("Cadastre um cliente primeiro.")
        else:
            cliente_id = st.selectbox(
                "Cliente",
                options=df_cli["id"].tolist(),
                format_func=lambda x: df_cli.loc[df_cli["id"] == x, "nome"].iloc[0],
                key="o_cli"
            )
            titulo = st.text_input("Título da obra (ex.: Apto 301 - Ed. X)", key="o_tit")
            end = st.text_input("Endereço da obra (opcional)", key="o_end")
            status = st.selectbox("Status", ["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"], key="o_status")

            if st.button("Salvar obra", type="primary", key="btn_save_obra"):
                if not titulo.strip():
                    st.warning("Informe o título.")
                else:
                    exec_sql(
                        """
                        insert into public.obras (cliente_id, titulo, endereco_obra, status)
                        values (%s,%s,%s,%s);
                        """,
                        (cliente_id, titulo.strip(), end.strip() or None, status),
                    )
                    st.success("Obra cadastrada!")
                    st.rerun()

        st.divider()
        df = safe_query("select id, cliente_id, titulo, status, criado_em from public.obras order by id desc limit 100;")
        st.dataframe(df, use_container_width=True, hide_index=True)

# =========================
# APONTAMENTOS (com bloqueio por UNIQUE no banco)
# =========================
if menu == "Apontamentos":
    st.subheader("Apontamentos (lançar trabalho)")
    st.caption("Regra: 1 apontamento por pessoa, por dia, por obra.")

    df_pessoas = safe_query("select id, nome from public.pessoas where ativo = true order by nome;")
    df_obras = safe_query("select id, titulo from public.obras order by id desc;")

    if df_pessoas.empty or df_obras.empty:
        st.info("Cadastre pelo menos 1 pessoa e 1 obra na aba 'Cadastros (mínimo)'.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            obra_id = st.selectbox(
                "Obra",
                options=df_obras["id"].tolist(),
                format_func=lambda x: df_obras.loc[df_obras["id"] == x, "titulo"].iloc[0],
                key="ap_obra"
            )
        with col2:
            pessoa_id = st.selectbox(
                "Pessoa",
                options=df_pessoas["id"].tolist(),
                format_func=lambda x: df_pessoas.loc[df_pessoas["id"] == x, "nome"].iloc[0],
                key="ap_pessoa"
            )
        with col3:
            data_ap = st.date_input("Data", value=date.today(), key="ap_data")

        # Fases (opcional)
        df_fases = safe_query("select id, ordem, nome_fase from public.obra_fases where obra_id=%s order by ordem;", (obra_id,))
        obra_fase_id = None
        if not df_fases.empty:
            obra_fase_id = st.selectbox(
                "Fase (opcional)",
                options=[None] + df_fases["id"].tolist(),
                format_func=lambda x: "—" if x is None else f"{int(df_fases.loc[df_fases['id']==x,'ordem'].iloc[0])} - {df_fases.loc[df_fases['id']==x,'nome_fase'].iloc[0]}",
                key="ap_fase"
            )

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            tipo_dia = st.selectbox("Tipo do dia", ["NORMAL", "FERIADO", "SABADO", "DOMINGO"], key="ap_tipo")
        with c2:
            valor_base = st.number_input("Valor base (R$)", min_value=0.0, step=10.0, value=0.0, key="ap_vb")
        with c3:
            desconto = st.number_input("Desconto (R$)", min_value=0.0, step=10.0, value=0.0, key="ap_desc")
        with c4:
            obs = st.text_input("Observação", value="", key="ap_obs")

        if st.button("Salvar apontamento", type="primary", use_container_width=True, key="btn_ap_save"):
            try:
                exec_sql(
                    """
                    insert into public.apontamentos
                      (obra_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
                    values
                      (%s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (obra_id, obra_fase_id, pessoa_id, data_ap, tipo_dia, valor_base, desconto, obs.strip() or None),
                )
                st.success("Apontamento salvo!")
                st.rerun()
            except psycopg2.errors.UniqueViolation:
                st.warning("Já existe apontamento para essa pessoa nesse dia nessa obra.")
            except Exception as e:
                st.error("Erro ao salvar apontamento.")
                st.exception(e)

        st.divider()
        st.markdown("### Apontamentos recentes")
        df_recent = safe_query(
            """
            select a.id, a.data, p.nome as pessoa, a.tipo_dia, a.valor_base, a.acrescimo_pct, a.desconto_valor, a.valor_final,
                   o.titulo as obra
            from public.apontamentos a
            join public.pessoas p on p.id = a.pessoa_id
            join public.obras o on o.id = a.obra_id
            order by a.data desc, a.id desc
            limit 80;
            """
        )
        st.dataframe(df_recent, use_container_width=True, hide_index=True)

# =========================
# GERAR PAGAMENTOS (sem duplicar por UNIQUE + ON CONFLICT)
# =========================
if menu == "Gerar Pagamentos":
    st.subheader("Gerar Pagamentos")
    st.caption("Pode clicar novamente se você corrigiu apontamentos. O sistema recalcula sem duplicar.")

    segunda = st.date_input("Segunda-feira da semana", value=monday_of_week(date.today()), key="gp_seg")
    sexta = segunda + timedelta(days=4)

    c1, c2 = st.columns(2)
    c1.info(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")
    c2.info("Inclui: NORMAL e FERIADO na semana • SÁB/DOM viram EXTRA separado")

    if st.button("Gerar pagamentos desta semana", type="primary", use_container_width=True, key="btn_gp"):
        try:
            exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
            st.success("Pagamentos gerados/atualizados!")
            st.rerun()
        except Exception as e:
            st.error("Erro ao gerar pagamentos.")
            st.exception(e)

    st.divider()
    st.markdown("### Resultado (abertos)")
    df_pg = safe_query(
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
    st.dataframe(df_pg, use_container_width=True, hide_index=True)

# =========================
# PAGAR (MODO 60+: botão por linha)
# =========================
if menu == "Pagar":
    st.subheader("Pagar (modo simples)")
    data_pg = st.date_input("Data do pagamento", value=date.today(), key="pay_date")

    st.markdown("### Pagar na próxima sexta")
    df_sexta = safe_query("select * from public.pagamentos_para_sexta;")

    if df_sexta.empty:
        st.info("Nada para pagar na próxima sexta.")
    else:
        for _, r in df_sexta.iterrows():
            col1, col2, col3, col4 = st.columns([5, 2, 2, 2])
            with col1:
                st.write(f"**{r['pessoa_nome']}**  •  {r['tipo']}")
            with col2:
                st.write(brl(r["valor_total"]))
            with col3:
                st.write(f"sexta: {r.get('sexta')}")
            with col4:
                if st.button("Pagar", type="primary", key=f"pay_{int(r['id'])}"):
                    try:
                        exec_sql(
                            "select public.fn_marcar_pagamento_pago(%s, %s, %s);",
                            (int(r["id"]), usuario, data_pg),
                        )
                        st.success(f"Pago! {r['pessoa_nome']}")
                        st.rerun()
                    except Exception as e:
                        st.error("Erro ao marcar como pago.")
                        st.exception(e)

    st.divider()
    st.markdown("### Extras pendentes (sábado/domingo)")
    df_extras = safe_query("select * from public.pagamentos_extras_pendentes;")

    if df_extras.empty:
        st.info("Sem extras pendentes.")
    else:
        for _, r in df_extras.iterrows():
            col1, col2, col3, col4 = st.columns([5, 2, 2, 2])
            with col1:
                st.write(f"**{r['pessoa_nome']}**  •  EXTRA")
            with col2:
                st.write(brl(r["valor_total"]))
            with col3:
                st.write(f"data: {r.get('data_extra')}")
            with col4:
                if st.button("Pagar", type="primary", key=f"pay_extra_{int(r['id'])}"):
                    try:
                        exec_sql(
                            "select public.fn_marcar_pagamento_pago(%s, %s, %s);",
                            (int(r["id"]), usuario, data_pg),
                        )
                        st.success(f"Pago extra! {r['pessoa_nome']}")
                        st.rerun()
                    except Exception as e:
                        st.error("Erro ao marcar extra como pago.")
                        st.exception(e)

    st.divider()
    st.markdown("### Todos os pagamentos pendentes (lista completa)")
    df_all = safe_query("select * from public.pagamentos_pendentes limit 200;")
    st.dataframe(df_all, use_container_width=True, hide_index=True)
