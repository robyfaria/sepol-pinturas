import streamlit as st
from utils.functions import tela_home, safe_df, q

st.set_page_config(page_title="SEPOL - Pinturas", layout="wide")

# Header + logo
col_title, col_logo = st.columns([6, 1])
with col_title:
    st.markdown("## 🏗️ SEPOL - Sistema de Gestão")
with col_logo:
    st.image("assets/logo.png", use_container_width=True)

st.divider()

# Sidebar
with st.sidebar:
    st.header("Menu")
    if "menu" not in st.session_state:
        st.session_state["menu"] = "HOME"

    st.session_state["menu"] = st.radio(
        "Navegação",
        ["HOME", "CADASTROS", "OBRAS", "FINANCEIRO"],
        index=["HOME", "CADASTROS", "OBRAS", "FINANCEIRO"].index(st.session_state["menu"]),
    )

menu = st.session_state["menu"]

# Router (sem funções no app.py além do import)
if menu == "HOME":
    tela_home()

elif menu == "CADASTROS":
    st.subheader("CADASTROS")
    st.caption("Cliente + Profissionais (PINTOR/AJUDANTE/TERCEIRO) na mesma tela.")
    st.info("Implementar em utils/functions.py: tela_cadastros()")

elif menu == "OBRAS":
    st.subheader("OBRAS")
    st.caption("Obra → Orçamento → Fases → Serviços")
    st.info("Implementar em utils/functions.py: tela_obras()")

elif menu == "FINANCEIRO":
    st.subheader("FINANCEIRO")
    st.caption("Pagamentos + Recebimentos")
    st.info("Implementar em utils/functions.py: tela_financeiro()")
