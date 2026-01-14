import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

st.set_page_config(page_title="SEPOL - Pinturas", layout="wide")

# -------------------------
# DB
# -------------------------
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

def safe_query(sql, params=None):
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

def monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())

# -------------------------
# UI - Sidebar Menu State
# -------------------------
st.title("SEPOL - Controle de Obras (modo simples)")

with st.sidebar:
    st.header("Acesso")
    usuario = st.text_input("Usuário", value="admin")

    st.divider()
    if "menu" not in st.session_state:
        st.session_state["menu"] = "HOJE"

    st.selectbox(
        "Menu",
        ["HOJE", "Apontamentos", "Gerar Pagamentos", "Pagar", "Cadastros (mínimo)"],
        key="menu"
    )

menu = st.session_state["menu"]

# -------------------------
# HOME
# -------------------------
if menu == "HOJE":
    st.subheader("Resumo de hoje")

    kpi = safe_query("select * from public.home_hoje_kpis;")
    if not kpi.empty:
        r = kpi.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Hoje", str(r["hoje"]))
        c2.metric("Sexta-alvo", str(r["sexta"]))
        c3.metric("Fases em andamento", int(r["fases_em_andamento"]))
        c4.metric("Recebimentos vencidos", int(r["recebimentos_vencidos_qtd"]))
        c5.metric("A receber (total)", brl(r["recebimentos_pendentes_total"]))

        c6, c7 = st.columns(2)
        c6.metric("Pagar na sexta (total)", brl(r["pagar_na_sexta_total"]))
        c7.metric("Extras pendentes (total)", brl(r["extras_pendentes_total"]))
    else:
        st.info("Sem dados ainda. Cadastre pessoas/clientes/obras e registre apontamentos.")

    st.divider()
    st.markdown("## HOJE eu preciso fazer")

    hoje = date.today()
    segunda = monday_of_week(hoje)
    sexta = segunda + timedelta(days=4)

    qtd_ap_hoje = int(safe_query("select count(*) as qtd from public.apontamentos where data=current_date;").iloc[0]["qtd"])
    qtd_pg_sem = int(safe_query(
        "select count(*) as qtd from public.pagamentos where tipo='SEMANAL' and referencia_inicio=%s and referencia_fim=%s;",
        (segunda, sexta)
    ).iloc[0]["qtd"])

    qtd_para_sexta = int(safe_query("select count(*) as qtd from public.pagamentos_para_sexta;").iloc[0]["qtd"])
    qtd_extras = int(safe_query("select count(*) as qtd from public.pagamentos_extras_pendentes;").iloc[0]["qtd"])

    def badge(ok: bool): return "✅" if ok else "⚠️"

    colL, colR = st.columns([2, 3])

    with colL:
        st.markdown(f"### {badge(qtd_ap_hoje > 0)} 1) Lançar apontamentos (hoje)")
        st.caption(f"Apontamentos hoje: {qtd_ap_hoje}")
        if st.button("Ir para Apontamentos", type="primary", use_container_width=True, key="go_ap"):
            st.session_state["menu"] = "Apontamentos"
            st.rerun()

        st.markdown(f"### {badge(qtd_pg_sem > 0)} 2) Gerar pagamentos da semana")
        st.caption(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")
        if st.button("Ir para Gerar Pagamentos", use_container_width=True, key="go_gp"):
            st.session_state["menu"] = "Gerar Pagamentos"
            st.rerun()

    with colR:
        st.markdown(f"### {badge(qtd_para_sexta == 0)} 3) Pagar na sexta")
        st.caption("Pendências para sexta: " + str(qtd_para_sexta))
        if st.button("Ir para Pagar", use_container_width=True, key="go_pay"):
            st.session_state["menu"] = "Pagar"
            st.rerun()

        st.markdown(f"### {badge(qtd_extras == 0)} 4) Pagar extras (sábado/domingo)")
        st.caption("Extras pendentes: " + str(qtd_extras))
        if st.button("Ir para Pagar (extras)", use_container_width=True, key="go_pay2"):
            st.session_state["menu"] = "Pagar"
            st.rerun()

    st.divider()
    if st.checkbox("Mostrar detalhes", value=False):
        df_and = safe_query("select * from public.home_hoje_fases_em_andamento limit 50;")
        df_rec = safe_query("select * from public.home_hoje_recebimentos_pendentes limit 50;")
        st.markdown("### Fases em andamento")
        st.dataframe(df_and, use_container_width=True, hide_index=True)
        st.markdown("### Recebimentos pendentes")
        st.dataframe(df_rec, use_container_width=True, hide_index=True)

# -------------------------
# CADASTROS (mínimo)
# -------------------------
if menu == "Cadastros (mínimo)":
    st.subheader("Cadastros mínimos (para iniciar)")
    tab1, tab2, tab3 = st.tabs(["Pessoas", "Clientes", "Obras"])

    with tab1:
        nome = st.text_input("Nome", key="p_nome")
        tipo = st.selectbox("Tipo", ["PINTOR", "AJUDANTE", "TERCEIRO"], key="p_tipo")
        tel = st.text_input("Telefone (opcional)", key="p_tel")
        if st.button("Salvar pessoa", type="primary", key="btn_save_pessoa"):
            if not nome.strip():
                st.warning("Informe o nome.")
            else:
                exec_sql("insert into public.pessoas (nome, tipo, telefone, ativo) values (%s,%s,%s,true);",
                         (nome.strip(), tipo, tel.strip() or None))
                st.success("Pessoa cadastrada!")
                st.rerun()
        st.divider()
        st.dataframe(safe_query("select id,nome,tipo,telefone,ativo,criado_em from public.pessoas order by id desc limit 100;"),
                     use_container_width=True, hide_index=True)

    with tab2:
        nome = st.text_input("Nome do cliente", key="c_nome")
        tel = st.text_input("Telefone (opcional)", key="c_tel")
        end = st.text_input("Endereço (opcional)", key="c_end")
        origem = st.selectbox("Origem", ["PROPRIO", "INDICADO"], key="c_origem")

        df_ind = safe_query("select id,nome from public.indicadores where ativo=true order by nome;")
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
                    "insert into public.clientes (nome,telefone,endereco,origem,indicador_id,ativo) values (%s,%s,%s,%s,%s,true);",
                    (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicador_id),
                )
                st.success("Cliente cadastrado!")
                st.rerun()

        st.divider()
        st.dataframe(safe_query("select id,nome,telefone,origem,indicador_id,ativo,criado_em from public.clientes order by id desc limit 100;"),
                     use_container_width=True, hide_index=True)

    with tab3:
        df_cli = safe_query("select id,nome from public.clientes where ativo=true order by nome;")
        if df_cli.empty:
            st.info("Cadastre um cliente primeiro.")
        else:
            cliente_id = st.selectbox("Cliente", df_cli["id"].tolist(),
                                      format_func=lambda x: df_cli.loc[df_cli["id"]==x,"nome"].iloc[0],
                                      key="o_cli")
            titulo = st.text_input("Título da obra", key="o_tit")
            end = st.text_input("Endereço da obra (opcional)", key="o_end")
            status = st.selectbox("Status", ["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"], key="o_status")
            if st.button("Salvar obra", type="primary", key="btn_save_obra"):
                if not titulo.strip():
                    st.warning("Informe o título.")
                else:
                    exec_sql("insert into public.obras (cliente_id,titulo,endereco_obra,status) values (%s,%s,%s,%s);",
                             (cliente_id, titulo.strip(), end.strip() or None, status))
                    st.success("Obra cadastrada!")
                    st.rerun()

        st.divider()
        st.dataframe(safe_query("select id,cliente_id,titulo,status,criado_em from public.obras order by id desc limit 100;"),
                     use_container_width=True, hide_index=True)

# -------------------------
# APONTAMENTOS (B: botões por linha + editar/excluir)
# -------------------------
if menu == "Apontamentos":
    st.subheader("Apontamentos (lançar trabalho)")
    st.caption("Regra: 1 apontamento por pessoa, por dia, por obra. Se errar: edite ou exclua.")

    df_pessoas = safe_query("select id,nome from public.pessoas where ativo=true order by nome;")
    df_obras = safe_query("select id,titulo from public.obras order by id desc;")

    if df_pessoas.empty or df_obras.empty:
        st.info("Cadastre pelo menos 1 pessoa e 1 obra na aba 'Cadastros (mínimo)'.")
        st.stop()

    # Estado de edição
    if "edit_ap_id" not in st.session_state:
        st.session_state["edit_ap_id"] = None

    edit_id = st.session_state["edit_ap_id"]

    # Carrega valores se estiver editando
    edit_row = None
    if edit_id:
        df_edit = safe_query(
            """
            select a.*
            from public.apontamentos a
            where a.id=%s
            """, (edit_id,)
        )
        if not df_edit.empty:
            edit_row = df_edit.iloc[0]
        else:
            st.session_state["edit_ap_id"] = None
            edit_id = None

    # Formulário (novo ou edição)
    st.markdown("### " + ("Editar apontamento" if edit_id else "Novo apontamento"))

    col1, col2, col3 = st.columns(3)
    with col1:
        obra_id = st.selectbox(
            "Obra",
            options=df_obras["id"].tolist(),
            index=(df_obras["id"].tolist().index(int(edit_row["obra_id"])) if edit_row is not None else 0),
            format_func=lambda x: df_obras.loc[df_obras["id"]==x,"titulo"].iloc[0],
            key="ap_obra"
        )
    with col2:
        pessoa_id = st.selectbox(
            "Pessoa",
            options=df_pessoas["id"].tolist(),
            index=(df_pessoas["id"].tolist().index(int(edit_row["pessoa_id"])) if edit_row is not None else 0),
            format_func=lambda x: df_pessoas.loc[df_pessoas["id"]==x,"nome"].iloc[0],
            key="ap_pessoa"
        )
    with col3:
        data_ap = st.date_input(
            "Data",
            value=(edit_row["data"] if edit_row is not None else date.today()),
            key="ap_data"
        )

    # Fase (opcional)
    df_fases = safe_query("select id,ordem,nome_fase from public.obra_fases where obra_id=%s order by ordem;", (obra_id,))
    obra_fase_id = None
    if not df_fases.empty:
        default = None
        if edit_row is not None and pd.notna(edit_row["obra_fase_id"]):
            default = int(edit_row["obra_fase_id"])
        opts = [None] + df_fases["id"].tolist()
        idx = opts.index(default) if default in opts else 0
        obra_fase_id = st.selectbox(
            "Fase (opcional)",
            options=opts,
            index=idx,
            format_func=lambda x: "—" if x is None else f"{int(df_fases.loc[df_fases['id']==x,'ordem'].iloc[0])} - {df_fases.loc[df_fases['id']==x,'nome_fase'].iloc[0]}",
            key="ap_fase"
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        tipo_dia = st.selectbox("Tipo do dia", ["NORMAL","FERIADO","SABADO","DOMINGO"],
                                index=(["NORMAL","FERIADO","SABADO","DOMINGO"].index(edit_row["tipo_dia"]) if edit_row is not None else 0),
                                key="ap_tipo")
    with c2:
        valor_base = st.number_input("Valor base (R$)", min_value=0.0, step=10.0,
                                     value=(float(edit_row["valor_base"]) if edit_row is not None else 0.0),
                                     key="ap_vb")
    with c3:
        desconto = st.number_input("Desconto (R$)", min_value=0.0, step=10.0,
                                   value=(float(edit_row["desconto_valor"]) if edit_row is not None else 0.0),
                                   key="ap_desc")
    with c4:
        obs = st.text_input("Observação", value=(edit_row["observacao"] or "" if edit_row is not None else ""), key="ap_obs")

    # trava se já foi pago
    travado_pago = False
    if edit_id:
        df_lock = safe_query(
            """
            select exists (
              select 1
              from public.pagamento_itens pi
              join public.pagamentos p on p.id = pi.pagamento_id
              where pi.apontamento_id = %s and p.status = 'PAGO'
            ) as travado;
            """, (edit_id,)
        )
        travado_pago = bool(df_lock.iloc[0]["travado"])

    btnA, btnB, btnC = st.columns([2,2,2])

    with btnA:
        if not edit_id:
            if st.button("Salvar apontamento", type="primary", use_container_width=True, key="btn_ap_save"):
                try:
                    exec_sql(
                        """
                        insert into public.apontamentos
                          (obra_id, obra_fase_id, pessoa_id, data, tipo_dia, valor_base, desconto_valor, observacao)
                        values
                          (%s,%s,%s,%s,%s,%s,%s,%s);
                        """,
                        (obra_id, obra_fase_id, pessoa_id, data_ap, tipo_dia, valor_base, desconto, obs.strip() or None),
                    )
                    st.success("Apontamento salvo!")
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    st.warning("Já existe apontamento para essa pessoa nesse dia nessa obra.")
                    st.stop()
                except Exception as e:
                    st.error("Erro ao salvar apontamento.")
                    st.exception(e)
                    st.stop()
        else:
            if st.button("Salvar alteração", type="primary", use_container_width=True, disabled=travado_pago, key="btn_ap_update"):
                try:
                    exec_sql(
                        """
                        update public.apontamentos
                        set obra_id=%s,
                            obra_fase_id=%s,
                            pessoa_id=%s,
                            data=%s,
                            tipo_dia=%s,
                            valor_base=%s,
                            desconto_valor=%s,
                            observacao=%s
                        where id=%s;
                        """,
                        (obra_id, obra_fase_id, pessoa_id, data_ap, tipo_dia, valor_base, desconto, obs.strip() or None, edit_id),
                    )
                    st.success("Apontamento atualizado! (se já tinha gerado pagamentos, clique em 'Gerar Pagamentos' novamente)")
                    st.session_state["edit_ap_id"] = None
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    st.warning("Conflito: já existe apontamento para essa pessoa nesse dia nessa obra.")
                    st.stop()
                except Exception as e:
                    st.error("Erro ao atualizar apontamento.")
                    st.exception(e)
                    st.stop()

    with btnB:
        if edit_id:
            if st.button("Excluir", use_container_width=True, disabled=travado_pago, key="btn_ap_delete"):
                st.session_state["confirm_delete_ap_id"] = edit_id

    with btnC:
        if edit_id:
            if st.button("Cancelar edição", use_container_width=True, key="btn_ap_cancel"):
                st.session_state["edit_ap_id"] = None
                st.session_state.pop("confirm_delete_ap_id", None)
                st.rerun()

    if edit_id and travado_pago:
        st.warning("Este apontamento está ligado a pagamento PAGO. Não pode editar nem excluir.")

    # Confirmação de exclusão
    if st.session_state.get("confirm_delete_ap_id") == edit_id:
        st.error("Confirma excluir este apontamento?")
        cX, cY = st.columns(2)
        with cX:
            if st.button("SIM, excluir", type="primary", use_container_width=True, key="btn_ap_delete_yes"):
                try:
                    # se estiver ligado a pagamento ABERTO, removemos o item também
                    exec_sql("delete from public.pagamento_itens where apontamento_id=%s;", (edit_id,))
                    exec_sql("delete from public.apontamentos where id=%s;", (edit_id,))
                    st.success("Apontamento excluído!")
                    st.session_state["edit_ap_id"] = None
                    st.session_state.pop("confirm_delete_ap_id", None)
                    st.rerun()
                except Exception as e:
                    st.error("Erro ao excluir.")
                    st.exception(e)
                    st.stop()
        with cY:
            if st.button("NÃO", use_container_width=True, key="btn_ap_delete_no"):
                st.session_state.pop("confirm_delete_ap_id", None)
                st.rerun()

    st.divider()
    st.markdown("### Apontamentos recentes (editar / excluir)")

    df_recent = safe_query(
        """
        select
          a.id,
          a.data,
          p.nome as pessoa,
          o.titulo as obra,
          a.tipo_dia,
          a.valor_base,
          a.desconto_valor,
          a.valor_final,
          exists (
            select 1
            from public.pagamento_itens pi
            join public.pagamentos pg on pg.id = pi.pagamento_id
            where pi.apontamento_id = a.id and pg.status='PAGO'
          ) as travado_pago,
          exists (
            select 1
            from public.pagamento_itens pi
            join public.pagamentos pg on pg.id = pi.pagamento_id
            where pi.apontamento_id = a.id
          ) as ja_gerou_pagamento
        from public.apontamentos a
        join public.pessoas p on p.id=a.pessoa_id
        join public.obras o on o.id=a.obra_id
        order by a.data desc, a.id desc
        limit 60;
        """
    )

    if df_recent.empty:
        st.info("Nenhum apontamento ainda.")
    else:
        for _, rr in df_recent.iterrows():
            colA, colB, colC, colD, colE, colF = st.columns([3,4,2,2,2,2])
            with colA:
                st.write(f"**{rr['data']}**")
                st.caption(rr["pessoa"])
            with colB:
                st.write(rr["obra"])
                tags = []
                if rr["ja_gerou_pagamento"]:
                    tags.append("🧾 já gerou pagamento")
                if rr["travado_pago"]:
                    tags.append("🔒 pago")
                if tags:
                    st.caption(" • ".join(tags))
            with colC:
                st.write(rr["tipo_dia"])
            with colD:
                st.write(brl(rr["valor_final"]))
            with colE:
                if st.button("Editar", key=f"ap_edit_{int(rr['id'])}", disabled=bool(rr["travado_pago"])):
                    st.session_state["edit_ap_id"] = int(rr["id"])
                    st.session_state.pop("confirm_delete_ap_id", None)
                    st.rerun()
            with colF:
                if st.button("Excluir", key=f"ap_del_{int(rr['id'])}", disabled=bool(rr["travado_pago"])):
                    st.session_state["edit_ap_id"] = int(rr["id"])
                    st.session_state["confirm_delete_ap_id"] = int(rr["id"])
                    st.rerun()

# -------------------------
# GERAR PAGAMENTOS
# -------------------------
if menu == "Gerar Pagamentos":
    st.subheader("Gerar Pagamentos")
    st.caption("Pode clicar novamente se você corrigiu apontamentos. Agora NÃO duplica (índice com COALESCE).")

    segunda = st.date_input("Segunda-feira da semana", value=monday_of_week(date.today()), key="gp_seg")
    sexta = segunda + timedelta(days=4)

    st.info(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")

    if st.button("Gerar pagamentos desta semana", type="primary", use_container_width=True, key="btn_gp"):
        try:
            exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
            st.success("Pagamentos gerados/atualizados!")
            st.rerun()
        except Exception as e:
            st.error("Erro ao gerar pagamentos.")
            st.exception(e)
            st.stop()

    st.divider()
    st.markdown("### Pagamentos ABERTOS desta semana")
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

# -------------------------
# PAGAR (botão por linha + lista de pagos)
# -------------------------
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
                    exec_sql("select public.fn_marcar_pagamento_pago(%s,%s,%s);", (int(r["id"]), usuario, data_pg))
                    st.success(f"Pago! {r['pessoa_nome']}")
                    st.rerun()

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
                    exec_sql("select public.fn_marcar_pagamento_pago(%s,%s,%s);", (int(r["id"]), usuario, data_pg))
                    st.success(f"Pago extra! {r['pessoa_nome']}")
                    st.rerun()

    st.divider()
    st.markdown("### Pagamentos realizados (últimos 30 dias)")
    df_pago = safe_query(
        """
        select
          p.id, pe.nome as pessoa, p.tipo, p.valor_total, p.pago_em, p.referencia_inicio, p.referencia_fim
        from public.pagamentos p
        join public.pessoas pe on pe.id=p.pessoa_id
        where p.status='PAGO'
          and p.pago_em >= (current_date - 30)
        order by p.pago_em desc, p.id desc
        limit 200;
        """
    )
    st.dataframe(df_pago, use_container_width=True, hide_index=True)
