# ===== PATCH MÍNIMO (app.py) =====
# Cole este bloco no TOPO do app.py (logo após os imports)
# e substitua seu sidebar/menu atual por este.

import streamlit as st

from utils.auth import require_login, logout_button
from utils.db import table_select

# -------------------------
# Config (logo + título)
# -------------------------
st.set_page_config(page_title="SEPOL - Pinturas", layout="wide")

# Ajuste o caminho do seu logo (ex: "assets/logo.png")
LOGO_PATH = "assets/logo.png"

# Header simples 60+
c1, c2 = st.columns([6, 1])
with c1:
    st.title("SEPOL - Pinturas")
with c2:
    try:
        st.image(LOGO_PATH, width=90)
    except Exception:
        pass

# -------------------------
# Login obrigatório
# -------------------------
require_login(logo_path=LOGO_PATH)

perfil = st.session_state.get("perfil", "OPERACAO")

# -------------------------
# Menu por perfil (RLS + UI)
# OPERACAO não vê CONFIG, FINANCEIRO, HOME (dashboard)
# -------------------------
MENU_ADMIN = ["HOME", "CADASTROS", "OBRAS", "FINANCEIRO", "CONFIG"]
MENU_OPER  = ["CADASTROS", "OBRAS"]

allowed = MENU_ADMIN if perfil == "ADMIN" else MENU_OPER

# Inicializa menu
if "menu" not in st.session_state or st.session_state["menu"] not in allowed:
    st.session_state["menu"] = allowed[0]

# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    st.header("Menu")
    st.selectbox("Tela", allowed, key="menu")
    st.divider()
    logout_button()

menu = st.session_state["menu"]

# =========================
# TELAS (stub mínimo)
# =========================

if menu == "HOME":
    st.subheader("🏠 Home (ADMIN)")
    st.info("Aqui entra seu dashboard. (Por enquanto: stub.)")

if menu == "CADASTROS":
    st.subheader("🧾 Cadastros (tudo em 1 tela)")
    st.caption("Clientes + Profissionais (público 60+)")

    colA, colB = st.columns(2)

    with colA:
        st.markdown("### Clientes (lista)")
        try:
            clientes = table_select("clientes", columns="id,nome,telefone,ativo,criado_em", order=("id", True), limit=200)
            st.dataframe(clientes, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error("Falha ao listar clientes (RLS/DB).")
            st.exception(e)

    with colB:
        st.markdown("### Profissionais (lista)")
        try:
            pessoas = table_select("pessoas", columns="id,nome,tipo,telefone,ativo,criado_em", order=("id", True), limit=200)
            st.dataframe(pessoas, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error("Falha ao listar profissionais (RLS/DB).")
            st.exception(e)

if menu == "OBRAS":
    st.subheader("🏗️ Obras")
    st.info("Stub mínimo. Aqui você pluga sua tela de Obras/Orçamento/Fases/Serviços.")

if menu == "FINANCEIRO":
    st.subheader("💰 Financeiro (ADMIN)")
    st.info("Stub mínimo. Aqui você pluga Pagamentos/Recebimentos.")

if menu == "CONFIG":
    st.subheader("⚙️ Config (ADMIN)")
    st.info("Stub mínimo. Aqui você pluga gestão de usuários + auditoria.")
