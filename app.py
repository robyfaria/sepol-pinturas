import streamlit as st

from utils.functions import (
    tela_home,
    tela_cadastros,
    tela_obras,
    tela_financeiro,
)

st.set_page_config(page_title="SEPOL - Pinturas", layout="wide")

# Header + logo
col_title, col_logo = st.columns([6, 1])
with col_title:
    st.markdown("## 🏗️ SEPOL - Sistema de Gestão (V1)")
    st.caption("Fluxo simples para uso diário (60+): Cadastros → Obras → Financeiro")
with col_logo:
    try:
        st.image("assets/logo.png", use_container_width=True)
    except Exception:
        pass

st.divider()

# Sidebar
with st.sidebar:
    st.header("Menu")
    if "menu" not in st.session_state:
        st.session_state["menu"] = "HOME"

    menu = st.radio(
        "Navegação",
        ["HOME", "CADASTROS", "OBRAS", "FINANCEIRO"],
        index=["HOME", "CADASTROS", "OBRAS", "FINANCEIRO"].index(st.session_state["menu"]),
        key="menu_radio"
    )
    st.session_state["menu"] = menu

# Router
if st.session_state["menu"] == "HOME":
    tela_home()

elif st.session_state["menu"] == "CADASTROS":
    tela_cadastros()

elif st.session_state["menu"] == "OBRAS":
    tela_obras()

elif st.session_state["menu"] == "FINANCEIRO":
    tela_financeiro()
