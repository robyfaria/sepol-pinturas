import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

# =========================
# Config
# =========================
st.set_page_config(page_title="SEPOL - Pinturas", layout="wide")
st.title("SEPOL - Controle de Obras (modo simples)")

# =========================
# DB
# =========================
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

# =========================
# Navegação segura (sem erro)
# =========================
def nav(destino: str):
    st.session_state["menu"] = destino

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("Acesso")
    usuario = st.text_input("Usuário", value="admin")

    st.divider()
    if "menu" not in st.session_state:
        st.session_state["menu"] = "HOJE"

    st.selectbox(
        "Menu",
        ["HOJE", "Cadastros", "Apontamentos", "Gerar Pagamentos", "Pagar"],
        key="menu",
    )

menu = st.session_state["menu"]

# =========================
# HOME
# =========================
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
        st.info("Sem dados ainda. Cadastre Indicações/Pessoas/Clientes/Obras e registre apontamentos.")

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

    colL1, colL2, colR1, colR2 = st.columns([3, 3, 3, 3])

    with colL1:
        st.markdown(f"### {badge(qtd_ap_hoje > 0)} 1) Lançar apontamentos (hoje)")
        st.caption(f"Apontamentos hoje: {qtd_ap_hoje}")
        st.button("Ir para Apontamentos", on_click=nav, args=("Apontamentos",), type="primary", use_container_width=True)

    with colL2:
        st.markdown(f"### {badge(qtd_pg_sem > 0)} 2) Gerar pagamentos da semana")
        st.caption(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")
        st.button("Ir para Gerar Pagamentos", on_click=nav, args=("Gerar Pagamentos",), use_container_width=True)

    with colR1:
        st.markdown(f"### {badge(qtd_para_sexta == 0)} 3) Pagar na sexta")
        st.caption(f"Pendências para sexta: {qtd_para_sexta}")
        st.button("Ir para Pagar", on_click=nav, args=("Pagar",), use_container_width=True)

    with colR2:
        st.markdown(f"### {badge(qtd_extras == 0)} 4) Pagar extras (sáb/dom)")
        st.caption(f"Extras pendentes: {qtd_extras}")
        st.button("Ir para Pagar (extras)", on_click=nav, args=("Pagar",), use_container_width=True)

# =========================
# CADASTROS (com editar/cancelar/inativar)
# =========================
if menu == "Cadastros":
    st.subheader("Cadastros")

    tabs = st.tabs(["Indicações", "Pessoas", "Clientes", "Obras"])

    # ---------- Helpers ----------
    def set_edit(key: str, rid: int | None):
        st.session_state[key] = rid

    def clear_edit(key: str):
        st.session_state[key] = None

    # ========== INDICAÇÕES ==========
    with tabs[0]:
        st.markdown("### Indicações (quem indicou)")

        if "edit_ind_id" not in st.session_state:
            st.session_state["edit_ind_id"] = None

        edit_id = st.session_state["edit_ind_id"]
        row = None
        if edit_id:
            df_one = safe_query("select * from public.indicacoes where id=%s;", (edit_id,))
            if not df_one.empty:
                row = df_one.iloc[0]
            else:
                clear_edit("edit_ind_id")
                edit_id = None

        st.markdown("#### " + ("Editar indicação" if edit_id else "Nova indicação"))
        c1, c2, c3 = st.columns(3)
        with c1:
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""), key="ind_nome")
        with c2:
            tipo = st.selectbox(
                "Tipo",
                ["ARQUITETO", "ENGENHEIRO", "LOJA", "OUTRO"],
                index=(["ARQUITETO","ENGENHEIRO","LOJA","OUTRO"].index(row["tipo"]) if row is not None else 0),
                key="ind_tipo"
            )
        with c3:
            tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row is not None else ""), key="ind_tel")

        b1, b2, b3 = st.columns([2,2,2])
        with b1:
            if not edit_id:
                if st.button("Salvar", type="primary", use_container_width=True, key="ind_save"):
                    if not nome.strip():
                        st.warning("Informe o nome.")
                        st.stop()
                    exec_sql(
                        "insert into public.indicacoes (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                        (nome.strip(), tipo, tel.strip() or None),
                    )
                    st.success("Indicação cadastrada!")
                    st.rerun()
            else:
                if st.button("Salvar alteração", type="primary", use_container_width=True, key="ind_update"):
                    if not nome.strip():
                        st.warning("Informe o nome.")
                        st.stop()
                    exec_sql(
                        "update public.indicacoes set nome=%s, tipo=%s, telefone=%s where id=%s;",
                        (nome.strip(), tipo, tel.strip() or None, int(edit_id)),
                    )
                    st.success("Indicação atualizada!")
                    clear_edit("edit_ind_id")
                    st.rerun()

        with b2:
            if edit_id:
                if st.button("Cancelar edição", use_container_width=True, key="ind_cancel"):
                    clear_edit("edit_ind_id")
                    st.rerun()

        st.divider()
        st.markdown("#### Lista")
        df = safe_query("select id, nome, tipo, telefone, ativo, criado_em from public.indicacoes order by nome;")

        if df.empty:
            st.info("Nenhuma indicação cadastrada.")
        else:
            for _, rr in df.iterrows():
                colA, colB, colC, colD, colE = st.columns([4,2,2,2,2])
                with colA:
                    st.write(f"**{rr['nome']}**")
                    st.caption(rr["tipo"])
                with colB:
                    st.write(rr["telefone"] or "")
                with colC:
                    st.write("ATIVO" if rr["ativo"] else "INATIVO")
                with colD:
                    if st.button("Editar", key=f"ind_edit_{int(rr['id'])}", disabled=not bool(rr["ativo"])):
                        set_edit("edit_ind_id", int(rr["id"]))
                        st.rerun()
                with colE:
                    if rr["ativo"]:
                        if st.button("Inativar", key=f"ind_inat_{int(rr['id'])}"):
                            exec_sql("update public.indicacoes set ativo=false where id=%s;", (int(rr["id"]),))
                            st.rerun()
                    else:
                        if st.button("Ativar", key=f"ind_at_{int(rr['id'])}"):
                            exec_sql("update public.indicacoes set ativo=true where id=%s;", (int(rr["id"]),))
                            st.rerun()

    # ========== PESSOAS ==========
    with tabs[1]:
        st.markdown("### Pessoas (pintores, ajudante, terceiros)")

        if "edit_pessoa_id" not in st.session_state:
            st.session_state["edit_pessoa_id"] = None

        edit_id = st.session_state["edit_pessoa_id"]
        row = None
        if edit_id:
            df_one = safe_query("select * from public.pessoas where id=%s;", (edit_id,))
            if not df_one.empty:
                row = df_one.iloc[0]
            else:
                clear_edit("edit_pessoa_id")
                edit_id = None

        st.markdown("#### " + ("Editar pessoa" if edit_id else "Nova pessoa"))
        c1, c2, c3 = st.columns(3)
        with c1:
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""), key="p_nome")
        with c2:
            tipo = st.selectbox(
                "Tipo",
                ["PINTOR", "AJUDANTE", "TERCEIRO"],
                index=(["PINTOR","AJUDANTE","TERCEIRO"].index(row["tipo"]) if row is not None else 0),
                key="p_tipo"
            )
        with c3:
            tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row is not None else ""), key="p_tel")

        b1, b2 = st.columns(2)
        with b1:
            if not edit_id:
                if st.button("Salvar", type="primary", use_container_width=True, key="p_save"):
                    if not nome.strip():
                        st.warning("Informe o nome.")
                        st.stop()
                    exec_sql("insert into public.pessoas (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                             (nome.strip(), tipo, tel.strip() or None))
                    st.success("Pessoa cadastrada!")
                    st.rerun()
            else:
                if st.button("Salvar alteração", type="primary", use_container_width=True, key="p_update"):
                    if not nome.strip():
                        st.warning("Informe o nome.")
                        st.stop()
                    exec_sql("update public.pessoas set nome=%s, tipo=%s, telefone=%s where id=%s;",
                             (nome.strip(), tipo, tel.strip() or None, int(edit_id)))
                    st.success("Pessoa atualizada!")
                    clear_edit("edit_pessoa_id")
                    st.rerun()

        with b2:
            if edit_id:
                if st.button("Cancelar edição", use_container_width=True, key="p_cancel"):
                    clear_edit("edit_pessoa_id")
                    st.rerun()

        st.divider()
        st.markdown("#### Lista")
        df = safe_query("select id, nome, tipo, telefone, ativo, criado_em from public.pessoas order by nome;")

        if df.empty:
            st.info("Nenhuma pessoa cadastrada.")
        else:
            for _, rr in df.iterrows():
                colA, colB, colC, colD, colE = st.columns([4,2,2,2,2])
                with colA:
                    st.write(f"**{rr['nome']}**")
                    st.caption(rr["tipo"])
                with colB:
                    st.write(rr["telefone"] or "")
                with colC:
                    st.write("ATIVO" if rr["ativo"] else "INATIVO")
                with colD:
                    if st.button("Editar", key=f"p_edit_{int(rr['id'])}", disabled=not bool(rr["ativo"])):
                        set_edit("edit_pessoa_id", int(rr["id"]))
                        st.rerun()
                with colE:
                    if rr["ativo"]:
                        if st.button("Inativar", key=f"p_inat_{int(rr['id'])}"):
                            exec_sql("update public.pessoas set ativo=false where id=%s;", (int(rr["id"]),))
                            st.rerun()
                    else:
                        if st.button("Ativar", key=f"p_at_{int(rr['id'])}"):
                            exec_sql("update public.pessoas set ativo=true where id=%s;", (int(rr["id"]),))
                            st.rerun()

    # ========== CLIENTES ==========
    with tabs[2]:
        st.markdown("### Clientes")

        if "edit_cliente_id" not in st.session_state:
            st.session_state["edit_cliente_id"] = None

        edit_id = st.session_state["edit_cliente_id"]
        row = None
        if edit_id:
            df_one = safe_query("select * from public.clientes where id=%s;", (edit_id,))
            if not df_one.empty:
                row = df_one.iloc[0]
            else:
                clear_edit("edit_cliente_id")
                edit_id = None

        df_ind = safe_query("select id, nome from public.indicacoes where ativo=true order by nome;")

        st.markdown("#### " + ("Editar cliente" if edit_id else "Novo cliente"))
        c1, c2, c3 = st.columns(3)
        with c1:
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""), key="c_nome")
        with c2:
            tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row is not None else ""), key="c_tel")
        with c3:
            end = st.text_input("Endereço (opcional)", value=(row["endereco"] or "" if row is not None else ""), key="c_end")

        origem = st.selectbox(
            "Origem",
            ["PROPRIO", "INDICADO"],
            index=(["PROPRIO","INDICADO"].index(row["origem"]) if row is not None else 0),
            key="c_origem"
        )

        indicacao_id = None
        if origem == "INDICADO":
            opts = df_ind["id"].tolist() if not df_ind.empty else []
            default = None
            if row is not None and pd.notna(row["indicacao_id"]):
                default = int(row["indicacao_id"])
            idx = opts.index(default) if default in opts else 0 if opts else 0

            if not opts:
                st.warning("Você selecionou INDICADO, mas não existe nenhuma Indicação ativa cadastrada.")
            indicacao_id = st.selectbox(
                "Quem indicou",
                options=opts,
                index=idx if opts else 0,
                format_func=lambda x: df_ind.loc[df_ind["id"] == x, "nome"].iloc[0] if not df_ind.empty else str(x),
                key="c_ind"
            )

        b1, b2 = st.columns(2)
        with b1:
            if not edit_id:
                if st.button("Salvar", type="primary", use_container_width=True, key="c_save"):
                    if not nome.strip():
                        st.warning("Informe o nome.")
                        st.stop()
                    if origem == "INDICADO" and not indicacao_id:
                        st.warning("Selecione quem indicou.")
                        st.stop()
                    exec_sql(
                        "insert into public.clientes (nome,telefone,endereco,origem,indicacao_id,ativo) values (%s,%s,%s,%s,%s,true);",
                        (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicacao_id),
                    )
                    st.success("Cliente cadastrado!")
                    st.rerun()
            else:
                if st.button("Salvar alteração", type="primary", use_container_width=True, key="c_update"):
                    if not nome.strip():
                        st.warning("Informe o nome.")
                        st.stop()
                    if origem == "INDICADO" and not indicacao_id:
                        st.warning("Selecione quem indicou.")
                        st.stop()
                    exec_sql(
                        "update public.clientes set nome=%s, telefone=%s, endereco=%s, origem=%s, indicacao_id=%s where id=%s;",
                        (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicacao_id, int(edit_id)),
                    )
                    st.success("Cliente atualizado!")
                    clear_edit("edit_cliente_id")
                    st.rerun()

        with b2:
            if edit_id:
                if st.button("Cancelar edição", use_container_width=True, key="c_cancel"):
                    clear_edit("edit_cliente_id")
                    st.rerun()

        st.divider()
        st.markdown("#### Lista")
        df = safe_query(
            """
            select c.id, c.nome, c.telefone, c.origem,
                   i.nome as indicacao_nome,
                   c.ativo, c.criado_em
            from public.clientes c
            left join public.indicacoes i on i.id = c.indicacao_id
            order by c.nome;
            """
        )
        if df.empty:
            st.info("Nenhum cliente cadastrado.")
        else:
            for _, rr in df.iterrows():
                colA, colB, colC, colD, colE, colF = st.columns([4,2,2,3,2,2])
                with colA:
                    st.write(f"**{rr['nome']}**")
                with colB:
                    st.write(rr["telefone"] or "")
                with colC:
                    st.write(rr["origem"])
                with colD:
                    st.write(rr["indicacao_nome"] or "")
                with colE:
                    st.write("ATIVO" if rr["ativo"] else "INATIVO")
                with colF:
                    r_id = int(rr["id"])
                    b_edit, b_act = st.columns(2)
                    with b_edit:
                        if st.button("Editar", key=f"c_edit_{r_id}", disabled=not bool(rr["ativo"])):
                            set_edit("edit_cliente_id", r_id)
                            st.rerun()
                    with b_act:
                        if rr["ativo"]:
                            if st.button("Inativar", key=f"c_inat_{r_id}"):
                                exec_sql("update public.clientes set ativo=false where id=%s;", (r_id,))
                                st.rerun()
                        else:
                            if st.button("Ativar", key=f"c_at_{r_id}"):
                                exec_sql("update public.clientes set ativo=true where id=%s;", (r_id,))
                                st.rerun()

    # ========== OBRAS ==========
    with tabs[3]:
        st.markdown("### Obras")

        if "edit_obra_id" not in st.session_state:
            st.session_state["edit_obra_id"] = None

        edit_id = st.session_state["edit_obra_id"]
        row = None
        if edit_id:
            df_one = safe_query("select * from public.obras where id=%s;", (edit_id,))
            if not df_one.empty:
                row = df_one.iloc[0]
            else:
                clear_edit("edit_obra_id")
                edit_id = None

        df_cli = safe_query("select id, nome from public.clientes where ativo=true order by nome;")
        if df_cli.empty:
            st.info("Cadastre um cliente ativo primeiro.")
        else:
            st.markdown("#### " + ("Editar obra" if edit_id else "Nova obra"))

            cli_ids = df_cli["id"].tolist()
            default_cli = int(row["cliente_id"]) if row is not None else cli_ids[0]
            cli_idx = cli_ids.index(default_cli) if default_cli in cli_ids else 0

            c1, c2, c3 = st.columns(3)
            with c1:
                cliente_id = st.selectbox(
                    "Cliente",
                    options=cli_ids,
                    index=cli_idx,
                    format_func=lambda x: df_cli.loc[df_cli["id"]==x, "nome"].iloc[0],
                    key="o_cli"
                )
            with c2:
                titulo = st.text_input("Título da obra", value=(row["titulo"] if row is not None else ""), key="o_tit")
            with c3:
                status = st.selectbox(
                    "Status",
                    ["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"],
                    index=(["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"].index(row["status"]) if row is not None else 0),
                    key="o_status"
                )
            end = st.text_input("Endereço da obra (opcional)", value=(row["endereco_obra"] or "" if row is not None else ""), key="o_end")

            b1, b2 = st.columns(2)
            with b1:
                if not edit_id:
                    if st.button("Salvar", type="primary", use_container_width=True, key="o_save"):
                        if not titulo.strip():
                            st.warning("Informe o título.")
                            st.stop()
                        exec_sql(
                            "insert into public.obras (cliente_id,titulo,endereco_obra,status) values (%s,%s,%s,%s);",
                            (cliente_id, titulo.strip(), end.strip() or None, status),
                        )
                        st.success("Obra cadastrada!")
                        st.rerun()
                else:
                    if st.button("Salvar alteração", type="primary", use_container_width=True, key="o_update"):
                        if not titulo.strip():
                            st.warning("Informe o título.")
                            st.stop()
                        exec_sql(
                            "update public.obras set cliente_id=%s, titulo=%s, endereco_obra=%s, status=%s where id=%s;",
                            (cliente_id, titulo.strip(), end.strip() or None, status, int(edit_id)),
                        )
                        st.success("Obra atualizada!")
                        clear_edit("edit_obra_id")
                        st.rerun()

            with b2:
                if edit_id:
                    if st.button("Cancelar edição", use_container_width=True, key="o_cancel"):
                        clear_edit("edit_obra_id")
                        st.rerun()

        st.divider()
        st.markdown("#### Lista")
        df = safe_query(
            """
            select o.id, o.titulo, o.status, c.nome as cliente, o.criado_em
            from public.obras o
            join public.clientes c on c.id=o.cliente_id
            order by o.id desc
            limit 200;
            """
        )
        if df.empty:
            st.info("Nenhuma obra cadastrada.")
        else:
            for _, rr in df.iterrows():
                colA, colB, colC, colD = st.columns([5,2,3,2])
                with colA:
                    st.write(f"**{rr['titulo']}**")
                    st.caption(rr["cliente"])
                with colB:
                    st.write(rr["status"])
                with colC:
                    st.write(str(rr["criado_em"])[:19])
                with colD:
                    if st.button("Editar", key=f"o_edit_{int(rr['id'])}"):
                        set_edit("edit_obra_id", int(rr["id"]))
                        st.rerun()

# =========================
# APONTAMENTOS (editar/excluir por linha + trava pago)
# =========================
if menu == "Apontamentos":
    st.subheader("Apontamentos (lançar trabalho)")
    st.caption("Regra: 1 apontamento por pessoa, por dia, por obra. Se errar: edite ou exclua.")

    df_pessoas = safe_query("select id,nome from public.pessoas where ativo=true order by nome;")
    df_obras = safe_query("select id,titulo from public.obras order by id desc;")

    if df_pessoas.empty or df_obras.empty:
        st.info("Cadastre pelo menos 1 pessoa e 1 obra em Cadastros.")
        st.stop()

    if "edit_ap_id" not in st.session_state:
        st.session_state["edit_ap_id"] = None
    if "confirm_del_ap_id" not in st.session_state:
        st.session_state["confirm_del_ap_id"] = None

    edit_id = st.session_state["edit_ap_id"]
    row = None
    if edit_id:
        df_one = safe_query("select * from public.apontamentos where id=%s;", (edit_id,))
        if not df_one.empty:
            row = df_one.iloc[0]
        else:
            st.session_state["edit_ap_id"] = None
            edit_id = None

    # trava se já foi pago
    travado_pago = False
    if edit_id:
        df_lock = safe_query(
            """
            select exists (
              select 1
              from public.pagamento_itens pi
              join public.pagamentos p on p.id = pi.pagamento_id
              where pi.apontamento_id=%s and p.status='PAGO'
            ) as travado;
            """,
            (edit_id,),
        )
        travado_pago = bool(df_lock.iloc[0]["travado"])

    st.markdown("### " + ("Editar apontamento" if edit_id else "Novo apontamento"))

    # inputs
    obra_ids = df_obras["id"].tolist()
    pessoa_ids = df_pessoas["id"].tolist()

    obra_default = int(row["obra_id"]) if row is not None else obra_ids[0]
    pessoa_default = int(row["pessoa_id"]) if row is not None else pessoa_ids[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        obra_id = st.selectbox(
            "Obra", obra_ids, index=(obra_ids.index(obra_default) if obra_default in obra_ids else 0),
            format_func=lambda x: df_obras.loc[df_obras["id"]==x, "titulo"].iloc[0],
            key="ap_obra"
        )
    with c2:
        pessoa_id = st.selectbox(
            "Pessoa", pessoa_ids, index=(pessoa_ids.index(pessoa_default) if pessoa_default in pessoa_ids else 0),
            format_func=lambda x: df_pessoas.loc[df_pessoas["id"]==x, "nome"].iloc[0],
            key="ap_pessoa"
        )
    with c3:
        data_ap = st.date_input("Data", value=(row["data"] if row is not None else date.today()), key="ap_data")

    df_fases = safe_query("select id,ordem,nome_fase from public.obra_fases where obra_id=%s order by ordem;", (obra_id,))
    obra_fase_id = None
    if not df_fases.empty:
        opts = [None] + df_fases["id"].tolist()
        default = int(row["obra_fase_id"]) if (row is not None and pd.notna(row["obra_fase_id"])) else None
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
        tipo_opts = ["NORMAL","FERIADO","SABADO","DOMINGO"]
        tipo_dia = st.selectbox(
            "Tipo do dia", tipo_opts,
            index=(tipo_opts.index(row["tipo_dia"]) if row is not None else 0),
            key="ap_tipo"
        )
    with c2:
        valor_base = st.number_input("Valor base (R$)", min_value=0.0, step=10.0,
                                     value=(float(row["valor_base"]) if row is not None else 0.0), key="ap_vb")
    with c3:
        desconto = st.number_input("Desconto (R$)", min_value=0.0, step=10.0,
                                   value=(float(row["desconto_valor"]) if row is not None else 0.0), key="ap_desc")
    with c4:
        obs = st.text_input("Observação", value=(row["observacao"] or "" if row is not None else ""), key="ap_obs")

    b1, b2, b3 = st.columns(3)
    with b1:
        if not edit_id:
            if st.button("Salvar apontamento", type="primary", use_container_width=True):
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
        else:
            if st.button("Salvar alteração", type="primary", use_container_width=True, disabled=travado_pago):
                try:
                    exec_sql(
                        """
                        update public.apontamentos
                        set obra_id=%s, obra_fase_id=%s, pessoa_id=%s, data=%s, tipo_dia=%s,
                            valor_base=%s, desconto_valor=%s, observacao=%s
                        where id=%s;
                        """,
                        (obra_id, obra_fase_id, pessoa_id, data_ap, tipo_dia, valor_base, desconto, obs.strip() or None, int(edit_id)),
                    )
                    st.success("Atualizado! Se já gerou pagamentos, clique em Gerar Pagamentos novamente.")
                    st.session_state["edit_ap_id"] = None
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    st.warning("Conflito: já existe apontamento para essa pessoa nesse dia nessa obra.")
                    st.stop()

    with b2:
        if edit_id:
            if st.button("Excluir", use_container_width=True, disabled=travado_pago):
                st.session_state["confirm_del_ap_id"] = int(edit_id)

    with b3:
        if edit_id:
            if st.button("Cancelar edição", use_container_width=True):
                st.session_state["edit_ap_id"] = None
                st.session_state["confirm_del_ap_id"] = None
                st.rerun()

    if edit_id and travado_pago:
        st.warning("Este apontamento está ligado a pagamento PAGO. Não pode editar nem excluir.")

    if st.session_state["confirm_del_ap_id"] == edit_id and edit_id is not None:
        st.error("Confirma excluir este apontamento?")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("SIM, excluir", type="primary", use_container_width=True):
                exec_sql("delete from public.pagamento_itens where apontamento_id=%s;", (int(edit_id),))
                exec_sql("delete from public.apontamentos where id=%s;", (int(edit_id),))
                st.success("Apontamento excluído!")
                st.session_state["edit_ap_id"] = None
                st.session_state["confirm_del_ap_id"] = None
                st.rerun()
        with cc2:
            if st.button("NÃO", use_container_width=True):
                st.session_state["confirm_del_ap_id"] = None
                st.rerun()

    st.divider()
    st.markdown("### Apontamentos recentes (editar/excluir)")

    df_recent = safe_query(
        """
        select
          a.id, a.data,
          p.nome as pessoa,
          o.titulo as obra,
          a.tipo_dia, a.valor_base, a.desconto_valor, a.valor_final,
          exists (
            select 1
            from public.pagamento_itens pi
            join public.pagamentos pg on pg.id=pi.pagamento_id
            where pi.apontamento_id=a.id and pg.status='PAGO'
          ) as travado_pago
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
            colA, colB, colC, colD, colE, colF = st.columns([2,4,2,2,2,2])
            with colA:
                st.write(f"**{rr['data']}**")
                st.caption(rr["pessoa"])
            with colB:
                st.write(rr["obra"])
                if rr["travado_pago"]:
                    st.caption("🔒 pago")
            with colC:
                st.write(rr["tipo_dia"])
            with colD:
                st.write(brl(rr["valor_final"]))
            with colE:
                if st.button("Editar", key=f"ap_edit_{int(rr['id'])}", disabled=bool(rr["travado_pago"])):
                    st.session_state["edit_ap_id"] = int(rr["id"])
                    st.session_state["confirm_del_ap_id"] = None
                    st.rerun()
            with colF:
                if st.button("Excluir", key=f"ap_del_{int(rr['id'])}", disabled=bool(rr["travado_pago"])):
                    st.session_state["edit_ap_id"] = int(rr["id"])
                    st.session_state["confirm_del_ap_id"] = int(rr["id"])
                    st.rerun()

# =========================
# GERAR PAGAMENTOS
# =========================
if menu == "Gerar Pagamentos":
    st.subheader("Gerar Pagamentos")
    segunda = st.date_input("Segunda-feira da semana", value=monday_of_week(date.today()))
    sexta = segunda + timedelta(days=4)
    st.info(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")

    if st.button("Gerar pagamentos desta semana", type="primary", use_container_width=True):
        exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
        st.success("Pagamentos gerados/atualizados!")
        st.rerun()

    st.divider()
    st.markdown("### Pagamentos pendentes (abertos)")
    df = safe_query("select * from public.pagamentos_pendentes limit 200;")
    st.dataframe(df, use_container_width=True, hide_index=True)

# =========================
# PAGAR
# =========================
if menu == "Pagar":
    st.subheader("Pagar (modo simples)")
    data_pg = st.date_input("Data do pagamento", value=date.today())

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
    df_pago = safe_query("select * from public.pagamentos_pagos_30d limit 200;")
    st.dataframe(df_pago, use_container_width=True, hide_index=True)
