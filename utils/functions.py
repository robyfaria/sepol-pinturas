from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st

# ======================================================
# SQL loader (arquivo sql/query.sql)
# ======================================================

def load_named_sql(sql_path: str | Path) -> Dict[str, str]:
    """Carrega queries nomeadas.

    Formato esperado:
      -- name: <nome>
      <sql...>

    Retorna {nome: sql}.
    """
    text = Path(sql_path).read_text(encoding="utf-8")
    chunks = re.split(r"^--\s*name:\s*([A-Za-z0-9_\-]+)\s*$", text, flags=re.M)
    # chunks = [pre, name1, sql1, name2, sql2, ...]
    out: Dict[str, str] = {}
    i = 1
    while i < len(chunks):
        name = chunks[i].strip()
        sql = chunks[i + 1].strip()
        if name:
            out[name] = sql
        i += 2
    return out


@st.cache_resource
def get_queries() -> Dict[str, str]:
    return load_named_sql(Path(__file__).resolve().parents[1] / "sql" / "query.sql")


# ======================================================
# DB helpers
# ======================================================


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        st.secrets["DATABASE_URL"],
        cursor_factory=RealDictCursor,
        connect_timeout=10,
        sslmode="require",
    )


@st.cache_resource
def get_conn() -> psycopg2.extensions.connection:
    return _connect()


def _ensure_conn() -> psycopg2.extensions.connection:
    conn = get_conn()
    try:
        if conn.closed:
            raise psycopg2.InterfaceError("connection closed")
        return conn
    except Exception:
        # reseta cache e reconecta
        get_conn.clear()
        return get_conn()


def _apply_session_settings(cur: psycopg2.extensions.cursor) -> None:
    auth = st.session_state.get("auth") if "auth" in st.session_state else None
    if auth and auth.get("auth_user_id"):
        claims = json.dumps({"sub": str(auth["auth_user_id"]), "role": "authenticated"})
        role = "authenticated"
        usuario = auth.get("usuario", "")
        perfil = auth.get("perfil", "")
    else:
        claims = json.dumps({"role": "anon"})
        role = "anon"
        usuario = ""
        perfil = ""
    cur.execute("select set_config('request.jwt.claims', %s, true);", (claims,))
    cur.execute("select set_config('role', %s, true);", (role,))
    cur.execute("select set_config('app.usuario', %s, true);", (usuario,))
    cur.execute("select set_config('app.perfil', %s, true);", (perfil,))


def query_df(sql: str, params: Optional[dict | tuple] = None) -> pd.DataFrame:
    conn = _ensure_conn()
    try:
        with conn.cursor() as cur:
            _apply_session_settings(cur)
            cur.execute(sql, params or {})
            rows = cur.fetchall()
        return pd.DataFrame(rows)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def exec_sql(sql: str, params: Optional[dict | tuple] = None) -> None:
    conn = _ensure_conn()
    try:
        with conn.cursor() as cur:
            _apply_session_settings(cur)
            cur.execute(sql, params or {})
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def qdf(name: str, params: Optional[dict] = None) -> pd.DataFrame:
    qs = get_queries()
    if name not in qs:
        raise KeyError(f"Query nao encontrada: {name}")
    return query_df(qs[name], params or {})


def qexec(name: str, params: Optional[dict] = None) -> None:
    qs = get_queries()
    if name not in qs:
        raise KeyError(f"Query nao encontrada: {name}")
    exec_sql(qs[name], params or {})


def safe_df(name: str, params: Optional[dict] = None, msg: str = "Falha ao consultar o banco.") -> pd.DataFrame:
    try:
        return qdf(name, params)
    except Exception as e:
        st.error(msg)
        st.exception(e)
        st.stop()


# ======================================================
# Auth
# ======================================================


def check_password(usuario: str, senha: str) -> Tuple[bool, Optional[dict]]:
    """Valida senha usando pgcrypto (crypt).

    Retorna (ok, user_row_dict).
    """
    df = qdf("q_login_user", {"usuario": usuario})
    if df.empty:
        return False, None
    u = dict(df.iloc[0])
    if not u.get("ativo"):
        return False, None

    conn = _ensure_conn()
    with conn.cursor() as cur:
        cur.execute(
            "select (crypt(%s, %s) = %s) as ok;",
            (senha, u["senha_hash"], u["senha_hash"]),
        )
        ok = bool(cur.fetchone()["ok"])
    if not ok:
        return False, None
    return True, u


def hash_password(senha: str) -> str:
    conn = _ensure_conn()
    with conn.cursor() as cur:
        cur.execute("select crypt(%s, gen_salt('bf')) as h;", (senha,))
        return cur.fetchone()["h"]


def require_login() -> dict:
    """Garante sessao autenticada. Retorna user dict."""
    if "auth" not in st.session_state:
        st.session_state["auth"] = None

    if st.session_state["auth"] is not None:
        return st.session_state["auth"]

    st.caption("Login")

    with st.form("login", clear_on_submit=False):
        usuario = st.text_input("Usuario")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        if entrar:
            ok, u = check_password(usuario.strip(), senha)
            if not ok:
                st.error("Usuario ou senha invalidos.")
                st.stop()
            if not u.get("auth_user_id"):
                st.error("Usuário sem vinculo ao Supabase Auth. Atualize o auth_user_id no cadastro.")
                st.stop()
            st.session_state["auth"] = {
                "id": u["id"],
                "usuario": u["usuario"],
                "perfil": u["perfil"],
                "auth_user_id": u.get("auth_user_id"),
            }
            st.rerun()

    st.stop()


def logout() -> None:
    st.session_state["auth"] = None
    st.rerun()


# ======================================================
# UI helpers
# ======================================================

def brl(v: Any) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def goto(menu: str) -> None:
    st.session_state["_menu_target"] = menu


def apply_pending_nav(default: str = "HOME") -> str:
    """Aplica navegacao pendente sem quebrar widgets.

    Use antes de construir o sidebar.
    """
    if "menu" not in st.session_state:
        st.session_state["menu"] = default
    if "_menu_target" in st.session_state and st.session_state["_menu_target"]:
        st.session_state["menu"] = st.session_state.pop("_menu_target")
    return st.session_state["menu"]


