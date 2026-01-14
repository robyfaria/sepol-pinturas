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
# Navegação segura
# =========================
def nav(destino: str):
    st.session_state["menu"] = destino

# =========================
# Mini-framework CRUD
# =========================
def ss_get(key, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]

def ss_set(key, value):
    st.session_state[key] = value

def crud_begin(entity_key: str):
    ss_get(f"{entity_key}_edit_id", None)
    ss_get(f"{entity_key}_confirm_toggle_id", None)

def crud_set_edit(entity_key: str, rid: int | None):
    ss_set(f"{entity_key}_edit_id", rid)

def crud_get_edit(entity_key: str):
    return ss_get(f"{entity_key}_edit_id", None)

def crud_clear_edit(entity_key: str):
    ss_set(f"{entity_key}_edit_id", None)

def crud_toggle_confirm(entity_key: str, rid: int | None):
    ss_set(f"{entity_key}_confirm_toggle_id", rid)

def crud_get_toggle_confirm(entity_key: str):
    return ss_get(f"{entity_key}_confirm_toggle_id", None)

def crud_clear_toggle_confirm(entity_key: str):
    ss_set(f"{entity_key}_confirm_toggle_id", None)

def crud_soft_toggle(table: str, id_value: int, new_ativo: bool):
    exec_sql(f"update public.{table} set ativo=%s where id=%s;", (new_ativo, id_value))

def crud_fetch_one(table: str, rid: int):
    df = safe_query(f"select * from public.{table} where id=%s;", (rid,))
    return df.iloc[0] if not df.empty else None

def crud_form_title(is_edit: bool, label: str):
    st.markdown(f"#### {'Editar' if is_edit else 'Novo'} {label}")

def crud_actions_row(entity_key: str, is_edit: bool, save_label: str = "Salvar", update_label: str = "Salvar alteração"):
    c1, c2 = st.columns(2)
    with c2:
        if is_edit:
            if st.button("Cancelar edição", use_container_width=True, key=f"{entity_key}_cancel"):
                crud_clear_edit(entity_key)
                st.rerun()
    return c1, c2

def list_rows_simple(df: pd.DataFrame, entity_key: str, cols, render_left, can_edit_fn=None, on_edit=None, on_toggle=None):
    """
    cols: lista de colunas Streamlit com pesos.
    render_left(rr, cols): escreve o conteúdo
    can_edit_fn(rr)->bool
    on_edit(id): callback
    on_toggle(id, ativo)->callback
    """
    for _, rr in df.iterrows():
        columns = st.columns(cols)
        render_left(rr, columns)

        rid = int(rr["id"])
        ativo = bool(rr["ativo"]) if "ativo" in rr else True
        can_edit = True if can_edit_fn is None else bool(can_edit_fn(rr))

        # Botões sempre no final
        # (colunas finais 2)
        btn_col_edit = columns[-2]
        btn_col_toggle = columns[-1]

        with btn_col_edit:
            if on_edit:
                if st.button("Editar", key=f"{entity_key}_edit_{rid}", disabled=not (ativo and can_edit), use_container_width=True):
                    on_edit(rid)

        with btn_col_toggle:
            if on_toggle and "ativo" in rr:
                if ativo:
                    if st.button("Inativar", key=f"{entity_key}_inat_{rid}", use_container_width=True):
                        on_toggle(rid, False)
                else:
                    if st.button("Ativar", key=f"{entity_key}_at_{rid}", use_container_width=True):
                        on_toggle(rid, True)

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
        st.markdown(f"### {badge(qtd_ap_hoje > 0)} 1) Lançar apontamentos")
        st.caption(f"Apontamentos hoje: {qtd_ap_hoje}")
        st.button("Ir para Apontamentos", on_click=nav, args=("Apontamentos",), type="primary", use_container_width=True)

    with colL2:
        st.markdown(f"### {badge(qtd_pg_sem > 0)} 2) Gerar pagamentos")
        st.caption(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")
        st.button("Ir para Gerar Pagamentos", on_click=nav, args=("Gerar Pagamentos",), use_container_width=True)

    with colR1:
        st.markdown(f"### {badge(qtd_para_sexta == 0)} 3) Pagar na sexta")
        st.caption(f"Pendências para sexta: {qtd_para_sexta}")
        st.button("Ir para Pagar", on_click=nav, args=("Pagar",), use_container_width=True)

    with colR2:
        st.markdown(f"### {badge(qtd_extras == 0)} 4) Extras (sáb/dom)")
        st.caption(f"Extras pendentes: {qtd_extras}")
        st.button("Ir para Pagar (extras)", on_click=nav, args=("Pagar",), use_container_width=True)

# =========================
# CADASTROS (padronizados)
# =========================
if menu == "Cadastros":
    st.subheader("Cadastros")
    tabs = st.tabs(["Indicações", "Pessoas", "Clientes", "Obras"])

    # ---------- INDICAÇÕES ----------
    with tabs[0]:
        entity = "ind"
        crud_begin(entity)

        edit_id = crud_get_edit(entity)
        row = crud_fetch_one("indicacoes", edit_id) if edit_id else None

        crud_form_title(bool(edit_id), "Indicação")

        c1, c2, c3 = st.columns(3)
        with c1:
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""), key=f"{entity}_nome")
        with c2:
            tipo = st.selectbox(
                "Tipo",
                ["ARQUITETO", "ENGENHEIRO", "LOJA", "OUTRO"],
                index=(["ARQUITETO","ENGENHEIRO","LOJA","OUTRO"].index(row["tipo"]) if row is not None else 0),
                key=f"{entity}_tipo"
            )
        with c3:
            tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row is not None else ""), key=f"{entity}_tel")

        bsave, _ = crud_actions_row(entity, bool(edit_id))
        with bsave:
            if st.button("Salvar" if not edit_id else "Salvar alteração", type="primary", use_container_width=True, key=f"{entity}_save"):
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if not edit_id:
                    exec_sql(
                        "insert into public.indicacoes (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                        (nome.strip(), tipo, tel.strip() or None),
                    )
                    st.success("Indicação cadastrada!")
                else:
                    exec_sql(
                        "update public.indicacoes set nome=%s, tipo=%s, telefone=%s where id=%s;",
                        (nome.strip(), tipo, tel.strip() or None, int(edit_id)),
                    )
                    st.success("Indicação atualizada!")
                    crud_clear_edit(entity)
                st.rerun()

        st.divider()
        st.markdown("#### Lista")

        df = safe_query("select id, nome, tipo, telefone, ativo, criado_em from public.indicacoes order by nome;")

        def render(rr, cols):
            with cols[0]:
                st.write(f"**{rr['nome']}**")
                st.caption(rr["tipo"])
            with cols[1]:
                st.write(rr["telefone"] or "")
            with cols[2]:
                st.write("ATIVO" if rr["ativo"] else "INATIVO")

        list_rows_simple(
            df=df,
            entity_key=entity,
            cols=[4, 2, 2, 2, 2],  # 3 conteúdo + editar + toggle
            render_left=render,
            on_edit=lambda rid: (crud_set_edit(entity, rid), st.rerun()),
            on_toggle=lambda rid, ativo: (crud_soft_toggle("indicacoes", rid, ativo), st.rerun()),
        )

    # ---------- PESSOAS ----------
    with tabs[1]:
        entity = "pes"
        crud_begin(entity)

        edit_id = crud_get_edit(entity)
        row = crud_fetch_one("pessoas", edit_id) if edit_id else None

        crud_form_title(bool(edit_id), "Pessoa")

        c1, c2, c3 = st.columns(3)
        with c1:
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""), key=f"{entity}_nome")
        with c2:
            tipo = st.selectbox(
                "Tipo",
                ["PINTOR", "AJUDANTE", "TERCEIRO"],
                index=(["PINTOR","AJUDANTE","TERCEIRO"].index(row["tipo"]) if row is not None else 0),
                key=f"{entity}_tipo"
            )
        with c3:
            tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row is not None else ""), key=f"{entity}_tel")

        bsave, _ = crud_actions_row(entity, bool(edit_id))
        with bsave:
            if st.button("Salvar" if not edit_id else "Salvar alteração", type="primary", use_container_width=True, key=f"{entity}_save"):
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if not edit_id:
                    exec_sql(
                        "insert into public.pessoas (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                        (nome.strip(), tipo, tel.strip() or None),
                    )
                    st.success("Pessoa cadastrada!")
                else:
                    exec_sql(
                        "update public.pessoas set nome=%s, tipo=%s, telefone=%s where id=%s;",
                        (nome.strip(), tipo, tel.strip() or None, int(edit_id)),
                    )
                    st.success("Pessoa atualizada!")
                    crud_clear_edit(entity)
                st.rerun()

        st.divider()
        st.markdown("#### Lista")

        df = safe_query("select id, nome, tipo, telefone, ativo, criado_em from public.pessoas order by nome;")

        def render(rr, cols):
            with cols[0]:
                st.write(f"**{rr['nome']}**")
                st.caption(rr["tipo"])
            with cols[1]:
                st.write(rr["telefone"] or "")
            with cols[2]:
                st.write("ATIVO" if rr["ativo"] else "INATIVO")

        list_rows_simple(
            df=df,
            entity_key=entity,
            cols=[4, 2, 2, 2, 2],
            render_left=render,
            on_edit=lambda rid: (crud_set_edit(entity, rid), st.rerun()),
            on_toggle=lambda rid, ativo: (crud_soft_toggle("pessoas", rid, ativo), st.rerun()),
        )

    # ---------- CLIENTES ----------
    with tabs[2]:
        entity = "cli"
        crud_begin(entity)

        edit_id = crud_get_edit(entity)
        row = crud_fetch_one("clientes", edit_id) if edit_id else None

        df_ind = safe_query("select id, nome from public.indicacoes where ativo=true order by nome;")

        crud_form_title(bool(edit_id), "Cliente")

        c1, c2, c3 = st.columns(3)
        with c1:
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""), key=f"{entity}_nome")
        with c2:
            tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row is not None else ""), key=f"{entity}_tel")
        with c3:
            end = st.text_input("Endereço (opcional)", value=(row["endereco"] or "" if row is not None else ""), key=f"{entity}_end")

        origem = st.selectbox(
            "Origem",
            ["PROPRIO", "INDICADO"],
            index=(["PROPRIO","INDICADO"].index(row["origem"]) if row is not None else 0),
            key=f"{entity}_origem"
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
                key=f"{entity}_ind"
            )

        bsave, _ = crud_actions_row(entity, bool(edit_id))
        with bsave:
            if st.button("Salvar" if not edit_id else "Salvar alteração", type="primary", use_container_width=True, key=f"{entity}_save"):
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if origem == "INDICADO" and not indicacao_id:
                    st.warning("Selecione quem indicou.")
                    st.stop()

                if not edit_id:
                    exec_sql(
                        "insert into public.clientes (nome,telefone,endereco,origem,indicacao_id,ativo) values (%s,%s,%s,%s,%s,true);",
                        (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicacao_id),
                    )
                    st.success("Cliente cadastrado!")
                else:
                    exec_sql(
                        "update public.clientes set nome=%s, telefone=%s, endereco=%s, origem=%s, indicacao_id=%s where id=%s;",
                        (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicacao_id, int(edit_id)),
                    )
                    st.success("Cliente atualizado!")
                    crud_clear_edit(entity)
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

        def render(rr, cols):
            with cols[0]:
                st.write(f"**{rr['nome']}**")
            with cols[1]:
                st.write(rr["telefone"] or "")
            with cols[2]:
                st.write(rr["origem"])
            with cols[3]:
                st.write(rr["indicacao_nome"] or "")
            with cols[4]:
                st.write("ATIVO" if rr["ativo"] else "INATIVO")

        list_rows_simple(
            df=df,
            entity_key=entity,
            cols=[4, 2, 2, 3, 2, 2, 2],  # 5 conteúdo + editar + toggle
            render_left=render,
            on_edit=lambda rid: (crud_set_edit(entity, rid), st.rerun()),
            on_toggle=lambda rid, ativo: (crud_soft_toggle("clientes", rid, ativo), st.rerun()),
        )

    # ---------- OBRAS ----------
    with tabs[3]:
        entity = "obr"
        crud_begin(entity)

        edit_id = crud_get_edit(entity)
        row = crud_fetch_one("obras", edit_id) if edit_id else None

        df_cli = safe_query("select id, nome from public.clientes where ativo=true order by nome;")
        if df_cli.empty:
            st.info("Cadastre um cliente ativo primeiro.")
        else:
            crud_form_title(bool(edit_id), "Obra")

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
                    key=f"{entity}_cli"
                )
            with c2:
                titulo = st.text_input("Título da obra", value=(row["titulo"] if row is not None else ""), key=f"{entity}_tit")
            with c3:
                status = st.selectbox(
                    "Status",
                    ["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"],
                    index=(["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"].index(row["status"]) if row is not None else 0),
                    key=f"{entity}_status"
                )
            end = st.text_input("Endereço da obra (opcional)", value=(row["endereco_obra"] or "" if row is not None else ""), key=f"{entity}_end")

            bsave, _ = crud_actions_row(entity, bool(edit_id))
            with bsave:
                if st.button("Salvar" if not edit_id else "Salvar alteração", type="primary", use_container_width=True, key=f"{entity}_save"):
                    if not titulo.strip():
                        st.warning("Informe o título.")
                        st.stop()
                    if not edit_id:
                        exec_sql(
                            "insert into public.obras (cliente_id,titulo,endereco_obra,status,ativo) values (%s,%s,%s,%s,true);",
                            (cliente_id, titulo.strip(), end.strip() or None, status),
                        )
                        st.success("Obra cadastrada!")
                    else:
                        exec_sql(
                            "update public.obras set cliente_id=%s, titulo=%s, endereco_obra=%s, status=%s where id=%s;",
                            (cliente_id, titulo.strip(), end.strip() or None, status, int(edit_id)),
                        )
                        st.success("Obra atualizada!")
                        crud_clear_edit(entity)
                    st.rerun()

        st.divider()
        st.markdown("#### Lista")
        df = safe_query(
            """
            select o.id, o.titulo, o.status, o.ativo, c.nome as cliente, o.criado_em
            from public.obras o
            join public.clientes c on c.id=o.cliente_id
            order by o.id desc
            limit 200;
            """
        )

        def render(rr, cols):
            with cols[0]:
                st.write(f"**{rr['titulo']}**")
                st.caption(rr["cliente"])
            with cols[1]:
                st.write(rr["status"])
            with cols[2]:
                st.write("ATIVO" if rr["ativo"] else "INATIVO")

        list_rows_simple(
            df=df,
            entity_key=entity,
            cols=[5, 2, 2, 2, 2],
            render_left=render,
            on_edit=lambda rid: (crud_set_edit(entity, rid), st.rerun()),
            on_toggle=lambda rid, ativo: (crud_soft_toggle("obras", rid, ativo), st.rerun()),
        )

# =========================
# APONTAMENTOS
# =========================
if menu == "Apontamentos":
    st.subheader("Apontamentos (lançar trabalho)")
    st.caption("Regra: 1 apontamento por pessoa, por dia, por obra. Se errar: edite ou exclua.")

    df_pessoas = safe_query("select id,nome from public.pessoas where ativo=true order by nome;")
    df_obras = safe_query("select id,titulo from public.obras where ativo=true order by id desc;")

    if df_pessoas.empty or df_obras.empty:
        st.info("Cadastre pelo menos 1 pessoa ativa e 1 obra ativa em Cadastros.")
        st.stop()

    ss_get("edit_ap_id", None)
    ss_get("confirm_del_ap_id", None)
    ss_get("recalc_week_date", None)  # para sugerir recalcular

    edit_id = st.session_state["edit_ap_id"]
    row = None
    if edit_id:
        df_one = safe_query("select * from public.apontamentos where id=%s;", (edit_id,))
        if not df_one.empty:
            row = df_one.iloc[0]
        else:
            st.session_state["edit_ap_id"] = None
            edit_id = None

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
            if st.button("Salvar apontamento", type="primary", use_container_width=True, key="ap_save"):
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
            if st.button("Salvar alteração", type="primary", use_container_width=True, disabled=travado_pago, key="ap_update"):
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
                    st.success("Atualizado! Recomendo recalcular pagamentos da semana.")
                    st.session_state["recalc_week_date"] = data_ap
                    st.session_state["edit_ap_id"] = None
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    st.warning("Conflito: já existe apontamento para essa pessoa nesse dia nessa obra.")
                    st.stop()

    with b2:
        if edit_id:
            if st.button("Excluir", use_container_width=True, disabled=travado_pago, key="ap_delete"):
                st.session_state["confirm_del_ap_id"] = int(edit_id)

    with b3:
        if edit_id:
            if st.button("Cancelar edição", use_container_width=True, key="ap_cancel"):
                st.session_state["edit_ap_id"] = None
                st.session_state["confirm_del_ap_id"] = None
                st.rerun()

    if edit_id and travado_pago:
        st.warning("Este apontamento está ligado a pagamento PAGO. Não pode editar nem excluir.")

    if st.session_state["confirm_del_ap_id"] == edit_id and edit_id is not None:
        st.error("Confirma excluir este apontamento?")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("SIM, excluir", type="primary", use_container_width=True, key="ap_delete_yes"):
                exec_sql("delete from public.pagamento_itens where apontamento_id=%s;", (int(edit_id),))
                exec_sql("delete from public.apontamentos where id=%s;", (int(edit_id),))
                st.success("Apontamento excluído! Recomendo recalcular pagamentos da semana.")
                st.session_state["recalc_week_date"] = row["data"] if row is not None else None
                st.session_state["edit_ap_id"] = None
                st.session_state["confirm_del_ap_id"] = None
                st.rerun()
        with cc2:
            if st.button("NÃO", use_container_width=True, key="ap_delete_no"):
                st.session_state["confirm_del_ap_id"] = None
                st.rerun()

    # Botão de recalcular semana (após edit/excluir)
    if st.session_state.get("recalc_week_date"):
        dref = st.session_state["recalc_week_date"]
        seg = monday_of_week(dref)
        sex = seg + timedelta(days=4)
        st.info(f"Recalcular pagamentos da semana: {seg.strftime('%d/%m/%Y')} → {sex.strftime('%d/%m/%Y')}")
        if st.button("Recalcular semana agora", type="primary", use_container_width=True, key="ap_recalc_week"):
            exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (seg,))
            st.success("Semana recalculada!")
            st.session_state["recalc_week_date"] = None
            st.rerun()

    st.divider()
    st.markdown("### Apontamentos recentes (editar/excluir)")

    df_recent = safe_query(
        """
        select
          a.id, a.data,
          p.nome as pessoa,
          o.titulo as obra,
          a.tipo_dia, a.valor_final,
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
            rid = int(rr["id"])
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
                if st.button("Editar", key=f"ap_edit_{rid}", disabled=bool(rr["travado_pago"])):
                    st.session_state["edit_ap_id"] = rid
                    st.session_state["confirm_del_ap_id"] = None
                    st.rerun()
            with colF:
                if st.button("Excluir", key=f"ap_del_{rid}", disabled=bool(rr["travado_pago"])):
                    st.session_state["edit_ap_id"] = rid
                    st.session_state["confirm_del_ap_id"] = rid
                    st.rerun()

# =========================
# GERAR PAGAMENTOS
# =========================
if menu == "Gerar Pagamentos":
    st.subheader("Gerar Pagamentos")
    segunda = st.date_input("Segunda-feira da semana", value=monday_of_week(date.today()), key="gp_seg")
    sexta = segunda + timedelta(days=4)
    st.info(f"Semana: {segunda.strftime('%d/%m/%Y')} → {sexta.strftime('%d/%m/%Y')}")

    if st.button("Gerar/Atualizar pagamentos desta semana", type="primary", use_container_width=True, key="gp_run"):
        exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
        st.success("Pagamentos gerados/atualizados!")
        st.rerun()

    st.divider()
    st.markdown("### Pagamentos pendentes (abertos)")
    df = safe_query("select * from public.pagamentos_pendentes limit 200;")
    st.dataframe(df, use_container_width=True, hide_index=True)

# =========================
# PAGAR + HISTÓRICO + ESTORNO
# =========================
if menu == "Pagar":
    st.subheader("Pagar (modo simples)")
    data_pg = st.date_input("Data do pagamento", value=date.today(), key="pay_date")

    # -------- PENDENTES PARA SEXTA --------
    st.markdown("### Pagar na próxima sexta")
    df_sexta = safe_query("select * from public.pagamentos_para_sexta;")
    if df_sexta.empty:
        st.info("Nada para pagar na próxima sexta.")
    else:
        for _, r in df_sexta.iterrows():
            rid = int(r["id"])
            col1, col2, col3, col4 = st.columns([5, 2, 2, 2])
            with col1:
                st.write(f"**{r['pessoa_nome']}**  •  {r['tipo']}")
            with col2:
                st.write(brl(r["valor_total"]))
            with col3:
                st.write(f"sexta: {r.get('sexta')}")
            with col4:
                if st.button("Pagar", type="primary", key=f"pay_{rid}"):
                    exec_sql("select public.fn_marcar_pagamento_pago(%s,%s,%s);", (rid, usuario, data_pg))
                    st.success(f"Pago! {r['pessoa_nome']}")
                    st.rerun()

    # -------- EXTRAS PENDENTES --------
    st.divider()
    st.markdown("### Extras pendentes (sábado/domingo)")
    df_extras = safe_query("select * from public.pagamentos_extras_pendentes;")
    if df_extras.empty:
        st.info("Sem extras pendentes.")
    else:
        for _, r in df_extras.iterrows():
            rid = int(r["id"])
            col1, col2, col3, col4 = st.columns([5, 2, 2, 2])
            with col1:
                st.write(f"**{r['pessoa_nome']}**  •  EXTRA")
            with col2:
                st.write(brl(r["valor_total"]))
            with col3:
                st.write(f"data: {r.get('data_extra')}")
            with col4:
                if st.button("Pagar", type="primary", key=f"pay_extra_{rid}"):
                    exec_sql("select public.fn_marcar_pagamento_pago(%s,%s,%s);", (rid, usuario, data_pg))
                    st.success(f"Pago extra! {r['pessoa_nome']}")
                    st.rerun()

    # -------- HISTÓRICO / ESTORNO --------
    st.divider()
    st.markdown("### Histórico (por pessoa) + Estorno")

    df_pessoas = safe_query("select id, nome from public.pessoas order by nome;")
    pessoa_id = None
    if not df_pessoas.empty:
        pessoa_id = st.selectbox(
            "Pessoa",
            options=[None] + df_pessoas["id"].tolist(),
            format_func=lambda x: "Todas" if x is None else df_pessoas.loc[df_pessoas["id"]==x,"nome"].iloc[0],
            key="hist_pessoa"
        )

    periodo = st.selectbox("Período", ["7 dias", "30 dias", "90 dias", "Tudo"], index=1, key="hist_periodo")
    tipo = st.selectbox("Tipo", ["Todos", "SEMANAL", "EXTRA", "POR_FASE"], index=0, key="hist_tipo")

    days = None
    if periodo == "7 dias":
        days = 7
    elif periodo == "30 dias":
        days = 30
    elif periodo == "90 dias":
        days = 90

    where = ["1=1"]
    params = []

    if pessoa_id is not None:
        where.append("p.pessoa_id=%s")
        params.append(int(pessoa_id))

    if tipo != "Todos":
        where.append("p.tipo=%s")
        params.append(tipo)

    if days is not None:
        where.append("p.criado_em >= (now() - interval '%s days')" )
        params.append(days)

    sql_hist = f"""
        select
          p.id,
          pe.nome as pessoa_nome,
          p.tipo,
          p.status,
          p.valor_total,
          p.referencia_inicio,
          p.referencia_fim,
          p.pago_em,
          p.criado_em
        from public.pagamentos p
        join public.pessoas pe on pe.id=p.pessoa_id
        where {" and ".join(where)}
        order by p.id desc
        limit 200;
    """

    df_hist = safe_query(sql_hist, tuple(params) if params else None)
    if df_hist.empty:
        st.info("Sem pagamentos nesse filtro.")
    else:
        # Estorno: confirmação
        ss_get("estorno_id", None)

        for _, r in df_hist.iterrows():
            rid = int(r["id"])
            status = r["status"]
            colA, colB, colC, colD, colE, colF = st.columns([4,2,2,2,2,2])
            with colA:
                st.write(f"**{r['pessoa_nome']}** • {r['tipo']} • {status}")
                st.caption(f"Ref: {r['referencia_inicio']} → {r['referencia_fim']} | pago_em: {r['pago_em']}")
            with colB:
                st.write(brl(r["valor_total"]))
            with colC:
                st.write(str(r["criado_em"])[:19])
            with colD:
                if status == "ABERTO":
                    st.write("—")
                else:
                    st.write("PAGO")
            with colE:
                # Ação rápida: Reabrir como ABERTO via estorno
                if status == "PAGO":
                    if st.button("Estornar", key=f"estornar_{rid}", use_container_width=True):
                        st.session_state["estorno_id"] = rid
                        st.rerun()
                else:
                    st.write("—")
            with colF:
                st.write("")

        # Modal simples de estorno
        if st.session_state.get("estorno_id"):
            pid = int(st.session_state["estorno_id"])
            st.error(f"CONFIRMAR ESTORNO do pagamento #{pid}?")
            motivo = st.text_input("Motivo do estorno (obrigatório)", key="estorno_motivo")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("SIM, estornar", type="primary", use_container_width=True, key="estorno_yes"):
                    if not motivo.strip():
                        st.warning("Informe o motivo do estorno.")
                        st.stop()
                    exec_sql("select public.fn_estornar_pagamento(%s,%s,%s);", (pid, usuario, motivo.strip()))
                    st.success("Pagamento estornado! Ele voltou para ABERTO.")
                    st.session_state["estorno_id"] = None
                    st.rerun()
            with c2:
                if st.button("NÃO", use_container_width=True, key="estorno_no"):
                    st.session_state["estorno_id"] = None
                    st.rerun()
