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
# PROFISSIONAIS (estável: form + modo edição)
# ======================================================
if menu == "PROFISSIONAIS":
    st.subheader("👷 Profissionais")

    if "edit_prof" not in st.session_state:
        st.session_state["edit_prof"] = None  # id em edição

    edit_id = st.session_state["edit_prof"]

    # ---------- FORM: NOVO ----------
    if edit_id is None:
        st.markdown("### ➕ Novo profissional")

        with st.form("form_prof_novo", clear_on_submit=True):
            nome = st.text_input("Nome")
            tipo = st.selectbox("Tipo", ["PINTOR", "AJUDANTE", "TERCEIRO"], index=0)
            tel = st.text_input("Telefone (opcional)")

            col1, col2 = st.columns([2, 1])
            with col1:
                salvar = st.form_submit_button("Salvar", type="primary", use_container_width=True)
            with col2:
                st.write("")  # espaçador

            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()

                exec_sql(
                    "insert into public.pessoas (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                    (nome.strip(), tipo, tel.strip() or None),
                )
                st.success("Profissional cadastrado.")
                st.rerun()

    # ---------- FORM: EDITAR ----------
    else:
        st.markdown("### ✏️ Editar profissional")

        df_one = safe_df("select * from public.pessoas where id=%s;", (int(edit_id),))
        if df_one.empty:
            st.session_state["edit_prof"] = None
            st.rerun()
        r = df_one.iloc[0]

        with st.form("form_prof_edit", clear_on_submit=False):
            nome = st.text_input("Nome", value=r["nome"], key="p_nome_edit")
            tipo = st.selectbox(
                "Tipo",
                ["PINTOR", "AJUDANTE", "TERCEIRO"],
                index=["PINTOR", "AJUDANTE", "TERCEIRO"].index(r["tipo"]),
                key="p_tipo_edit",
            )
            tel = st.text_input("Telefone (opcional)", value=r["telefone"] or "", key="p_tel_edit")

            c1, c2 = st.columns(2)
            with c1:
                salvar_alt = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
            with c2:
                cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)

            if salvar_alt:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()

                exec_sql(
                    "update public.pessoas set nome=%s, tipo=%s, telefone=%s where id=%s;",
                    (nome.strip(), tipo, tel.strip() or None, int(edit_id)),
                )
                st.success("Profissional atualizado.")
                st.session_state["edit_prof"] = None
                # Não mexe em session_state dos widgets aqui; apenas rerun
                st.rerun()

            if cancelar:
                st.session_state["edit_prof"] = None
                st.rerun()

    st.divider()

    # ---------- LISTA ----------
    st.markdown("### 📋 Lista")
    df = safe_df("select id, nome, tipo, telefone, ativo from public.pessoas order by nome;")

    if df.empty:
        st.info("Nenhum profissional cadastrado.")
    else:
        for _, rr in df.iterrows():
            colA, colB, colC = st.columns([6, 2, 2])

            with colA:
                st.write(f"**{rr['nome']}** — {rr['tipo']}")
                if rr["telefone"]:
                    st.caption(rr["telefone"])

            with colB:
                st.write("ATIVO ✅" if rr["ativo"] else "INATIVO ⛔")

            with colC:
                b1, b2 = st.columns(2)  # lado a lado
                with b1:
                    if st.button("Editar", key=f"p_edit_{int(rr['id'])}", use_container_width=True):
                        st.session_state["edit_prof"] = int(rr["id"])
                        st.rerun()
                with b2:
                    if rr["ativo"]:
                        if st.button("INATIVAR ⛔", key=f"p_inat_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.pessoas set ativo=false where id=%s;", (int(rr["id"]),))
                            st.rerun()
                    else:
                        if st.button("ATIVAR ✅", key=f"p_at_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.pessoas set ativo=true where id=%s;", (int(rr["id"]),))
                            st.rerun()

# ======================================================
# CLIENTES + INDICAÇÕES (estável: form + modo edição)
# ======================================================
if menu == "CLIENTES":
    st.subheader("👥 Clientes & Indicações")

    if "edit_cliente" not in st.session_state:
        st.session_state["edit_cliente"] = None  # id cliente em edição
    if "edit_ind" not in st.session_state:
        st.session_state["edit_ind"] = None  # id indicação em edição

    # -------------------------
    # INDICAÇÕES
    # -------------------------
    st.markdown("## Indicações (quem indicou)")

    edit_ind_id = st.session_state["edit_ind"]

    if edit_ind_id is None:
        with st.form("form_ind_novo", clear_on_submit=True):
            c1, c2, c3 = st.columns([4, 2, 2])
            with c1:
                nome = st.text_input("Nome da indicação")
            with c2:
                tipo = st.selectbox("Tipo", ["ARQUITETO", "ENGENHEIRO", "LOJA", "OUTRO"], index=0)
            with c3:
                tel = st.text_input("Telefone (opcional)")

            salvar = st.form_submit_button("Salvar indicação", type="primary", use_container_width=True)
            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                exec_sql(
                    "insert into public.indicacoes (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                    (nome.strip(), tipo, tel.strip() or None),
                )
                st.success("Indicação cadastrada.")
                st.rerun()
    else:
        df_one = safe_df("select * from public.indicacoes where id=%s;", (int(edit_ind_id),))
        if df_one.empty:
            st.session_state["edit_ind"] = None
            st.rerun()
        r = df_one.iloc[0]

        with st.form("form_ind_edit", clear_on_submit=False):
            c1, c2, c3 = st.columns([4, 2, 2])
            with c1:
                nome = st.text_input("Nome da indicação", value=r["nome"], key="ind_nome_edit")
            with c2:
                tipo = st.selectbox(
                    "Tipo",
                    ["ARQUITETO", "ENGENHEIRO", "LOJA", "OUTRO"],
                    index=["ARQUITETO", "ENGENHEIRO", "LOJA", "OUTRO"].index(r["tipo"]),
                    key="ind_tipo_edit",
                )
            with c3:
                tel = st.text_input("Telefone (opcional)", value=r["telefone"] or "", key="ind_tel_edit")

            b1, b2 = st.columns(2)
            with b1:
                salvar_alt = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
            with b2:
                cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)

            if salvar_alt:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                exec_sql(
                    "update public.indicacoes set nome=%s, tipo=%s, telefone=%s where id=%s;",
                    (nome.strip(), tipo, tel.strip() or None, int(edit_ind_id)),
                )
                st.success("Indicação atualizada.")
                st.session_state["edit_ind"] = None
                st.rerun()

            if cancelar:
                st.session_state["edit_ind"] = None
                st.rerun()

    df_ind = safe_df("select id, nome, tipo, telefone, ativo from public.indicacoes order by nome;")
    if df_ind.empty:
        st.info("Nenhuma indicação cadastrada.")
    else:
        for _, rr in df_ind.iterrows():
            colA, colB, colC = st.columns([6, 2, 2])
            with colA:
                st.write(f"**{rr['nome']}** — {rr['tipo']}")
                if rr["telefone"]:
                    st.caption(rr["telefone"])
            with colB:
                st.write("ATIVO ✅" if rr["ativo"] else "INATIVO ⛔")
            with colC:
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Editar", key=f"ind_edit_{int(rr['id'])}", use_container_width=True):
                        st.session_state["edit_ind"] = int(rr["id"])
                        st.rerun()
                with b2:
                    if rr["ativo"]:
                        if st.button("INATIVAR ⛔", key=f"ind_inat_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.indicacoes set ativo=false where id=%s;", (int(rr["id"]),))
                            st.rerun()
                    else:
                        if st.button("ATIVAR ✅", key=f"ind_at_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.indicacoes set ativo=true where id=%s;", (int(rr["id"]),))
                            st.rerun()

    st.divider()

    # ======================================================
    # CLIENTES
    # ======================================================
    st.markdown("## Clientes")

    edit_cli_id = st.session_state["edit_cliente"]

    # opções de indicação ativas para cliente indicado
    df_ind_ativos = safe_df("select id, nome from public.indicacoes where ativo=true order by nome;")

    def indic_fmt(x):
        if df_ind_ativos.empty:
            return str(x)
        return df_ind_ativos.loc[df_ind_ativos["id"] == x, "nome"].iloc[0]

    if edit_cli_id is None:
        with st.form("form_cli_novo", clear_on_submit=True):
            c1, c2, c3 = st.columns([4, 2, 2])
            with c1:
                nome = st.text_input("Nome do cliente")
            with c2:
                tel = st.text_input("Telefone (opcional)")
            with c3:
                origem = st.selectbox("Origem", ["PROPRIO", "INDICADO"], index=0)

            end = st.text_input("Endereço (opcional)")

            # Mostra sempre (porque em form não re-renderiza condicional)
            ids = df_ind_ativos["id"].tolist()
            opcoes = [None] + ids
            indicacao_id = st.selectbox(
                "Quem indicou (apenas se Origem = INDICADO)",
                opcoes,
                format_func=lambda x: "—" if x is None else indic_fmt(x),
            )
            
            salvar = st.form_submit_button("Salvar cliente", type="primary", use_container_width=True)
            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
            
                if origem == "INDICADO":
                    if indicacao_id is None:
                        st.warning("Selecione quem indicou.")
                        st.stop()
                else:
                    indicacao_id = None  # garante nulo se PROPRIO
            
                exec_sql(
                    """
                    insert into public.clientes (nome,telefone,endereco,origem,indicacao_id,ativo)
                    values (%s,%s,%s,%s,%s,true);
                    """,
                    (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicacao_id),
                )
                st.success("Cliente cadastrado.")
                st.rerun()
    else:
        df_one = safe_df("select * from public.clientes where id=%s;", (int(edit_cli_id),))
        if df_one.empty:
            st.session_state["edit_cliente"] = None
            st.rerun()
        r = df_one.iloc[0]

        with st.form("form_cli_edit", clear_on_submit=False):
            c1, c2, c3 = st.columns([4, 2, 2])
            with c1:
                nome = st.text_input("Nome do cliente", value=r["nome"], key="cli_nome_edit")
            with c2:
                tel = st.text_input("Telefone (opcional)", value=r["telefone"] or "", key="cli_tel_edit")
            with c3:
                origem = st.selectbox(
                    "Origem",
                    ["PROPRIO", "INDICADO"],
                    index=["PROPRIO", "INDICADO"].index(r["origem"]),
                    key="cli_origem_edit",
                )

            end = st.text_input("Endereço (opcional)", value=r["endereco"] or "", key="cli_end_edit")
            
            ids = df_ind_ativos["id"].tolist()
            opcoes = [None] + ids
            
            default_sel = None
            if pd.notna(r["indicacao_id"]):
                default_sel = int(r["indicacao_id"])
            
            # tenta manter a seleção atual
            idx = opcoes.index(default_sel) if default_sel in opcoes else 0
            
            indicacao_id = st.selectbox(
                "Quem indicou (apenas se Origem = INDICADO)",
                opcoes,
                index=idx,
                format_func=lambda x: "—" if x is None else indic_fmt(x),
                key="cli_ind_edit_any",
            )

            b1, b2 = st.columns(2)
            with b1:
                salvar_alt = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
            with b2:
                cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)

            if salvar_alt:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
            
                if origem == "INDICADO":
                    if indicacao_id is None:
                        st.warning("Selecione quem indicou.")
                        st.stop()
                else:
                    indicacao_id = None
            
                exec_sql(
                    """
                    update public.clientes
                    set nome=%s, telefone=%s, endereco=%s, origem=%s, indicacao_id=%s
                    where id=%s;
                    """,
                    (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicacao_id, int(edit_cli_id)),
                )
                st.success("Cliente atualizado.")
                st.session_state["edit_cliente"] = None
                st.rerun()

            if cancelar:
                st.session_state["edit_cliente"] = None
                st.rerun()

    st.markdown("### 📋 Lista de clientes")
    df_cli = safe_df("""
        select c.id, c.nome, c.telefone, c.endereco, c.origem, c.ativo,
               i.nome as indicacao_nome
        from public.clientes c
        left join public.indicacoes i on i.id=c.indicacao_id
        order by c.nome;
    """)

    if df_cli.empty:
        st.info("Nenhum cliente cadastrado.")
    else:
        for _, rr in df_cli.iterrows():
            colA, colB, colC = st.columns([6, 2, 2])
            with colA:
                st.write(f"**{rr['nome']}** — {rr['origem']} — {rr['indicacao_nome'] or ''}")
                if rr["telefone"]:
                    st.caption(rr["telefone"])
                if rr["endereco"]:
                    st.caption(rr["endereco"])
            with colB:
                st.write("ATIVO ✅" if rr["ativo"] else "INATIVO ⛔")
            with colC:
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Editar", key=f"cli_edit_{int(rr['id'])}", use_container_width=True):
                        st.session_state["edit_cliente"] = int(rr["id"])
                        st.rerun()
                with b2:
                    if rr["ativo"]:
                        if st.button("INATIVAR ⛔", key=f"cli_inat_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.clientes set ativo=false where id=%s;", (int(rr["id"]),))
                            st.rerun()
                    else:
                        if st.button("ATIVAR ✅", key=f"cli_at_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.clientes set ativo=true where id=%s;", (int(rr["id"]),))
                            st.rerun()

# ======================================================
# OBRAS (estável: form + modo edição + cliente rápido com origem/indicação)
# ======================================================
if menu == "OBRAS":
    st.subheader("🏗️ Obras")

    if "edit_obra" not in st.session_state:
        st.session_state["edit_obra"] = None

    # Listas base
    df_cli_ativos = safe_df("select id, nome from public.clientes where ativo=true order by nome;")
    df_ind_ativos = safe_df("select id, nome from public.indicacoes where ativo=true order by nome;")

    def ind_fmt(x):
        if df_ind_ativos.empty:
            return str(x)
        return df_ind_ativos.loc[df_ind_ativos["id"] == x, "nome"].iloc[0]

    # -------------------------
    # Cliente rápido (com origem + indicação + indicação rápida inline)
    # -------------------------
    with st.expander("➕ Cliente rápido (para criar obra na hora)"):
        with st.form("form_cliente_rapido", clear_on_submit=True):
            c1, c2, c3 = st.columns([4, 2, 2])
            with c1:
                nome = st.text_input("Nome do cliente")
            with c2:
                tel = st.text_input("Telefone (opcional)")
            with c3:
                origem = st.selectbox("Origem", ["PROPRIO", "INDICADO"], index=0)
    
            end = st.text_input("Endereço (opcional)")
    
            st.markdown("**Indicação (apenas se Origem = INDICADO)**")
    
            # Nova indicação (opcional) — sempre visível
            cc1, cc2, cc3 = st.columns([4, 2, 2])
            with cc1:
                ind_nome = st.text_input("Nova indicação (opcional)")
            with cc2:
                ind_tipo = st.selectbox("Tipo da indicação", ["ARQUITETO", "ENGENHEIRO", "LOJA", "OUTRO"], index=0)
            with cc3:
                ind_tel = st.text_input("Telefone indicação (opcional)")
    
            # Selecionar indicação existente — sempre visível
            ids = df_ind_ativos["id"].tolist()
            opcoes = [None] + ids
            indicacao_id = st.selectbox(
                "Ou selecione indicação existente",
                opcoes,
                format_func=lambda x: "—" if x is None else ind_fmt(x),
            )
    
            criar = st.form_submit_button("Criar cliente", type="primary", use_container_width=True)
    
            if criar:
                if not nome.strip():
                    st.warning("Informe o nome do cliente.")
                    st.stop()
    
                # Se origem indicado, precisa resolver indicacao_id (nova ou existente)
                if origem == "INDICADO":
                    # Se digitou nova indicação, cria e usa ela
                    if ind_nome.strip():
                        exec_sql(
                            "insert into public.indicacoes (nome,tipo,telefone,ativo) values (%s,%s,%s,true);",
                            (ind_nome.strip(), ind_tipo, ind_tel.strip() or None),
                        )
                        df_last = safe_df(
                            "select id from public.indicacoes where nome=%s order by id desc limit 1;",
                            (ind_nome.strip(),),
                        )
                        indicacao_id = int(df_last.iloc[0]["id"])
    
                    # Se ainda não tem, exige seleção
                    if indicacao_id is None:
                        st.warning("Selecione uma indicação existente ou cadastre uma nova.")
                        st.stop()
                else:
                    indicacao_id = None  # PROPRIO sempre nulo
    
                exec_sql(
                    """
                    insert into public.clientes (nome,telefone,endereco,origem,indicacao_id,ativo)
                    values (%s,%s,%s,%s,%s,true);
                    """,
                    (nome.strip(), tel.strip() or None, end.strip() or None, origem, indicacao_id),
                )
    
                st.success("Cliente criado. Agora selecione ele no cadastro da obra abaixo.")
                st.rerun()

    st.divider()

    # Atualiza clientes (caso tenha criado cliente rápido)
    df_cli_ativos = safe_df("select id, nome from public.clientes where ativo=true order by nome;")
    cli_ids = df_cli_ativos["id"].tolist()

    if not cli_ids:
        st.warning("Cadastre pelo menos um cliente ativo.")
        st.stop()

    edit_id = st.session_state["edit_obra"]

    if edit_id is None:
        st.markdown("### ➕ Nova obra")
        with st.form("form_obra_nova", clear_on_submit=True):
            cliente_id = st.selectbox(
                "Cliente",
                cli_ids,
                format_func=lambda x: df_cli_ativos.loc[df_cli_ativos["id"] == x, "nome"].iloc[0],
            )
            titulo = st.text_input("Título da obra")
            endereco = st.text_input("Endereço (opcional)")
            status = st.selectbox(
                "Status",
                ["AGUARDANDO", "INICIADO", "PAUSADO", "CANCELADO", "CONCLUIDO"],
                index=0,
            )

            salvar = st.form_submit_button("Salvar obra", type="primary", use_container_width=True)
            if salvar:
                if not titulo.strip():
                    st.warning("Informe o título.")
                    st.stop()
                exec_sql(
                    """
                    insert into public.obras (cliente_id,titulo,endereco_obra,status,ativo)
                    values (%s,%s,%s,%s,true);
                    """,
                    (int(cliente_id), titulo.strip(), endereco.strip() or None, status),
                )
                st.success("Obra cadastrada.")
                st.rerun()
    else:
        df_one = safe_df("select * from public.obras where id=%s;", (int(edit_id),))
        if df_one.empty:
            st.session_state["edit_obra"] = None
            st.rerun()
        r = df_one.iloc[0]

        st.markdown("### ✏️ Editar obra")
        with st.form("form_obra_edit", clear_on_submit=False):
            cliente_default = int(r["cliente_id"])
            idx = cli_ids.index(cliente_default) if cliente_default in cli_ids else 0

            cliente_id = st.selectbox(
                "Cliente",
                cli_ids,
                index=idx,
                format_func=lambda x: df_cli_ativos.loc[df_cli_ativos["id"] == x, "nome"].iloc[0],
                key="obra_cli_edit",
            )
            titulo = st.text_input("Título da obra", value=r["titulo"], key="obra_tit_edit")
            endereco = st.text_input("Endereço (opcional)", value=r["endereco_obra"] or "", key="obra_end_edit")
            status = st.selectbox(
                "Status",
                ["AGUARDANDO", "INICIADO", "PAUSADO", "CANCELADO", "CONCLUIDO"],
                index=["AGUARDANDO", "INICIADO", "PAUSADO", "CANCELADO", "CONCLUIDO"].index(r["status"]),
                key="obra_status_edit",
            )

            b1, b2 = st.columns(2)
            with b1:
                salvar_alt = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
            with b2:
                cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)

            if salvar_alt:
                if not titulo.strip():
                    st.warning("Informe o título.")
                    st.stop()
                exec_sql(
                    """
                    update public.obras
                    set cliente_id=%s, titulo=%s, endereco_obra=%s, status=%s
                    where id=%s;
                    """,
                    (int(cliente_id), titulo.strip(), endereco.strip() or None, status, int(edit_id)),
                )
                st.success("Obra atualizada.")
                st.session_state["edit_obra"] = None
                st.rerun()

            if cancelar:
                st.session_state["edit_obra"] = None
                st.rerun()

    st.divider()
    st.markdown("### 📋 Lista de obras")

    df_obras = safe_df("""
        select o.id, o.titulo, o.status, o.ativo, c.nome as cliente
        from public.obras o
        join public.clientes c on c.id=o.cliente_id
        order by o.id desc;
    """)

    if df_obras.empty:
        st.info("Nenhuma obra cadastrada.")
    else:
        for _, rr in df_obras.iterrows():
            colA, colB, colC = st.columns([6, 2, 2])
            with colA:
                st.write(f"**{rr['titulo']}** — {rr['cliente']}")
            with colB:
                st.write(rr["status"])
            with colC:
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Editar", key=f"obra_edit_{int(rr['id'])}", use_container_width=True):
                        st.session_state["edit_obra"] = int(rr["id"])
                        st.rerun()
                with b2:
                    if rr["ativo"]:
                        if st.button("INATIVAR ⛔", key=f"obra_inat_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.obras set ativo=false where id=%s;", (int(rr["id"]),))
                            st.rerun()
                    else:
                        if st.button("ATIVAR ✅", key=f"obra_at_{int(rr['id'])}", use_container_width=True):
                            exec_sql("update public.obras set ativo=true where id=%s;", (int(rr["id"]),))
                            st.rerun()
