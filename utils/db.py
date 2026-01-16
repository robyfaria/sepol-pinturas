# utils/db.py
import streamlit as st
from supabase import create_client

def sb_anon():
    """
    Cliente ANON (não logado).
    Use para login e leitura pública (quando permitido).
    """
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"],
    )

def sb_admin():
    """
    Cliente SERVICE ROLE (admin).
    Use SOMENTE no backend/admin: criar usuário, resetar senha, etc.
    NUNCA use para login do usuário final.
    """
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"],
    )

def sb():
    """
    Cliente autenticado (com sessão do usuário) – RLS funciona aqui.
    Requer st.session_state["sb_session"] com access_token/refresh_token.
    """
    client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"],
    )

    sess = st.session_state.get("sb_session")
    if not sess:
        return client

    access_token = sess.get("access_token")
    refresh_token = sess.get("refresh_token")

    if access_token and refresh_token:
        client.auth.set_session(access_token, refresh_token)

    return client

def rpc(fn_name: str, params: dict | None = None):
    """Chama RPC no Supabase (RLS aplicado) e retorna .data"""
    res = sb().rpc(fn_name, params or {}).execute()
    return res.data

def table_select(table: str, columns: str = "*", filters: dict | None = None, order: tuple | None = None, limit: int | None = None):
    """
    Select simples com Supabase.
    filters: {"ativo": True, "id": 1} -> eq
    order: ("criado_em", True) -> descending True/False
    """
    q = sb().table(table).select(columns)
    if filters:
        for k, v in filters.items():
            q = q.eq(k, v)
    if order:
        col, desc = order
        q = q.order(col, desc=bool(desc))
    if limit:
        q = q.limit(int(limit))
    return q.execute().data

def table_insert(table: str, payload: dict):
    res = sb().table(table).insert(payload).execute()
    return res.data

def table_update(table: str, payload: dict, eq_filters: dict):
    q = sb().table(table).update(payload)
    for k, v in eq_filters.items():
        q = q.eq(k, v)
    res = q.execute()
    return res.data

def table_delete(table: str, eq_filters: dict):
    q = sb().table(table).delete()
    for k, v in eq_filters.items():
        q = q.eq(k, v)
    res = q.execute()
    return res.data
