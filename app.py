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
col_title, col_log = st.columns([6,1])
with col_title:
    st.markdown("## 🏗️ SEPOL - Controle de Obras")
with col_log:
    st.image("assets/logo.png", use_container_width=True)

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
            df_one = safe_df("q_clientes")
            df_one = df_one.loc[df_one["id"] == int(edit_id)]
            row = df_one.iloc[0] if not df_one.empty else None

        with st.form("cliente_form", clear_on_submit=True):
            nome = st.text_input("Nome", value=(row["nome"] if row is not None else ""))
            telefone = st.text_input("Telefone (opcional)", value=(row.get("telefone") if row is not None else "") or "")
            endereco = st.text_input("Endereco (opcional)", value=(row.get("endereco") if row is not None else "") or "")
            c1, c2, c3 = st.columns(3)
            salvar = c1.form_submit_button("Salvar", type="primary", use_container_width=True)
            cancelar = c2.form_submit_button("Cancelar edicao", use_container_width=True, disabled=(edit_id is None))
            limpar = c3.form_submit_button("Limpar", use_container_width=True)

            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if edit_id is None:
                    qexec("i_cliente", {"nome": nome.strip(), "telefone": telefone.strip() or None, "endereco": endereco.strip() or None})
                    st.success("Cliente cadastrado!")
                else:
                    qexec("u_cliente", {"id": int(edit_id), "nome": nome.strip(), "telefone": telefone.strip() or None, "endereco": endereco.strip() or None})
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
                        qexec("u_cliente_set_ativo", {"id": rid, "ativo": not bool(rr.get("ativo"))})
                        st.rerun()

    # ---------- PROFISSIONAIS ----------
    with t2:
        st.subheader("Profissionais")

        if "edit_prof_id" not in st.session_state:
            st.session_state["edit_prof_id"] = None

        edit_id = st.session_state["edit_prof_id"]
        row = None
        if edit_id:
            df_one = safe_df("q_pessoas")
            df_one = df_one.loc[df_one["id"] == int(edit_id)]
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
            observacao = st.text_area("Observacao (opcional)", value=(row.get("observacao") if row is not None else "") or "")
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
                        "i_pessoa",
                        {
                            "nome": nome.strip(),
                            "tipo": tipo,
                            "telefone": telefone.strip() or None,
                            "diaria_base": float(diaria) if diaria > 0 else None,
                            "observacao": observacao.strip() or None,
                        },
                    )
                    st.success("Profissional cadastrado!")
                else:
                    qexec(
                        "u_pessoa",
                        {
                            "id": int(edit_id),
                            "nome": nome.strip(),
                            "tipo": tipo,
                            "telefone": telefone.strip() or None,
                            "diaria_base": float(diaria) if diaria > 0 else None,
                            "observacao": observacao.strip() or None,
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
        df = safe_df("q_pessoas")
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
                        qexec("u_pessoa_set_ativo", {"id": rid, "ativo": not bool(rr.get("ativo"))})
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
        obra_df = df.loc[df["id"] == int(obra_sel)]
        d = obra_df.iloc[0] if not obra_df.empty else {}
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
        qexec("call_gerar_pagamentos_semana", {"segunda": segunda})
        st.success("Pagamentos gerados/atualizados.")
        st.rerun()

    st.divider()
    st.markdown("## 2) Pagamentos pendentes")
    df = safe_df("q_pagamentos_pendentes")
    st.dataframe(df, use_container_width=True, hide_index=True)

# =========================
# CONFIG (ADMIN)
# =========================
if menu == "CONFIG" and perfil == "ADMIN":
    st.subheader("⚙️ Configurações")
    st.caption("Gestão de usuários do sistema (ADMIN/OPERAÇÃO).")
    
    # --------- Helpers UI ----------
    def refresh_users():
        st.session_state["users_df"] = safe_df("q_users")
    
    if "users_df" not in st.session_state:
        refresh_users()
    
    df_users = st.session_state["users_df"]
    
    # --------- Criar usuário ----------
    st.markdown("## 1) Criar novo usuário")
    with st.form("form_user_create", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            new_usuario = st.text_input("Usuário", placeholder="ex: maria")
        with c2:
            new_perfil = st.selectbox("Perfil", ["ADMIN", "OPERACAO"], index=1)
        with c3:
            new_senha = st.text_input("Senha inicial", type="password", placeholder="defina uma senha")
    
        criar = st.form_submit_button("Criar usuário", type="primary", use_container_width=True)
        if criar:
            if not new_usuario.strip():
                st.warning("Informe o usuário.")
                st.stop()
            if not new_senha.strip() or len(new_senha.strip()) < 6:
                st.warning("Defina uma senha com pelo menos 6 caracteres.")
                st.stop()
    
            try:
                qexec("i_user", {
                    "usuario": new_usuario.strip().lower(),
                    "senha": new_senha.strip(),
                    "perfil": new_perfil,
                })
                st.success("Usuário criado.")
                refresh_users()
                st.rerun()
            except Exception as e:
                st.error("Falha ao criar usuário (talvez já exista).")
                st.exception(e)
    
    st.divider()
    
    # --------- Lista e ações ----------
    st.markdown("## 2) Usuários cadastrados")
    if df_users.empty:
        st.info("Nenhum usuário ainda.")
        st.stop()
    
    # seleção simples
    ids = df_users["id"].tolist()
    sel_id = st.selectbox(
        "Selecionar usuário",
        options=ids,
        format_func=lambda x: f"{df_users.loc[df_users['id']==x,'usuario'].iloc[0]} • {df_users.loc[df_users['id']==x,'perfil'].iloc[0]} • {'ATIVO' if bool(df_users.loc[df_users['id']==x,'ativo'].iloc[0]) else 'INATIVO'}",
        key="cfg_user_sel",
    )
    
    user_row = df_users[df_users["id"] == sel_id].iloc[0]
    u_usuario = user_row["usuario"]
    u_perfil = user_row["perfil"]
    u_ativo = bool(user_row["ativo"])
    
    cA, cB, cC, cD = st.columns([3, 2, 2, 3])
    with cA:
        st.metric("Usuário", str(u_usuario))
    with cB:
        st.metric("Perfil", str(u_perfil))
    with cC:
        st.metric("Status", "ATIVO" if u_ativo else "INATIVO")
    with cD:
        st.caption("Ações rápidas")
    
    col1, col2 = st.columns(2)
    
    # ---- Ativar/Inativar ----
    with col1:
        label = "Inativar" if u_ativo else "Ativar"
        if st.button(label, use_container_width=True):
            try:
                qexec("u_user_set_ativo", {"id": sel_id, "ativo": (not u_ativo)})
                st.success("Atualizado.")
                refresh_users()
                st.rerun()
            except Exception as e:
                st.error("Falha ao atualizar status.")
                st.exception(e)
    
    # ---- Reset senha ----
    with col2:
        if st.button("Resetar senha", type="primary", use_container_width=True):
            st.session_state["reset_user_id"] = sel_id
            st.session_state["reset_user_nome"] = u_usuario
            st.session_state["reset_open"] = True
    
    # Modal simples (sem st.dialog, para compatibilidade)
    if st.session_state.get("reset_open"):
        st.divider()
        st.markdown(f"### 🔑 Resetar senha — **{st.session_state.get('reset_user_nome','')}**")
    
        with st.form("form_reset_senha", clear_on_submit=True):
            nova1 = st.text_input("Nova senha", type="password")
            nova2 = st.text_input("Confirmar nova senha", type="password")
    
            b1, b2 = st.columns(2)
            with b1:
                ok = st.form_submit_button("Salvar nova senha", type="primary", use_container_width=True)
            with b2:
                cancel = st.form_submit_button("Cancelar", use_container_width=True)
    
            if cancel:
                st.session_state["reset_open"] = False
                st.rerun()
    
            if ok:
                if not nova1 or len(nova1) < 6:
                    st.warning("Senha deve ter pelo menos 6 caracteres.")
                    st.stop()
                if nova1 != nova2:
                    st.warning("As senhas não conferem.")
                    st.stop()
    
                try:
                    qexec("u_user_reset_senha", {"id": st.session_state["reset_user_id"], "senha": nova1})
                    st.success("Senha atualizada.")
                    st.session_state["reset_open"] = False
                    refresh_users()
                    st.rerun()
                except Exception as e:
                    st.error("Falha ao resetar senha.")
                    st.exception(e)
    
    st.divider()
    
    # tabela 60+ (visível)
    st.markdown("## 3) Visão geral")
    st.dataframe(
        df_users[["usuario", "perfil", "ativo", "criado_em"]],
        use_container_width=True,
        hide_index=True
    )
    
    st.divider()
    
    # Auditoria do BD
    st.markdown("## Auditoria (ultimos 200)")
    df = safe_df("q_auditoria_ultimos", {"limite": 200})
    st.dataframe(df, use_container_width=True, hide_index=True)
