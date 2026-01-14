# ======================================================
# SEPOL - V1.1 Cadastros Estáveis
# ======================================================
import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ======================================================
# CONFIG
# ======================================================
st.set_page_config("DEV SEPOL - Controle de Obras", layout="wide")

# ======================================================
# DB
# ======================================================
@st.cache_resource
def _conn_holder():
    # guarda uma conexão (pode morrer; a gente valida antes de usar)
    return {"conn": None}

def get_conn():
    holder = _conn_holder()
    conn = holder.get("conn")

    # se não existe ou está fechada → cria nova
    if conn is None or getattr(conn, "closed", 1) != 0:
        holder["conn"] = psycopg2.connect(
            st.secrets["DATABASE_URL"],
            cursor_factory=RealDictCursor,
            connect_timeout=10,
            sslmode="require",
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        conn = holder["conn"]

    return conn

def query_df(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
        return pd.DataFrame(rows)
    except psycopg2.InterfaceError:
        # conexão morreu → recria e tenta 1x
        holder = _conn_holder()
        holder["conn"] = None
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
        return pd.DataFrame(rows)
    except Exception:
        # rollback só se conexão estiver viva
        try:
            if getattr(conn, "closed", 1) == 0:
                conn.rollback()
        except Exception:
            pass
        raise

def exec_sql(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    except psycopg2.InterfaceError:
        # conexão morreu → recria e tenta 1x
        holder = _conn_holder()
        holder["conn"] = None
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    except Exception:
        try:
            if getattr(conn, "closed", 1) == 0:
                conn.rollback()
        except Exception:
            pass
        raise

def safe_df(sql, params=None):
    try:
        return query_df(sql, params)
    except Exception as e:
        st.error("Falha ao consultar o banco. (Conexão pode ter expirado; tente novamente.)")
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
# HELPERS
# ======================================================
def first_or_none(df, col):
    if df is None or df.empty:
        return None
    return df.iloc[0][col]

def to_int(x):
    try:
        return int(x)
    except Exception:
        return None

def go(dest):
    st.session_state["menu"] = dest
    st.session_state["menu_widget"] = dest  # mantém o selectbox sincronizado

def badge_status_orc(stt: str) -> str:
    stt = (stt or "").upper()
    return {
        "RASCUNHO": "📝 RASCUNHO",
        "EMITIDO": "📤 EMITIDO",
        "APROVADO": "✅ APROVADO",
        "REPROVADO": "❌ REPROVADO",
        "CANCELADO": "🚫 CANCELADO",
    }.get(stt, f"• {stt}")

def msg_status_orc(stt: str):
    stt = (stt or "").upper()
    if stt == "RASCUNHO":
        st.info("RASCUNHO: pode editar fases/serviços e recalcular.")
    elif stt == "EMITIDO":
        st.warning("EMITIDO: orçamento já foi enviado. Você pode REABRIR se precisar corrigir.")
    elif stt == "APROVADO":
        st.success("APROVADO: este orçamento vira referência da obra (pagamentos/recebimentos).")
    elif stt == "REPROVADO":
        st.error("REPROVADO: não gera fluxo financeiro.")
    elif stt == "CANCELADO":
        st.error("CANCELADO: não utilizar. Crie um novo orçamento se necessário.")

# ======================================================
# PDF
# ======================================================
def gerar_pdf_orcamento(df_head, df_itens) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    r = df_head.iloc[0]
    y = h - 50
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, f"SEPOL - Orçamento #{r['orcamento_id']}")    
    y -= 16
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"{r['titulo']}  - Status: {r['status']}")
    y -= 16

    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Cliente: {r['cliente_nome']}  Tel: {r.get('cliente_tel') or ''}")
    y -= 14
    c.drawString(50, y, f"Obra: {r['obra_titulo']}")
    y -= 14
    c.drawString(50, y, f"Endereço: {r.get('endereco_obra') or ''}")
    y -= 14
    
    y -= 24

    # Agrupa por fase
    if df_itens.empty:
        c.setFont("Helvetica", 10)
        c.drawString(50, y, "Sem fases/serviços cadastrados.")
        c.showPage()
        c.save()
        return buf.getvalue()

    fases = df_itens.groupby(["fase_id","ordem","nome_fase","valor_fase"], dropna=False)
    for (fase_id, ordem, nome_fase, valor_fase), g in fases:
        if y < 120:
            c.showPage()
            y = h - 50

        c.setFont("Helvetica-Bold", 12)
        # c.drawString(50, y, f"Fase {int(ordem)} - {nome_fase}  |  Total fase: {brl(valor_fase)}")
        c.drawString(50, y, f"Fase {int(ordem)} - {nome_fase}")
        y -= 16

        # Cabeçalho da tabela
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, y, "Serviço")
        c.drawString(270, y, "Qtd")
        c.drawString(310, y, "Un")
        # c.drawString(340, y, "V.Unit")
        # c.drawString(430, y, "Total")
        y -= 12
        c.setFont("Helvetica", 9)

        # Linhas
        for _, row in g.iterrows():
            serv = row.get("servico") or "-"
            qtd = row.get("quantidade")
            un = row.get("unidade") or ""
            # vunit = row.get("valor_unit")
            # vtot = row.get("valor_total")

            if y < 90:
                c.showPage()
                y = h - 50

            c.drawString(50, y, str(serv)[:40])
            c.drawRightString(300, y, "" if pd.isna(qtd) else f"{float(qtd):.2f}")
            c.drawString(310, y, str(un))
            # c.drawRightString(410, y, "" if pd.isna(vunit) else brl(vunit))
            # c.drawRightString(520, y, "" if pd.isna(vtot) else brl(vtot))
            y -= 12

        y -= 14

    y -= 14
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, f"TOTAL BRUTO: {brl(r['valor_total'])}")
    c.drawString(200, y, f"DESCONTO: {brl(r['desconto_valor'])}")
    c.drawString(350, y, f"TOTAL FINAL: {brl(r['valor_total_final'])}")
    y -= 20

    c.showPage()
    c.save()
    return buf.getvalue()

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
with st.sidebar:
    st.markdown(f"👤 {st.session_state['usuario']}")
    
    MENU_OPTS = ["HOJE", "PROFISSIONAIS", "CLIENTES", "SERVIÇOS", "OBRAS", "APONTAMENTOS", "FINANCEIRO"]
    
    if "menu" not in st.session_state:
        st.session_state["menu"] = "HOJE"
    if "menu_widget" not in st.session_state:
        st.session_state["menu_widget"] = st.session_state["menu"]
    
    # widget controla "menu_widget"
    st.selectbox("Menu", MENU_OPTS, key="menu_widget")
    
    # sincroniza: se usuário mudou no widget → atualiza menu
    if st.session_state["menu_widget"] != st.session_state["menu"]:
        st.session_state["menu"] = st.session_state["menu_widget"]
        st.rerun()

    if st.button("🔄 Recarregar conexão"):
        _conn_holder()["conn"] = None
        st.success("Conexão será recriada no próximo acesso.")
        
    if st.button("Sair"):
        st.session_state["usuario"] = None
        st.rerun()

menu = st.session_state["menu"]
st.title("🏗️ SEPOL - DEV")

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
                    if st.button("EDITAR ✏️", key=f"p_edit_{int(rr['id'])}", use_container_width=True):
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
                    if st.button("EDITAR ✏️", key=f"ind_edit_{int(rr['id'])}", use_container_width=True):
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

            if df_ind_ativos.empty:
                st.warning("Não existe nenhuma Indicação ativa cadastrada ainda.")
                ids = []
            else:
                # garante colunas
                if "id" not in df_ind_ativos.columns:
                    st.error(f"Erro: coluna 'id' não veio na consulta. Colunas disponíveis: {list(df_ind_ativos.columns)}")
                    st.stop()
                # Mostra sempre (porque em form não re-renderiza condicional)
                ids = [int(x) for x in df_ind_ativos["id"].tolist()]

            map_ind_cli = dict(zip(df_ind_ativos["id"], df_ind_ativos["nome"]))
            if ids:
                indicacao_id = st.selectbox(
                    "Quem indicou? (Clientes - Apenas se Origem = INDICADO)",
                    options=[None] + ids,  # sempre lista python
                    index=0,
                    format_func=lambda x: "—" if x is None else map_ind_cli.get(int(x), f"ID {x}"),
                    key="edit_cli_indicacao_id",
                    disabled=(len(ids)==0),
                )
            else:
                st.info("Cadastre uma Indicação em Cadastros → Indicações (ou use Cliente Próprio).")
            
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
            default_sel = None
            if pd.notna(r["indicacao_id"]):
                default_sel = int(r["indicacao_id"])
            
            # tenta manter a seleção atual
            idx = opcoes.index(default_sel) if default_sel in opcoes else 0
            
            indicacao_id = st.selectbox(
                "Quem indicou? (Obras - Apenas se Origem = INDICADO)",
                options=[None] + ids,
                index=idx,
                format_func=lambda x: df_ind_ativos.loc[df_ind_ativos["id"] == x, "nome"].iloc[0],
                key="cli_ind_edit_any",
                disabled=(len(ids)==0),
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
                    if st.button("EDITAR ✏️", key=f"cli_edit_{int(rr['id'])}", use_container_width=True):
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
# SERVIÇOS + CATÁLOGO (V1.5: form + modo edição)
# ======================================================
if menu == "SERVIÇOS":
    st.subheader("🏗️ Serviços (catálogo)")

    if "edit_servico_id" not in st.session_state:
        st.session_state["edit_servico_id"] = None

    edit_id = st.session_state["edit_servico_id"]

    # carregar registro para edição
    row = None
    if edit_id:
        df_one = safe_df("select * from public.servicos where id=%s;", (int(edit_id),))
        if not df_one.empty:
            row = df_one.iloc[0]
        else:
            st.session_state["edit_servico_id"] = None
            edit_id = None

    st.markdown("#### " + ("Editar serviço" if edit_id else "Novo serviço"))

    # form (não mexe em session_state de widget)
    with st.form("servico_form", clear_on_submit=(edit_id is None)):
        c1, c2 = st.columns([5, 2])
        with c1:
            nome = st.text_input("Nome do serviço", value=(row["nome"] if row is not None else ""))
        with c2:
            unidade_opts = ["UN", "M2", "L", "H", "DIA"]
            unidade = st.selectbox(
                "Unidade",
                unidade_opts,
                index=(unidade_opts.index(row["unidade"]) if row is not None else 0),
            )

        b1, b2, b3 = st.columns([2,2,2])

        with b1:
            salvar = st.form_submit_button("Salvar", type="primary", use_container_width=True)

        with b2:
            cancelar = st.form_submit_button("Cancelar edição", use_container_width=True, disabled=(not bool(edit_id)))

        with b3:
            limpar = st.form_submit_button("Limpar", use_container_width=True)

        if salvar:
            if not nome.strip():
                st.warning("Informe o nome do serviço.")
                st.stop()

            try:
                if not edit_id:
                    exec_sql(
                        "insert into public.servicos (nome, unidade, ativo) values (%s,%s,true);",
                        (nome.strip(), unidade),
                    )
                    st.success("Serviço cadastrado!")
                else:
                    exec_sql(
                        "update public.servicos set nome=%s, unidade=%s where id=%s;",
                        (nome.strip(), unidade, int(edit_id)),
                    )
                    st.success("Serviço atualizado!")
                    st.session_state["edit_servico_id"] = None

                st.rerun()
            except Exception as e:
                st.error("Falha ao salvar (talvez serviço com mesmo nome).")
                st.exception(e)
                st.stop()

        if cancelar:
            st.session_state["edit_servico_id"] = None
            st.rerun()

        if limpar:
            st.session_state["edit_servico_id"] = None
            st.rerun()

    st.divider()
    st.markdown("#### Lista")

    df = safe_df("select id, nome, unidade, ativo, criado_em from public.servicos order by nome;")
    if df.empty:
        st.info("Nenhum serviço cadastrado.")
    else:
        for _, rr in df.iterrows():
            sid = int(rr["id"])
            colA, colB, colC, colD, colE = st.columns([5,2,2,2,2])
            with colA:
                st.write(f"**{rr['nome']}**")
            with colB:
                st.write(rr["unidade"])
            with colC:
                st.write("ATIVO" if rr["ativo"] else "INATIVO")
            with colD:
                if st.button("Editar", key=f"serv_edit_{sid}", use_container_width=True):
                    st.session_state["edit_servico_id"] = sid
                    st.rerun()
            with colE:
                bE1, bE2 = st.columns(2)
                with bE1:
                    if rr["ativo"]:
                        if st.button("Inativar", key=f"serv_inat_{sid}", use_container_width=True):
                            exec_sql("update public.servicos set ativo=false where id=%s;", (sid,))
                            st.rerun()
                    else:
                        if st.button("Ativar", key=f"serv_at_{sid}", use_container_width=True):
                            exec_sql("update public.servicos set ativo=true where id=%s;", (sid,))
                            st.rerun()
                with bE2:
                    st.write("")  # só pra manter alinhamento

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

            if df_ind_ativos.empty:
                st.warning("Não existe nenhuma Indicação ativa cadastrada ainda.")
                ids = []
            else:
                # garante colunas
                if "id" not in df_ind_ativos.columns:
                    st.error(f"Erro: coluna 'id' não veio na consulta. Colunas disponíveis: {list(df_ind_ativos.columns)}")
                    st.stop()
                # Mostra sempre (porque em form não re-renderiza condicional)   
                ids = [int(x) for x in df_ind_ativos["id"].tolist()]

            map_ind = dict(zip(df_ind_ativos["id"], df_ind_ativos["nome"]))
            if ids:
                indicacao_id = st.selectbox(
                    "Quem indicou? (Cliente Rápido - Apenas se Origem = INDICADO)",
                    options=[None] + ids,  # sempre lista python
                    index=0,
                    format_func=lambda x: "—" if x is None else map_ind.get(int(x), f"ID {x}"),
                    key="obra_cli_indicacao_id",
                    disabled=(len(ids)==0),
                )

            else:
                st.info("Cadastre uma Indicação em Cadastros → Indicações (ou use Cliente Próprio).")
    
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

    if df_cli_ativos.empty:
        st.warning("Não existe nenhum Cliente ativa cadastrado ainda.")
        cli_ids = []
    else:
        # garante colunas
        if "id" not in df_cli_ativos.columns:
            st.error(f"Erro: coluna 'id' não veio na consulta. Colunas disponíveis: {list(df_cli_ativos.columns)}")
            st.stop()
        # Mostra sempre (porque em form não re-renderiza condicional)   
        cli_ids = [int(x) for x in df_cli_ativos["id"].tolist()]

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
                    if st.button("EDITAR ✏️", key=f"obra_edit_{int(rr['id'])}", use_container_width=True):
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
                            
    if "obra_sel" not in st.session_state:
        st.session_state["obra_sel"] = None
    if "orc_sel" not in st.session_state:
        st.session_state["orc_sel"] = None
    if "edit_orc" not in st.session_state:
        st.session_state["edit_orc"] = None
    if "edit_fase" not in st.session_state:
        st.session_state["edit_fase"] = None

    st.divider()
    st.markdown("## 🔎 Abrir uma Obra")

    df_obras = safe_df("""
        select o.id, o.titulo, o.status, c.nome as cliente
        from public.obras o
        join public.clientes c on c.id=o.cliente_id
        where o.ativo=true
        order by o.id desc
        limit 200;
    """)

    if df_obras.empty:
        st.info("Nenhuma obra cadastrada.")
        st.stop()

    obra_ids = df_obras["id"].tolist()
    default_obra = st.session_state["obra_sel"] if st.session_state["obra_sel"] in obra_ids else obra_ids[0]

    obra_sel = st.selectbox(
        "Selecione a obra",
        obra_ids,
        index=obra_ids.index(default_obra),
        format_func=lambda x: f"#{x} • {df_obras.loc[df_obras['id']==x,'titulo'].iloc[0]} • {df_obras.loc[df_obras['id']==x,'cliente'].iloc[0]}",
        key="obra_sel_box",
    )

    # sincroniza seleção
    if st.session_state["obra_sel"] != obra_sel:
        st.session_state["obra_sel"] = obra_sel
        st.session_state["orc_sel"] = None
        st.session_state["edit_orc"] = None
        st.session_state["edit_fase"] = None
        st.rerun()

    obra_id = int(st.session_state["obra_sel"])

    tabs = st.tabs(["Orçamentos", "Fases do Orçamento", "Serviços", "Recebimentos"])

    with tabs[0]:
        st.markdown("### 📄 Orçamentos da Obra")
    
        df_orc = safe_df("""
            select id, titulo, status, valor_total, desconto_valor, valor_total_final, criado_em, aprovado_em
            from public.orcamentos
            where obra_id=%s
            order by id desc;
        """, (obra_id,))
    
        # --- Criar novo orçamento ---
        with st.form("orc_novo", clear_on_submit=True):
            col1, col2 = st.columns([5,2])
            with col1:
                tit = st.text_input("Título do orçamento", value="Orçamento")
            with col2:
                st.caption("Status inicial")
                st.write("RASCUNHO")

            
            criar = st.form_submit_button("Criar orçamento", type="primary", use_container_width=True)
            if criar:
                if not tit.strip():
                    st.warning("Informe o título.")
                    st.stop()
                exec_sql(
                    "insert into public.orcamentos (obra_id, titulo, status) values (%s,%s,'RASCUNHO');",
                    (obra_id, tit.strip()),
                )
                st.success("Orçamento criado.")
                st.rerun()
    
        st.divider()
        st.markdown("#### Lista (selecionar / editar / aprovar)")
    
        if df_orc.empty:
            st.info("Nenhum orçamento ainda. Crie um orçamento.")
        else:
            # seleção do orçamento ativo na UI
            orc_ids = df_orc["id"].tolist()
            if st.session_state["orc_sel"] not in orc_ids:
                st.session_state["orc_sel"] = orc_ids[0]
    
            sel = st.selectbox(
                "Orçamento selecionado",
                orc_ids,
                index=orc_ids.index(st.session_state["orc_sel"]),
                format_func=lambda x: f"#{x} • {df_orc.loc[df_orc['id']==x,'titulo'].iloc[0]} • {df_orc.loc[df_orc['id']==x,'status'].iloc[0]}",
                key="orc_sel_box",
            )
            st.session_state["orc_sel"] = sel

            st.divider()
            st.markdown("### 🔎 Orçamento selecionado")
            
            orc_sel = int(st.session_state["orc_sel"])
            df_sel = safe_df("""
                select id, titulo, status, criado_em, aprovado_em, valor_total, desconto_valor, valor_total_final
                from public.orcamentos
                where id=%s;
            """, (orc_sel,))
            
            if not df_sel.empty:
                rr = df_sel.iloc[0]
                cA, cB, cC = st.columns([5,2,2])
                with cA:
                    st.write(f"**#{int(rr['id'])} — {rr['titulo']}**")
                    st.caption(f"{badge_status_orc(rr['status'])}")
                with cB:
                    st.metric("Total", brl(rr.get("valor_total", 0)))
                    st.metric("Total", brl(rr.get("desconto_valor", 0)))
                    st.metric("Total", brl(rr.get("valor_total_final", 0)))
                with cC:
                    st.write("Ações")
                    status_atual = rr["status"]
                    travado_final = status_atual in ("APROVADO","REPROVADO","CANCELADO")
                    
                    st.markdown("#### Desconto (antes de emitir)")
                    desc_novo = st.number_input(
                        "Desconto em R$",
                        min_value=0.0,
                        step=50.0,
                        value=float(rr.get("desconto_valor", 0) or 0),
                        disabled=travado_final,
                        key=f"desc_orc_{orc_sel}"
                    )
                    
                    if st.button("Salvar desconto", use_container_width=True, disabled=travado_final):
                        exec_sql("update public.orcamentos set desconto_valor=%s where id=%s;", (float(desc_novo), int(orc_sel)))
                        exec_sql("select public.fn_recalcular_orcamento(%s);", (int(orc_sel),))
                        st.success("Desconto aplicado e totais recalculados.")
                        st.rerun()

                    if st.button("Recalcular", key=f"sel_recalc_{orc_sel}", use_container_width=True):
                        exec_sql("select public.fn_recalcular_orcamento(%s);", (orc_sel,))
                        st.success("Recalculado.")
                        st.rerun()
                        
                    if st.button("Emitir (PDF)", key=f"sel_emit_{orc_sel}", type="primary", use_container_width=True,
                                 disabled=(rr["status"] in ("APROVADO","REPROVADO","CANCELADO"))):
                        exec_sql("update public.orcamentos set desconto_valor=%s where id=%s;", (float(desc_novo), int(rid)))
                        exec_sql("select public.fn_recalcular_orcamento(%s);", (orc_sel,))
                        exec_sql("update public.orcamentos set status='EMITIDO' where id=%s;", (orc_sel,))
                        st.success("Emitido. Role para baixar o PDF na lista ou clique novamente no orçamento.")
                        st.rerun()
            
                msg_status_orc(rr["status"])

    
            # grid simples 60+
            for _, r in df_orc.iterrows():
                rid = int(r["id"])
                status_atual = r["status"]
                selecionado = (rid == st.session_state.get("orc_sel"))
                c1, c2, c3, c4, c5 = st.columns([5,2,2,2,2])
                
                with c1:
                    titulo = r["titulo"]
                    st.write(f"**#{rid} — {titulo}**")
                    st.caption(f"{badge_status_orc(status_atual)}  •  Criado: {str(r['criado_em'])[:19]}")
                    if selecionado:
                        st.success("✅ Este é o orçamento selecionado")
                    
                with c2:
                    if st.button("Selecionar", key=f"orc_pick_{rid}", use_container_width=True):
                        st.session_state["orc_sel"] = rid
                        st.session_state["edit_orc"] = rid
                        st.rerun()
                        
                with c3:
                    if st.button("Editar", key=f"orc_edit_{rid}", use_container_width=True):
                        st.session_state["edit_orc"] = rid
                        st.rerun()
                        
                with c4:
                    if st.button("Aprovar", key=f"orc_ap_{rid}", type="primary", use_container_width=True):
                        try:
                            exec_sql(
                                "update public.orcamentos set status='APROVADO', aprovado_em=current_date where id=%s;",
                                (rid,),
                            )
                            st.success("Orçamento aprovado.")
                            st.rerun()
                        except Exception as e:
                            st.error("Não foi possível aprovar. Talvez já exista outro orçamento APROVADO para esta obra.")
                            st.exception(e)
                
                with c5:
                    status_atual = r["status"]

                    # -----------------------------
                    # STATUS EDITÁVEL (apenas RASCUNHO <-> EMITIDO)
                    # -----------------------------
                    status_editaveis = ["RASCUNHO", "EMITIDO"]
                    
                    # se já está finalizado, trava totalmente
                    travado_final = status_atual in ("APROVADO", "REPROVADO", "CANCELADO")
                    
                    # se status atual não está nos editáveis (ex: aprovado),
                    # mantemos só para exibição
                    opcoes_status = status_editaveis if status_atual in status_editaveis else [status_atual]
                    
                    novo_status = st.selectbox(
                        "Status",
                        opcoes_status,
                        index=opcoes_status.index(status_atual),
                        key=f"orc_st_{rid}",
                        disabled=travado_final
                    )

                    # --- salvar status ---
                    if st.button("Salvar status", key=f"orc_svst_{rid}", use_container_width=True, disabled=travado_final or (novo_status == status_atual)):
                        # Aprovação deve passar pela regra do índice único
                        try:
                            exec_sql(
                                """
                                update public.orcamentos 
                                set status=%s, 
                                    aprovado_em=case when %s='APROVADO' then current_date else aprovado_em end 
                                where id=%s;
                                """,
                                (novo_status, novo_status, rid),
                            )
                            st.success("Status atualizado.")
                            st.rerun()
                        except Exception as e:
                            st.error("Falha ao atualizar status (provável conflito com orçamento APROVADO).")
                            st.exception(e)

                    st.divider()
                    st.caption("Ações do Orçamento")
                    
                    # --- recalcular (sempre útil antes de emitir) ---
                    if st.button("Recalcular totais", key=f"orc_recalc_{rid}", use_container_width=True, disabled=travado_final):
                        exec_sql("select public.fn_recalcular_orcamento(%s);", (rid,))
                        st.success("Totais recalculados.")
                        st.rerun()
                    
                    # --- emitir (gera PDF) ---
                    if st.button("Emitir (gera PDF)", key=f"orc_emit_{rid}", type="primary", use_container_width=True, disabled=travado_final):
                        # recalcula + emite
                        exec_sql("update public.orcamentos set desconto_valor=%s where id=%s;", (float(desc_novo), int(rid)))
                        exec_sql("select public.fn_recalcular_orcamento(%s);", (rid,))
                        exec_sql("update public.orcamentos set status='EMITIDO' where id=%s;", (rid,))
                    
                        df_head = safe_df(
                            """
                            select
                              o.id as orcamento_id, o.titulo, o.status, o.valor_total, o.desconto_valor, o.valor_total_final,
                              ob.titulo as obra_titulo, ob.endereco_obra,
                              c.nome as cliente_nome, c.telefone as cliente_tel
                            from public.orcamentos o
                            join public.obras ob on ob.id=o.obra_id
                            join public.clientes c on c.id=ob.cliente_id
                            where o.id=%s;
                            """, 
                            (rid,),
                        )
                        
                        df_itens = safe_df(
                            """
                            select
                              f.id as fase_id, f.ordem, f.nome_fase, f.valor_fase,
                              s.nome as servico, s.unidade,
                              ofs.quantidade, ofs.valor_unit, ofs.valor_total
                            from public.obra_fases f
                            left join public.orcamento_fase_servicos ofs on ofs.obra_fase_id=f.id and ofs.orcamento_id=f.orcamento_id
                            left join public.servicos s on s.id=ofs.servico_id
                            where f.orcamento_id=%s
                            order by f.ordem, s.nome nulls last;
                            """, 
                            (rid,),
                        )
                    
                        pdf_bytes = gerar_pdf_orcamento(df_head, df_itens)
                    
                        st.download_button(
                            "⬇️ Baixar PDF do Orçamento",
                            data=pdf_bytes,
                            file_name=f"SEPOL_Orcamento_{rid}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"orc_pdf_{rid}"
                        )

                    # --- REABRIR (somente se ainda não foi aprovado/reprovado/cancelado) ---
                    pode_reabrir = status_atual in ("EMITIDO", "RASCUNHO")
                
                    if st.button("Reabrir (voltar para RASCUNHO)", key=f"orc_reabrir_{rid}", use_container_width=True, disabled=(not pode_reabrir)):
                        exec_sql("update public.orcamentos set status='RASCUNHO' where id=%s;", (rid,))
                        st.success("Orçamento reaberto (RASCUNHO).")
                        st.rerun()
    
            # Form de edição do orçamento selecionado
            edit_id = st.session_state.get("edit_orc")
            if edit_id:
                df_one = safe_df("select * from public.orcamentos where id=%s;", (int(edit_id),))
                if not df_one.empty:
                    rr = df_one.iloc[0]
                    st.divider()
                    st.markdown("#### ✏️ Editar orçamento")
                    with st.form("orc_edit_form", clear_on_submit=False):
                        travado_final = rr["status"] in ("APROVADO","REPROVADO","CANCELADO")
                        t = st.text_input("Título", value=rr["titulo"] or "", disabled=travado_final)
                        obs = st.text_input("Observação (opcional)", value=rr["observacao"] or "", disabled=travado_final)
                        b1, b2 = st.columns(2)
                        with b1:
                            salvar = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
                        with b2:
                            cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)
                        if salvar:
                            if not t.strip():
                                st.warning("Informe o título.")
                                st.stop()
                            exec_sql("update public.orcamentos set titulo=%s, observacao=%s where id=%s;", (t.strip(), obs.strip() or None, int(edit_id)))
                            st.session_state["edit_orc"] = None
                            st.success("Atualizado.")
                            st.rerun()
                        if cancelar:
                            st.session_state["edit_orc"] = None
                            st.rerun()

    with tabs[1]:
        st.markdown("### 🧱 Fases do Orçamento")
    
        orc_id = st.session_state.get("orc_sel")
        if not orc_id:
            st.info("Selecione um orçamento na aba Orçamentos.")
            st.stop()
    
        # status do orçamento (para travar apontamento depois)
        df_orc1 = safe_df("select id, status, titulo from public.orcamentos where id=%s;", (int(orc_id),))
        orc_status = df_orc1.iloc[0]["status"]
        st.caption(f"Orçamento #{orc_id}: **{df_orc1.iloc[0]['titulo']}** • Status: **{orc_status}**")
    
        df_fases = safe_df("""
            select id, ordem, nome_fase, status, valor_fase
            from public.obra_fases
            where orcamento_id=%s
            order by ordem asc;
        """, (int(orc_id),))
    
        # --- Nova fase / editar fase ---
        edit_fase = st.session_state.get("edit_fase")
    
        if edit_fase:
            df_one = safe_df("select * from public.obra_fases where id=%s;", (int(edit_fase),))
            if df_one.empty:
                st.session_state["edit_fase"] = None
                st.rerun()
            r = df_one.iloc[0]
            st.markdown("#### ✏️ Editar fase")
            with st.form("fase_edit", clear_on_submit=False):
                c1, c2, c3 = st.columns([2,5,2])
                with c1:
                    ordem = st.number_input("Ordem", min_value=1, step=1, value=int(r["ordem"]))
                with c2:
                    nome = st.text_input("Nome da fase", value=r["nome_fase"])
                with c3:
                    status = st.selectbox("Status", ["AGUARDANDO","INICIADO","PAUSADO","CONCLUIDO","CANCELADO"],
                                          index=["AGUARDANDO","INICIADO","PAUSADO","CONCLUIDO","CANCELADO"].index(r["status"]))
                valor = st.number_input("Valor da fase (R$)", min_value=0.0, step=100.0, value=float(r["valor_fase"]))
                b1, b2, b3 = st.columns(3)
                with b1:
                    salvar = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
                with b2:
                    cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)
                with b3:
                    excluir = st.form_submit_button("Excluir", use_container_width=True)
    
                if salvar:
                    if not nome.strip():
                        st.warning("Informe o nome da fase.")
                        st.stop()
                    try:
                        exec_sql("""
                            update public.obra_fases
                            set ordem=%s, nome_fase=%s, status=%s, valor_fase=%s
                            where id=%s;
                        """, (int(ordem), nome.strip(), status, float(valor), int(edit_fase)))
                        st.success("Fase atualizada.")
                        st.session_state["edit_fase"] = None
                        st.rerun()
                    except Exception as e:
                        st.error("Falha ao salvar (talvez conflito de ordem dentro do orçamento).")
                        st.exception(e)
                        st.stop()
    
                if cancelar:
                    st.session_state["edit_fase"] = None
                    st.rerun()
    
                if excluir:
                    # se já existir recebimento, vai bloquear por FK (ok)
                    try:
                        exec_sql("delete from public.obra_fases where id=%s;", (int(edit_fase),))
                        st.success("Fase excluída.")
                        st.session_state["edit_fase"] = None
                        st.rerun()
                    except Exception as e:
                        st.error("Não foi possível excluir (pode haver recebimento associado).")
                        st.exception(e)
                        st.stop()
        else:
            st.markdown("#### ➕ Nova fase")
            with st.form("fase_nova", clear_on_submit=True):
                c1, c2, c3 = st.columns([2,5,2])
                with c1:
                    ordem = st.number_input("Ordem", min_value=1, step=1, value=1)
                with c2:
                    nome = st.text_input("Nome da fase", value="PREPARAÇÃO E APLICAÇÃO")
                with c3:
                    status = st.selectbox("Status", ["AGUARDANDO","INICIADO","PAUSADO","CONCLUIDO","CANCELADO"], index=0)
                valor = st.number_input("Valor da fase (R$)", min_value=0.0, step=100.0, value=0.0)
    
                salvar = st.form_submit_button("Salvar fase", type="primary", use_container_width=True)
                if salvar:
                    if not nome.strip():
                        st.warning("Informe o nome da fase.")
                        st.stop()
                    try:
                        exec_sql("""
                            insert into public.obra_fases (obra_id, orcamento_id, nome_fase, ordem, status, valor_fase)
                            values (%s,%s,%s,%s,%s,%s);
                        """, (obra_id, int(orc_id), nome.strip(), int(ordem), status, float(valor)))
                        st.success("Fase criada.")
                        st.rerun()
                    except Exception as e:
                        st.error("Falha ao criar (provável conflito de ordem dentro do orçamento).")
                        st.exception(e)
                        st.stop()
    
        st.divider()
        st.markdown("#### Lista de fases")        
        if df_fases.empty:
            st.info("Nenhuma fase ainda.")
        else:            
            total_orc = float(df_fases["valor_fase"].sum()) if "valor_fase" in df_fases.columns else 0.0
            st.success(f"Total das Fases neste Orçamento: {brl(total_orc)}")
            for _, rr in df_fases.iterrows():
                fid = int(rr["id"])
                c1, c2, c3, c4, c5 = st.columns([1,4,2,2,2])
                with c1:
                    st.write(int(rr["ordem"]))
                with c2:
                    st.write(f"**{rr['nome_fase']}**")
                with c3:
                    st.write(rr["status"])
                with c4:
                    st.write(brl(rr["valor_fase"]))
                with c5:
                    if st.button("Editar", key=f"fase_edit_{fid}", use_container_width=True):
                        st.session_state["edit_fase"] = fid
                        st.rerun()

    with tabs[2]:
        st.markdown("### 🧾 Serviços da Fase (Orçamento)")
    
        orc_id = st.session_state.get("orc_sel")
        if not orc_id:
            st.info("Selecione um orçamento na aba Orçamentos.")
            st.stop()
    
        # fases do orçamento
        df_fases = safe_df("""
            select id, ordem, nome_fase, status, valor_fase
            from public.obra_fases
            where orcamento_id=%s
            order by ordem;
        """, (int(orc_id),))
    
        if df_fases.empty:
            st.info("Crie fases primeiro na aba Fases do Orçamento.")
            st.stop()
    
        # catálogo serviços ativos
        df_serv = safe_df("""
            select id, nome, unidade
            from public.servicos
            where ativo=true
            order by nome;
        """)
    
        if df_serv.empty:
            st.warning("Cadastre serviços primeiro em Cadastros → Serviços.")
            st.stop()
    
        # selecionar fase
        fase_ids = df_fases["id"].astype(int).tolist()
        if "fase_sel" not in st.session_state or st.session_state["fase_sel"] not in fase_ids:
            st.session_state["fase_sel"] = fase_ids[0]
    
        fase_sel = st.selectbox(
            "Selecione a fase",
            options=fase_ids,
            index=fase_ids.index(st.session_state["fase_sel"]),
            format_func=lambda x: f"{int(df_fases.loc[df_fases['id']==x,'ordem'].iloc[0])} - {df_fases.loc[df_fases['id']==x,'nome_fase'].iloc[0]}",
            key="fase_sel_box"
        )
        st.session_state["fase_sel"] = fase_sel
        obra_fase_id = int(fase_sel)
    
        st.caption("Dica 60+: cadastre aqui os serviços planejados. Isso monta o orçamento por fase.")
    
        # adicionar serviço na fase
        st.markdown("#### ➕ Adicionar serviço na fase")
        with st.form("add_servico_fase", clear_on_submit=True):
            serv_ids = df_serv["id"].astype(int).tolist()
            serv_id = st.selectbox(
                "Serviço",
                options=serv_ids,
                format_func=lambda x: f"{df_serv.loc[df_serv['id']==x,'nome'].iloc[0]} ({df_serv.loc[df_serv['id']==x,'unidade'].iloc[0]})"
            )
            c1, c2 = st.columns(2)
            with c1:
                qtd = st.number_input("Quantidade", min_value=0.01, step=1.0, value=1.0)
            with c2:
                vunit = st.number_input("Valor unitário (R$)", min_value=0.0, step=50.0, value=0.0)
    
            obs = st.text_input("Observação (opcional)")
    
            add = st.form_submit_button("Adicionar", type="primary", use_container_width=True)
            if add:
                try:
                    exec_sql("""
                        insert into public.orcamento_fase_servicos
                          (orcamento_id, obra_fase_id, servico_id, quantidade, valor_unit, observacao)
                        values (%s,%s,%s,%s,%s,%s);
                    """, (int(orc_id), obra_fase_id, int(serv_id), float(qtd), float(vunit), obs.strip() or None))
                    st.success("Serviço adicionado na fase.")
                    st.rerun()
                except Exception as e:
                    st.error("Falha ao adicionar (talvez serviço já exista nessa fase).")
                    st.exception(e)
                    st.stop()
    
        # lista serviços na fase
        st.divider()
        st.markdown("#### Lista de serviços da fase")
    
        df_it = safe_df("""
            select
              ofs.id,
              s.nome as servico,
              s.unidade,
              ofs.quantidade,
              ofs.valor_unit,
              ofs.valor_total,
              ofs.observacao
            from public.orcamento_fase_servicos ofs
            join public.servicos s on s.id=ofs.servico_id
            where ofs.orcamento_id=%s and ofs.obra_fase_id=%s
            order by s.nome;
        """, (int(orc_id), obra_fase_id))
    
        if df_it.empty:
            st.info("Nenhum serviço adicionado nesta fase.")
        else:
            total_fase = float(df_it["valor_total"].sum()) if "valor_total" in df_it.columns else 0.0
            st.success(f"Total dos serviços nesta fase: {brl(total_fase)}")
    
            # editar/excluir por linha (simples)
            for _, r in df_it.iterrows():
                iid = int(r["id"])
                col1, col2, col3, col4, col5, col6 = st.columns([4,1,1,2,2,2])
                with col1:
                    st.write(f"**{r['servico']}**")
                    if r.get("observacao"):
                        st.caption(r["observacao"])
                with col2:
                    st.write(r["unidade"])
                with col3:
                    st.write(float(r["quantidade"]))
                with col4:
                    st.write(brl(r["valor_unit"]))
                with col5:
                    st.write(brl(r["valor_total"]))
                with col6:
                    bE, bX = st.columns(2)
                    with bE:
                        if st.button("Editar", key=f"ofs_edit_{iid}", use_container_width=True):
                            st.session_state["edit_ofs_id"] = iid
                            st.rerun()
                    with bX:
                        if st.button("Remover", key=f"ofs_del_{iid}", use_container_width=True):
                            exec_sql("delete from public.orcamento_fase_servicos where id=%s;", (iid,))
                            st.success("Removido.")
                            st.rerun()
    
        # editor inline do item selecionado
        if "edit_ofs_id" not in st.session_state:
            st.session_state["edit_ofs_id"] = None
    
        edit_ofs_id = st.session_state.get("edit_ofs_id")
        if edit_ofs_id:
            df_one = safe_df("""
                select ofs.*, s.nome as servico_nome, s.unidade
                from public.orcamento_fase_servicos ofs
                join public.servicos s on s.id=ofs.servico_id
                where ofs.id=%s;
            """, (int(edit_ofs_id),))
    
            if df_one.empty:
                st.session_state["edit_ofs_id"] = None
                st.rerun()
    
            rr = df_one.iloc[0]
            st.divider()
            st.markdown(f"#### ✏️ Editar item — {rr['servico_nome']} ({rr['unidade']})")
    
            with st.form("ofs_edit_form", clear_on_submit=False):
                c1, c2 = st.columns(2)
                with c1:
                    qtd2 = st.number_input("Quantidade", min_value=0.01, step=1.0, value=float(rr["quantidade"]))
                with c2:
                    vunit2 = st.number_input("Valor unitário (R$)", min_value=0.0, step=50.0, value=float(rr["valor_unit"]))
                obs2 = st.text_input("Observação", value=(rr["observacao"] or ""))
    
                b1, b2 = st.columns(2)
                with b1:
                    salvar = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
                with b2:
                    cancelar = st.form_submit_button("Cancelar", use_container_width=True)
    
                if salvar:
                    exec_sql("""
                        update public.orcamento_fase_servicos
                        set quantidade=%s, valor_unit=%s, observacao=%s
                        where id=%s;
                    """, (float(qtd2), float(vunit2), obs2.strip() or None, int(edit_ofs_id)))
                    st.session_state["edit_ofs_id"] = None
                    st.success("Atualizado.")
                    st.rerun()
    
                if cancelar:
                    st.session_state["edit_ofs_id"] = None
                    st.rerun()

    
    with tabs[3]:
        st.markdown("### 💳 Recebimentos (por fase)")
    
        orc_id = st.session_state.get("orc_sel")
        if not orc_id:
            st.info("Selecione um orçamento na aba Orçamentos.")
            st.stop()
    
        df_fases = safe_df("""
            select id, ordem, nome_fase, valor_fase, status
            from public.obra_fases
            where orcamento_id=%s
            order by ordem;
        """, (int(orc_id),))
    
        if df_fases.empty:
            st.info("Crie fases primeiro.")
            st.stop()
    
        # lista fases + recebimento existente (se houver)
        df_rec = safe_df("""
            select r.id as receb_id, r.obra_fase_id, r.status as receb_status,
                   r.valor_previsto, r.acrescimo, r.valor_total, r.vencimento, r.recebido_em
            from public.recebimentos r
            where r.orcamento_id=%s
            order by r.id desc;
        """, (int(orc_id),))
    
        rec_by_fase = {}
        if not df_rec.empty:
            for _, r in df_rec.iterrows():
                rec_by_fase[int(r["obra_fase_id"])] = r
    
        for _, f in df_fases.iterrows():
            fase_id = int(f["id"])
            rec = rec_by_fase.get(fase_id)
    
            st.markdown(f"#### Fase {int(f['ordem'])} — {f['nome_fase']}")
            c1, c2, c3, c4 = st.columns([2,2,2,2])
            with c1:
                st.write("Valor fase:", brl(f["valor_fase"]))
            with c2:
                st.write("Recebimento:", ("—" if rec is None else f"#{int(rec['receb_id'])}"))
            with c3:
                st.write("Status:", ("—" if rec is None else rec["receb_status"]))
            with c4:
                st.write("Total:", ("—" if rec is None else brl(rec["valor_total"])))
    
            with st.expander("Criar / Atualizar recebimento"):
                with st.form(f"rec_form_{fase_id}", clear_on_submit=False):
                    status = st.selectbox(
                        "Status",
                        ["ABERTO","VENCIDO","PAGO","CANCELADO"],
                        index=(["ABERTO","VENCIDO","PAGO","CANCELADO"].index(rec["receb_status"]) if rec is not None else 0),
                        key=f"rec_st_{fase_id}"
                    )
                    vb = st.number_input(
                        "Valor base (R$)",
                        min_value=0.0, step=100.0,
                        value=(float(rec["valor_previsto"]) if rec is not None else float(f["valor_fase"])),
                        key=f"rec_vb_{fase_id}"
                    )
                    ac = st.number_input(
                        "Acréscimo (R$)",
                        min_value=0.0, step=50.0,
                        value=(float(rec["acrescimo"]) if rec is not None else 0.0),
                        key=f"rec_ac_{fase_id}"
                    )
                    venc = st.date_input(
                        "Vencimento (opcional)",
                        value=(rec["vencimento"] if rec is not None and rec["vencimento"] is not None else date.today()),
                        key=f"rec_venc_{fase_id}"
                    )
                    pago = st.date_input(
                        "Pago em (se PAGO)",
                        value=(rec["recebido_em"] if rec is not None and rec["recebido_em"] is not None else date.today()),
                        key=f"rec_pago_{fase_id}"
                    )
    
                    salvar = st.form_submit_button("Salvar recebimento", type="primary", use_container_width=True)
                    if salvar:
                        if rec is None:
                            exec_sql("""
                                insert into public.recebimentos
                                (obra_id, obra_fase_id, orcamento_id, status, valor_previsto, acrescimo, vencimento, recebido_em)
                                values (%s,%s,%s,%s,%s,%s,%s,%s);
                            """, (obra_id, fase_id, int(orc_id), status, float(vb), float(ac), venc, (pago if status=='PAGO' else None)))
                            st.success("Recebimento criado.")
                            st.rerun()
                        else:
                            exec_sql("""
                                update public.recebimentos
                                set status=%s, valor_previsto=%s, acrescimo=%s,
                                    vencimento=%s,
                                    recebido_em=%s
                                where id=%s;
                            """, (status, float(vb), float(ac), venc, (pago if status=='PAGO' else None), int(rec["receb_id"])))
                            st.success("Recebimento atualizado.")
                            st.rerun()

# ======================================================
# SEPOL - V1.2 Novas funcionalidades estáveis
# ======================================================
# ======================================================
# HOJE (60+ operacional)
# ======================================================
if menu == "HOJE":
    st.subheader("📅 HOJE")

    # KPIs (usa view do seu SQL V1)
    kpi = safe_df("select * from public.home_hoje_kpis;")
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
        st.info("Sem dados ainda.")

    st.divider()
    st.markdown("### Ações rápidas")
    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("Ir para Apontamentos", type="primary", on_click=go, args=("APONTAMENTOS",), use_container_width=True):
            st.session_state["menu"] = "APONTAMENTOS"
            st.rerun()
    with a2:
        if st.button("Ir para Financeiro", on_click=go, args=("FINANCEIRO",), use_container_width=True):            
            st.session_state["menu"] = "FINANCEIRO"
            st.rerun()
    with a3:
        if st.button("Ir para Obras", on_click=go, args=("OBRAS",), use_container_width=True):
            st.session_state["menu"] = "OBRAS"
            st.rerun()

# ======================================================
# APONTAMENTOS (estável + trava se pago)
# ======================================================
if menu == "APONTAMENTOS":
    st.subheader("📝 Apontamentos")
    st.caption("Regra: 1 apontamento por pessoa, por dia, por obra. Se errou, edite (se não estiver pago).")

    if "edit_ap" not in st.session_state:
        st.session_state["edit_ap"] = None

    df_pessoas = safe_df("select id,nome from public.pessoas where ativo=true order by nome;")
    df_obras = safe_df("select id,titulo from public.obras where ativo=true order by titulo;")

    if df_pessoas.empty or df_obras.empty:
        st.warning("Cadastre profissionais e obras primeiro.")
        st.stop()

    pessoa_ids = df_pessoas["id"].tolist()
    obra_ids = df_obras["id"].tolist()

    edit_id = st.session_state["edit_ap"]

    # ---------- NOVO ----------
    if edit_id is None:
        with st.form("form_ap_novo", clear_on_submit=True):
            c1, c2, c3 = st.columns([4, 4, 2])
            with c1:
                obra_id = st.selectbox(
                    "Obra",
                    obra_ids,
                    format_func=lambda x: df_obras.loc[df_obras["id"] == x, "titulo"].iloc[0],
                )
            with c2:
                pessoa_id = st.selectbox(
                    "Profissional",
                    pessoa_ids,
                    format_func=lambda x: df_pessoas.loc[df_pessoas["id"] == x, "nome"].iloc[0],
                )
            with c3:
                data_ap = st.date_input("Data", value=date.today())

            c4, c5, c6, c7 = st.columns([2, 2, 2, 4])
            with c4:
                tipo_dia = st.selectbox("Tipo do dia", ["NORMAL", "FERIADO", "SABADO", "DOMINGO"], index=0)
            with c5:
                valor_base = st.number_input("Valor base (R$)", min_value=0.0, step=50.0, value=0.0)
            with c6:
                desconto = st.number_input("Desconto (R$)", min_value=0.0, step=10.0, value=0.0)
            with c7:
                obs = st.text_input("Observação (opcional)")

            salvar = st.form_submit_button("Salvar apontamento", type="primary", use_container_width=True)
            if salvar:
                try:
                    exec_sql(
                        """
                        insert into public.apontamentos
                        (obra_id,pessoa_id,data,tipo_dia,valor_base,desconto_valor,observacao)
                        values (%s,%s,%s,%s,%s,%s,%s);
                        """,
                        (int(obra_id), int(pessoa_id), data_ap, tipo_dia, float(valor_base), float(desconto), obs.strip() or None),
                    )
                    st.success("Apontamento salvo.")
                    st.rerun()
                except psycopg2.errors.UniqueViolation:
                    st.warning("Já existe apontamento para essa pessoa nesse dia nessa obra.")
                    st.stop()

    # ---------- EDITAR ----------
    else:
        df_one = safe_df("select * from public.apontamentos where id=%s;", (int(edit_id),))
        if df_one.empty:
            st.session_state["edit_ap"] = None
            st.rerun()
        r = df_one.iloc[0]

        # trava se apontamento estiver ligado a pagamento PAGO
        lock = safe_df(
            """
            select exists (
              select 1
              from public.pagamento_itens pi
              join public.pagamentos p on p.id=pi.pagamento_id
              where pi.apontamento_id=%s and p.status='PAGO'
            ) as travado;
            """,
            (int(edit_id),),
        )
        travado = bool(lock.iloc[0]["travado"])

        if travado:
            st.warning("🔒 Este apontamento está ligado a pagamento PAGO. Não é possível editar/excluir.")
            if st.button("Voltar"):
                st.session_state["edit_ap"] = None
                st.rerun()
        else:
            with st.form("form_ap_edit", clear_on_submit=False):
                c1, c2, c3 = st.columns([4, 4, 2])
                with c1:
                    obra_id = st.selectbox(
                        "Obra",
                        obra_ids,
                        index=obra_ids.index(int(r["obra_id"])) if int(r["obra_id"]) in obra_ids else 0,
                        format_func=lambda x: df_obras.loc[df_obras["id"] == x, "titulo"].iloc[0],
                        key="ap_obra_edit",
                    )
                with c2:
                    pessoa_id = st.selectbox(
                        "Profissional",
                        pessoa_ids,
                        index=pessoa_ids.index(int(r["pessoa_id"])) if int(r["pessoa_id"]) in pessoa_ids else 0,
                        format_func=lambda x: df_pessoas.loc[df_pessoas["id"] == x, "nome"].iloc[0],
                        key="ap_pessoa_edit",
                    )
                with c3:
                    data_ap = st.date_input("Data", value=r["data"], key="ap_data_edit")

                c4, c5, c6, c7 = st.columns([2, 2, 2, 4])
                with c4:
                    tipo_dia = st.selectbox(
                        "Tipo do dia",
                        ["NORMAL", "FERIADO", "SABADO", "DOMINGO"],
                        index=["NORMAL", "FERIADO", "SABADO", "DOMINGO"].index(r["tipo_dia"]),
                        key="ap_tipo_edit",
                    )
                with c5:
                    valor_base = st.number_input("Valor base (R$)", min_value=0.0, step=50.0, value=float(r["valor_base"]), key="ap_vb_edit")
                with c6:
                    desconto = st.number_input("Desconto (R$)", min_value=0.0, step=10.0, value=float(r["desconto_valor"]), key="ap_desc_edit")
                with c7:
                    obs = st.text_input("Observação (opcional)", value=r["observacao"] or "", key="ap_obs_edit")

                b1, b2, b3 = st.columns(3)
                with b1:
                    salvar_alt = st.form_submit_button("Salvar alteração", type="primary", use_container_width=True)
                with b2:
                    cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)
                with b3:
                    excluir = st.form_submit_button("Excluir", use_container_width=True)

                if salvar_alt:
                    try:
                        exec_sql(
                            """
                            update public.apontamentos
                            set obra_id=%s, pessoa_id=%s, data=%s, tipo_dia=%s,
                                valor_base=%s, desconto_valor=%s, observacao=%s
                            where id=%s;
                            """,
                            (int(obra_id), int(pessoa_id), data_ap, tipo_dia, float(valor_base), float(desconto), obs.strip() or None, int(edit_id)),
                        )
                        st.success("Apontamento atualizado.")
                        st.session_state["edit_ap"] = None
                        st.rerun()
                    except psycopg2.errors.UniqueViolation:
                        st.warning("Conflito: já existe apontamento para essa pessoa nesse dia nessa obra.")
                        st.stop()

                if cancelar:
                    st.session_state["edit_ap"] = None
                    st.rerun()

                if excluir:
                    # remove itens e aponta (pagamento será recalculado ao gerar semana novamente)
                    exec_sql("delete from public.pagamento_itens where apontamento_id=%s;", (int(edit_id),))
                    exec_sql("delete from public.apontamentos where id=%s;", (int(edit_id),))
                    st.success("Apontamento excluído.")
                    st.session_state["edit_ap"] = None
                    st.rerun()

    st.divider()
    st.markdown("### Apontamentos recentes")
    df_recent = safe_df(
        """
        select a.id, a.data, p.nome as profissional, o.titulo as obra,
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
        limit 80;
        """
    )

    if df_recent.empty:
        st.info("Nenhum apontamento ainda.")
    else:
        for _, rr in df_recent.iterrows():
            colA, colB, colC, colD, colE = st.columns([2, 4, 3, 2, 2])
            with colA:
                st.write(f"**{rr['data']}**")
            with colB:
                st.write(rr["profissional"])
                if rr["travado_pago"]:
                    st.caption("🔒 pago")
            with colC:
                st.write(rr["obra"])
            with colD:
                st.write(rr["tipo_dia"])
            with colE:
                if st.button("EDITAR ✏️", key=f"ap_edit_{int(rr['id'])}", disabled=bool(rr["travado_pago"]), use_container_width=True):
                    st.session_state["edit_ap"] = int(rr["id"])
                    st.rerun()

# ======================================================
# FINANCEIRO (gerar, pagar, estornar, histórico)
# ======================================================
if menu == "FINANCEIRO":
    st.subheader("💰 Financeiro")

    # -------- Gerar pagamentos da semana --------
    st.markdown("## 1) Gerar pagamentos da semana")
    segunda = st.date_input("Segunda-feira da semana", value=(date.today() - timedelta(days=date.today().weekday())))
    if st.button("Gerar pagamentos desta semana", type="primary", use_container_width=True):
        exec_sql("select public.fn_gerar_pagamentos_semana(%s);", (segunda,))
        st.success("Pagamentos gerados/atualizados.")
        st.rerun()

    st.divider()

    # -------- Pagar / Estornar --------
    st.markdown("## 2) Pagar / Estornar")

    tab1, tab2 = st.tabs(["Pagar pendentes", "Histórico por profissional"])

    with tab1:
        st.markdown("### Pendentes para sexta")
        df_sexta = safe_df("select * from public.pagamentos_para_sexta;")
        if df_sexta.empty:
            st.info("Nada para pagar na próxima sexta.")
        else:
            data_pg = st.date_input("Data do pagamento", value=date.today(), key="data_pg_fin")
            for _, r in df_sexta.iterrows():
                c1, c2, c3 = st.columns([6, 2, 2])
                with c1:
                    st.write(f"**{r['pessoa_nome']}** • {r['tipo']}")
                with c2:
                    st.write(brl(r["valor_total"]))
                with c3:
                    if st.button("Pagar", key=f"pay_{int(r['id'])}", type="primary", use_container_width=True):
                        exec_sql("select public.fn_marcar_pagamento_pago(%s,%s,%s);", (int(r["id"]), st.session_state["usuario"], data_pg))
                        st.success("Pago!")
                        st.rerun()

        st.divider()
        st.markdown("### Extras pendentes (sábado/domingo)")
        df_extras = safe_df("select * from public.pagamentos_extras_pendentes;")
        if df_extras.empty:
            st.info("Sem extras pendentes.")
        else:
            data_pg2 = st.date_input("Data do pagamento (extras)", value=date.today(), key="data_pg_extras")
            for _, r in df_extras.iterrows():
                c1, c2, c3 = st.columns([6, 2, 2])
                with c1:
                    st.write(f"**{r['pessoa_nome']}** • EXTRA ({r.get('data_extra')})")
                with c2:
                    st.write(brl(r["valor_total"]))
                with c3:
                    if st.button("Pagar extra", key=f"pay_extra_{int(r['id'])}", type="primary", use_container_width=True):
                        exec_sql("select public.fn_marcar_pagamento_pago(%s,%s,%s);", (int(r["id"]), st.session_state["usuario"], data_pg2))
                        st.success("Extra pago!")
                        st.rerun()

        st.divider()
        st.markdown("### Estornar pagamento (se houve confusão)")
        df_pagos = safe_df("""
            select p.id, pe.nome as pessoa, p.tipo, p.valor_total, p.pago_em
            from public.pagamentos p
            join public.pessoas pe on pe.id=p.pessoa_id
            where p.status='PAGO'
            order by p.pago_em desc, p.id desc
            limit 200;
        """)
        if df_pagos.empty:
            st.info("Nenhum pagamento PAGO para estornar.")
        else:
            opcoes = df_pagos["id"].tolist()
            pid = st.selectbox(
                "Selecione um pagamento PAGO",
                opcoes,
                format_func=lambda x: f"#{x} • {df_pagos.loc[df_pagos['id']==x,'pessoa'].iloc[0]} • {df_pagos.loc[df_pagos['id']==x,'tipo'].iloc[0]} • {brl(df_pagos.loc[df_pagos['id']==x,'valor_total'].iloc[0])} • {df_pagos.loc[df_pagos['id']==x,'pago_em'].iloc[0]}",
            )
            motivo = st.text_input("Motivo do estorno (opcional)")
            if st.button("Estornar", use_container_width=True):
                exec_sql("select public.fn_estornar_pagamento(%s,%s,%s);", (int(pid), st.session_state["usuario"], motivo or None))
                st.success("Pagamento estornado (voltou para ABERTO).")
                st.rerun()

    with tab2:
        st.markdown("### Histórico por profissional (muito útil 60+)")
        df_prof = safe_df("select id,nome from public.pessoas order by nome;")
        if df_prof.empty:
            st.info("Cadastre profissionais primeiro.")
        else:
            prof_id = st.selectbox("Profissional", df_prof["id"].tolist(), format_func=lambda x: df_prof.loc[df_prof["id"]==x,"nome"].iloc[0])
            df_hist = safe_df("""
                select p.id, p.tipo, p.status, p.valor_total, p.referencia_inicio, p.referencia_fim, p.pago_em
                from public.pagamentos p
                where p.pessoa_id=%s
                order by coalesce(p.pago_em, p.referencia_fim, p.referencia_inicio) desc, p.id desc
                limit 200;
            """, (int(prof_id),))
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
