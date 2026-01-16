# utils/auth.py
import streamlit as st
from supabase_auth.errors import AuthApiError
from utils.db import rpc, sb_anon, sb  # <-- importante

def is_logged_in() -> bool:
    return "sb_session" in st.session_state and bool(st.session_state["sb_session"].get("access_token"))

def logout():
    try:
        # tenta invalidar no Supabase (ok falhar silenciosamente)
        sb_admin().auth.sign_out()
    except Exception:
        pass

    for k in ["sb_session", "perfil", "usuario_email", "usuario_id"]:
        if k in st.session_state:
            del st.session_state[k]

    st.rerun()

def load_profile():
    """
    Busca o perfil do usuário via RPC (fn_user_perfil).
    Depende de sessão válida em st.session_state["sb_session"].
    """
    try:
        perfil = rpc("fn_user_perfil")  # retorna string
        st.session_state["perfil"] = perfil
    except Exception:
        st.session_state["perfil"] = None

def require_login(logo_path: str | None = None):
    """
    Gate simples: se não logou, mostra UI de login e interrompe.
    """
    if not is_logged_in():
        login_ui(logo_path=logo_path)
        st.stop()

    if "perfil" not in st.session_state:
        load_profile()

    # Se não tiver perfil (não cadastrado/ativo na usuarios_app), bloqueia
    if not st.session_state.get("perfil"):
        st.error("Seu usuário não está habilitado no sistema (usuarios_app). Peça ao ADMIN para ativar.")
        if st.button("Sair"):
            logout()
        st.stop()

def login_ui(logo_path: str | None = None):
    st.markdown("## 🔐 SEPOL — Login")

    if logo_path:
        try:
            st.image(logo_path, width=160)
        except Exception:
            pass

    email = st.text_input("Email", key="login_email")
    senha = st.text_input("Senha", type="password", key="login_senha")

    c1, c2 = st.columns([2, 1])
    with c1:
        entrar = st.button("Entrar", type="primary", use_container_width=True)
    with c2:
        st.button("Limpar", use_container_width=True, on_click=_clear_login_fields)

    if entrar:
        email = (email or "").strip()
        senha = (senha or "")

        # ✅ validações locais (evita exception desnecessária)
        if "@" not in email or "." not in email:
            st.error("Informe um e-mail válido.")
            return
        if not senha.strip():
            st.error("Informe a senha.")
            return

        try:
            # ✅ login deve usar ANON
            res = sb_anon().auth.sign_in_with_password({"email": email, "password": senha})
            sess = res.session
            if not sess:
                st.error("Falha no login: sessão não retornada.")
                return

            st.session_state["sb_session"] = {
                "access_token": sess.access_token,
                "refresh_token": sess.refresh_token,
            }
            st.session_state["usuario_email"] = email
            st.session_state["usuario_id"] = res.user.id

            # carrega perfil (seu método)
            load_profile()

            st.success("Login realizado.")
            st.rerun()

        except AuthApiError as e:
            msg = str(e).lower()
            # ✅ mensagens mais úteis e sem stack trace gigante
            if "email not confirmed" in msg or "not confirmed" in msg or "confirm" in msg:
                st.error("Usuário não confirmado. Confirme o e-mail no Supabase Auth ou desative confirmação no DEV.")
            else:
                st.error("E-mail ou senha inválidos.")
            return

        except Exception:
            st.error("Falha no login (erro inesperado).")
            # se quiser logar no console sem poluir UI:
            # import traceback; print(traceback.format_exc())
            return

def _clear_login_fields():
    for k in ["login_email", "login_senha"]:
        if k in st.session_state:
            st.session_state[k] = ""

def logout_button():
    perfil = st.session_state.get("perfil", "—")
    email = st.session_state.get("usuario_email", "")
    st.caption(f"👤 {email} • Perfil: **{perfil}**")
    if st.button("Sair", use_container_width=True):
        logout()
