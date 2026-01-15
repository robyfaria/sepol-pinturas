import streamlit as st
import pandas as pd
from datetime import date, timedelta

from utils.functions import (
    require_login,
    logout,
    safe_df,
    qexec,
    brl,
    apply_pending_nav,
    goto,
)

st.set_page_config(page_title="SEPOL - Pinturas", layout="wide")

# =========================
# Auth
# =========================
auth = require_login()
perfil = auth["perfil"]
usuario = auth["usuario"]

# =========================
# Sidebar (com controle de permissao)
# =========================
menu_atual = apply_pending_nav("HOME")

with st.sidebar:
    st.image("assets/logo.png", width=140) if False else None  # opcional: crie assets/logo.png
    st.markdown("### SEPOL")
    st.caption(f"Logado: **{usuario}** ({perfil})")

    opcoes = ["HOME", "CADASTROS", "OBRAS"]
    if perfil == "ADMIN":
        opcoes += ["FINANCEIRO", "CONFIG"]

    st.selectbox("Menu", opcoes, key="menu")

    if st.button("Sair", use_container_width=True):
        logout()

menu = st.session_state["menu"]

# =========================
# HOME
# =========================
if menu == "HOME":
    st.title("🏠 Home")
    st.caption("Visao rapida")

    # KPIs (se as views existirem)
    try:
        kpi = safe_df("q_home_kpis")
        r = kpi.iloc[0] if not kpi.empty else None
        if r is not None:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Hoje", str(r.get("hoje")))
            c2.metric("Sexta", str(r.get("sexta")))
            c3.metric("Fases em andamento", int(r.get("fases_em_andamento", 0)))
            c4.metric("A receber", brl(r.get("recebimentos_pendentes_total", 0)))
    except Exception:
        st.info("KPIs ainda nao configurados neste banco.")

    st.divider()
    st.markdown("### Acoes rapidas")
    cA, cB, cC = st.columns(3)
    with cA:
        if st.button("Apontamentos", type="primary", use_container_width=True):
            goto("OBRAS")
            st.rerun()
    with cB:
        if perfil == "ADMIN" and st.button("Financeiro", use_container_width=True):
            goto("FINANCEIRO")
            st.rerun()
    with cC:
        if st.button("Cadastros", use_container_width=True):
            goto("CADASTROS")
            st.rerun()

# =========================
# CADASTROS (clientes + profissionais numa tela)
# =========================
if menu == "CADASTROS":
    st.title("🗂️ Cadastros")
    st.caption("Tudo em uma tela: Cliente + Profissionais")

    t1, t2 = st.tabs(["Clientes", "Profissionais"])

    # ---------- CLIENTES ----------
    with t1:
        st.subheader("Clientes")

        if "edit_cliente_id" not in st.session_state:
            st.session_state["edit_cliente_id"] = None

        edit_id = st.session_state["edit_cliente_id"]
        row = None
        if edit_id:
            df_one = safe_df("q_cliente_by_id", {"id": int(edit_id)})
            row = df_one.iloc[0] if not df_one.empty else None

        with st.form("cliente_form", clear_on_submit=True):
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""))
            telefone = st.text_input("Telefone (opcional)", value=(row.get("telefone") if row is not None else "") or "")
            endereco = st.text_input("Endereco (opcional)", value=(row.get("endereco") if row is not None else "") or "")
            ativo = st.checkbox("Ativo", value=(bool(row.get("ativo")) if row is not None else True))

            c1, c2, c3 = st.columns(3)
            salvar = c1.form_submit_button("Salvar", type="primary", use_container_width=True)
            cancelar = c2.form_submit_button("Cancelar edicao", use_container_width=True, disabled=(edit_id is None))
            limpar = c3.form_submit_button("Limpar", use_container_width=True)

            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if edit_id is None:
                    qexec("i_cliente", {"nome": nome.strip(), "telefone": telefone.strip() or None, "endereco": endereco.strip() or None, "ativo": ativo})
                    st.success("Cliente cadastrado!")
                else:
                    qexec("u_cliente", {"id": int(edit_id), "nome": nome.strip(), "telefone": telefone.strip() or None, "endereco": endereco.strip() or None, "ativo": ativo})
                    st.success("Cliente atualizado!")
                    st.session_state["edit_cliente_id"] = None
                st.rerun()

            if cancelar:
                st.session_state["edit_cliente_id"] = None
                st.rerun()

            if limpar:
                st.rerun()

        st.divider()
        df = safe_df("q_clientes")
        if df.empty:
            st.info("Nenhum cliente.")
        else:
            for _, rr in df.iterrows():
                rid = int(rr["id"])
                ca, cb, cc = st.columns([5, 2, 2])
                with ca:
                    st.write(f"**{rr['nome']}**")
                    st.caption((rr.get("telefone") or "") + (" • " + rr.get("endereco") if rr.get("endereco") else ""))
                with cb:
                    st.write("ATIVO" if rr.get("ativo") else "INATIVO")
                with cc:
                    b1, b2 = st.columns(2)
                    if b1.button("Editar", key=f"cli_ed_{rid}"):
                        st.session_state["edit_cliente_id"] = rid
                        st.rerun()
                    if b2.button("Ativar/Inativar", key=f"cli_tg_{rid}"):
                        qexec("toggle_cliente", {"id": rid})
                        st.rerun()

    # ---------- PROFISSIONAIS ----------
    with t2:
        st.subheader("Profissionais")

        if "edit_prof_id" not in st.session_state:
            st.session_state["edit_prof_id"] = None

        edit_id = st.session_state["edit_prof_id"]
        row = None
        if edit_id:
            df_one = safe_df("q_prof_by_id", {"id": int(edit_id)})
            row = df_one.iloc[0] if not df_one.empty else None

        with st.form("prof_form", clear_on_submit=True):
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""))
            tipo = st.selectbox(
                "Tipo",
                ["PINTOR", "AJUDANTE", "TERCEIRO"],
                index=(["PINTOR", "AJUDANTE", "TERCEIRO"].index(row["tipo"]) if row is not None else 0),
            )
            telefone = st.text_input("Telefone (opcional)", value=(row.get("telefone") if row is not None else "") or "")
            diaria = st.number_input("Diaria base (opcional)", min_value=0.0, step=10.0, value=float(row.get("diaria_base") or 0) if row is not None else 0.0)
            ativo = st.checkbox("Ativo", value=(bool(row.get("ativo")) if row is not None else True))

            c1, c2, c3 = st.columns(3)
            salvar = c1.form_submit_button("Salvar", type="primary", use_container_width=True)
            cancelar = c2.form_submit_button("Cancelar edicao", use_container_width=True, disabled=(edit_id is None))
            limpar = c3.form_submit_button("Limpar", use_container_width=True)

            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if edit_id is None:
                    qexec(
                        "i_prof",
                        {
                            "nome": nome.strip(),
                            "tipo": tipo,
                            "telefone": telefone.strip() or None,
                            "diaria_base": float(diaria) if diaria > 0 else None,
                            "ativo": ativo,
                        },
                    )
                    st.success("Profissional cadastrado!")
                else:
                    qexec(
                        "u_prof",
                        {
                            "id": int(edit_id),
                            "nome": nome.strip(),
                            "tipo": tipo,
                            "telefone": telefone.strip() or None,
                            "diaria_base": float(diaria) if diaria > 0 else None,
                            "ativo": ativo,
                        },
                    )
                    st.success("Profissional atualizado!")
                    st.session_state["edit_prof_id"] = None
                st.rerun()

            if cancelar:
                st.session_state["edit_prof_id"] = None
                st.rerun()

            if limpar:
                st.rerun()

        st.divider()
        df = safe_df("q_profissionais")
        if df.empty:
            st.info("Nenhum profissional.")
        else:
            for _, rr in df.iterrows():
                rid = int(rr["id"])
                ca, cb, cc = st.columns([5, 2, 2])
                with ca:
                    st.write(f"**{rr['nome']}**")
                    st.caption(f"{rr['tipo']}" + (f" • {rr.get('telefone')}" if rr.get("telefone") else ""))
                with cb:
                    st.write("ATIVO" if rr.get("ativo") else "INATIVO")
                with cc:
                    b1, b2 = st.columns(2)
                    if b1.button("Editar", key=f"pr_ed_{rid}"):
                        st.session_state["edit_prof_id"] = rid
                        st.rerun()
                    if b2.button("Ativar/Inativar", key=f"pr_tg_{rid}"):
                        qexec("toggle_prof", {"id": rid})
                        st.rerun()

# =========================
# OBRAS
# =========================
if menu == "OBRAS":
    st.title("🏗️ Obras")
    st.caption("Acompanhe as obras e detalhes principais.")

    df = safe_df("q_obras")
    if df.empty:
        st.info("Nenhuma obra cadastrada ainda.")
    else:
        obra_ids = df["id"].tolist()
        if "obra_sel" not in st.session_state or st.session_state["obra_sel"] not in obra_ids:
            st.session_state["obra_sel"] = int(obra_ids[0])
        obra_sel = st.selectbox(
            "Obra selecionada",
            obra_ids,
            index=obra_ids.index(st.session_state["obra_sel"]),
            format_func=lambda x: f"#{int(x)} • {df.loc[df['id']==x,'titulo'].iloc[0]}",
            key="obra_sel",
        )

        st.subheader("Detalhes")
        d = safe_df("q_obra_by_id", {"id": int(obra_sel)}).iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Cliente", d.get("cliente_nome", ""))
        c2.metric("Status", d.get("status", ""))
        c3.metric("Ativo", "SIM" if d.get("ativo") else "NAO")

        st.info("Mais opcoes desta obra aparecem conforme os cadastros forem preenchidos.")

# =========================
# FINANCEIRO (ADMIN only)
# =========================
if menu == "FINANCEIRO" and perfil == "ADMIN":
    st.title("💰 Financeiro")

    st.markdown("## 1) Gerar pagamentos da semana")
    segunda = st.date_input("Segunda-feira", value=(date.today() - timedelta(days=date.today().weekday())))
    if st.button("Gerar pagamentos desta semana", type="primary", use_container_width=True):
        # A funcao no banco ja bloqueia reabrir pagamentos PAGO.
        qexec("call_gerar_pag_semana", {"segunda": segunda})
        st.success("Pagamentos gerados/atualizados.")
        st.rerun()

    st.divider()
    st.markdown("## 2) Pagamentos pendentes")
    df = safe_df("q_pagamentos_pendentes")
    st.dataframe(df, use_container_width=True, hide_index=True)

# =========================
# CONFIG (ADMIN only)
# =========================
if menu == "CONFIG" and perfil == "ADMIN":
    st.title("⚙️ Configuracoes")
    st.caption("Logs de auditoria + gestao de usuarios")

    st.markdown("## Auditoria (ultimos 200)")
    df = safe_df("q_auditoria_ultimos", {"limite": 200})
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.info("Gestao de usuarios (criar/resetar senha) ficara disponivel aqui.")
