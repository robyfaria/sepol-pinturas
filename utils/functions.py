import os
import re
from datetime import date, timedelta

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

import streamlit as st


# =========================================================
# DB
# =========================================================
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        st.secrets["DATABASE_URL"],
        cursor_factory=RealDictCursor,
        connect_timeout=10,
    )

def _ensure_conn_alive(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("select 1;")
        return conn
    except Exception:
        return get_conn()

def query_df(sql, params=None):
    conn = _ensure_conn_alive(get_conn())
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
        return pd.DataFrame(rows)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

def query_one(sql, params=None):
    df = query_df(sql, params)
    if df.empty:
        return None
    return dict(df.iloc[0])

def exec_sql(sql, params=None):
    conn = _ensure_conn_alive(get_conn())
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    except psycopg2.InterfaceError:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# =========================================================
# SQL Registry (sql/queries.sql)
# =========================================================
@st.cache_resource
def load_queries(path="sql/queries.sql"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"--\s*name:\s*(\S+)\s*\n"
    parts = re.split(pattern, content)

    queries = {}
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip()
        if body:
            queries[name] = body

    return queries

def q(name: str) -> str:
    queries = load_queries()
    if name not in queries:
        raise KeyError(f"Query não encontrada em sql/queries.sql: {name}")
    return queries[name]


# =========================================================
# Helpers 60+
# =========================================================
def brl(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())

def badge_status_orc(stt: str) -> str:
    mp = {
        "RASCUNHO": "🟡 RASCUNHO",
        "EMITIDO": "🔵 EMITIDO",
        "APROVADO": "🟢 APROVADO",
        "REPROVADO": "🔴 REPROVADO",
        "CANCELADO": "⚫ CANCELADO",
    }
    return mp.get(stt, stt)

def safe_df(sql, params=None):
    try:
        return query_df(sql, params)
    except Exception as e:
        st.error("Falha ao consultar o banco.")
        st.code(getattr(e, "pgerror", None) or str(e))
        st.stop()

def safe_exec(sql, params=None, ok_msg=None):
    try:
        exec_sql(sql, params)
        if ok_msg:
            st.success(ok_msg)
    except Exception as e:
        st.error("Falha ao executar no banco.")
        st.code(getattr(e, "pgerror", None) or str(e))
        st.stop()

def goto(menu: str):
    st.session_state["menu"] = menu
    st.rerun()


# =========================================================
# Seed (30 segundos)
# =========================================================
def seed_quick_30s():
    safe_exec(q("ins_cliente_seed"))
    cli = query_one(q("get_cliente_seed"))
    cliente_id = int(cli["id"])

    safe_exec(q("ins_prof_seed"))
    pintor = query_one(q("get_pintor_seed"))
    ajud = query_one(q("get_ajudante_seed"))
    pintor_id = int(pintor["id"])
    ajud_id = int(ajud["id"])

    safe_exec(q("ins_obra_seed"), (cliente_id,))
    obra = query_one(q("get_obra_seed"))
    obra_id = int(obra["id"])

    # cria orçamento
    safe_exec(q("ins_orc_seed"), (obra_id,))
    orc = query_one(q("get_orc_seed"), (obra_id,))
    orc_id = int(orc["id"])

    # fases
    safe_exec(q("ins_fases_seed"), (orc_id, obra_id, orc_id, obra_id))
    fases = query_df(q("q_fases_do_orcamento"), (orc_id,))
    fase1 = int(fases.iloc[0]["id"])
    fase2 = int(fases.iloc[1]["id"])

    # serviços catálogo
    safe_exec(q("ins_servicos_seed"))
    s1 = query_one(q("get_serv_pintura"))
    s2 = query_one(q("get_serv_massa"))
    s1_id = int(s1["id"])
    s2_id = int(s2["id"])

    # vínculo serviços
    safe_exec(q("ins_vinculos_seed"), (orc_id, fase1, s1_id, orc_id, fase1, s2_id, orc_id, fase2, s1_id))

    # recalcula e aprova
    safe_exec(q("call_recalc_orc"), (orc_id,))
    safe_exec(q("set_orc_emitido"), (orc_id,))
    safe_exec(q("set_orc_aprovado"), (orc_id,))

    # recebimentos
    safe_exec(q("ins_receb_seed"), (fase1, orc_id, fase2, orc_id))

    # apontamentos (semana atual)
    hoje = date.today()
    seg = monday_of_week(hoje)

    safe_exec(q("ins_apont_seed"), (
        obra_id, orc_id, fase1, pintor_id, seg,
        obra_id, orc_id, fase1, pintor_id, seg + timedelta(days=1),
        obra_id, orc_id, fase1, ajud_id, seg
    ))

    # gera pagamentos
    safe_exec(q("call_gerar_pag_semana"), (seg,))

    return {"obra_id": obra_id, "orcamento_id": orc_id, "segunda": str(seg)}


# =========================================================
# TELAS
# =========================================================
def tela_home():
    st.subheader("HOME")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("📒 Cadastros", use_container_width=True):
            goto("CADASTROS")
    with c2:
        if st.button("🏗️ Obras", use_container_width=True):
            goto("OBRAS")
    with c3:
        if st.button("💰 Financeiro", use_container_width=True):
            goto("FINANCEIRO")
    with c4:
        if st.button("⚡ Seed (DEV)", type="primary", use_container_width=True):
            out = seed_quick_30s()
            st.success(f"Seed pronto ✅ Obra #{out['obra_id']} • Orçamento #{out['orcamento_id']} • Semana {out['segunda']}")
            st.rerun()

    st.divider()
    st.markdown("### Visão rápida")
    # tenta view (se existir), se falhar usa fallback
    try:
        df = query_df(q("q_home_kpis_safe"))
    except Exception:
        df = query_df(q("q_home_kpis_fallback"))

    r = dict(df.iloc[0])
    k1, k2, k3 = st.columns(3)
    k1.metric("Hoje", str(r.get("hoje")))
    k2.metric("A receber (total)", brl(r.get("recebimentos_pendentes_total", 0)))
    k3.metric("A pagar (total)", brl(r.get("pagar_na_sexta_total", 0)))


def tela_cadastros():
    st.subheader("CADASTROS")
    st.caption("Uma única tela: Cliente + Profissionais (PINTOR / AJUDANTE / TERCEIRO).")

    tabs = st.tabs(["Clientes", "Profissionais"])

    # -------------------------
    # CLIENTES
    # -------------------------
    with tabs[0]:
        st.markdown("### 👤 Clientes")

        if "cli_edit_id" not in st.session_state:
            st.session_state["cli_edit_id"] = None

        df_cli = safe_df(q("q_clientes_all"))
        edit_id = st.session_state["cli_edit_id"]

        row = None
        if edit_id:
            one = safe_df(q("q_cliente_by_id"), (int(edit_id),))
            if not one.empty:
                row = dict(one.iloc[0])
            else:
                st.session_state["cli_edit_id"] = None
                edit_id = None

        with st.form("cli_form", clear_on_submit=(edit_id is None)):
            c1, c2, c3 = st.columns(3)
            with c1:
                nome = st.text_input("Nome", value=(row["nome"] if row else ""))
            with c2:
                tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row else ""))
            with c3:
                end = st.text_input("Endereço (opcional)", value=(row["endereco"] or "" if row else ""))

            b1, b2, b3 = st.columns(3)
            with b1:
                salvar = st.form_submit_button("Salvar", type="primary", use_container_width=True)
            with b2:
                cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)
            with b3:
                st.write("")

            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if edit_id is None:
                    safe_exec(q("ins_cliente"), (nome.strip(), tel.strip() or None, end.strip() or None), "Cliente criado!")
                else:
                    safe_exec(q("upd_cliente"), (nome.strip(), tel.strip() or None, end.strip() or None, int(edit_id)), "Cliente atualizado!")
                    st.session_state["cli_edit_id"] = None
                st.rerun()

            if cancelar:
                st.session_state["cli_edit_id"] = None
                st.rerun()

        st.divider()
        st.markdown("#### Lista")
        if df_cli.empty:
            st.info("Nenhum cliente ainda.")
        else:
            for _, r in df_cli.iterrows():
                rid = int(r["id"])
                colA, colB, colC = st.columns([6, 2, 2])
                with colA:
                    st.write(f"**{r['nome']}**")
                    st.caption(r["telefone"] or "")
                with colB:
                    if st.button("Editar", key=f"cli_ed_{rid}", use_container_width=True):
                        st.session_state["cli_edit_id"] = rid
                        st.rerun()
                with colC:
                    if bool(r["ativo"]):
                        if st.button("Inativar", key=f"cli_in_{rid}", use_container_width=True):
                            safe_exec(q("set_cliente_ativo"), (False, rid))
                            st.rerun()
                    else:
                        if st.button("Ativar", key=f"cli_at_{rid}", use_container_width=True):
                            safe_exec(q("set_cliente_ativo"), (True, rid))
                            st.rerun()

    # -------------------------
    # PROFISSIONAIS (pessoas)
    # -------------------------
    with tabs[1]:
        st.markdown("### 🧑‍🔧 Profissionais")

        if "prof_edit_id" not in st.session_state:
            st.session_state["prof_edit_id"] = None

        df_p = safe_df(q("q_profissionais_all"))
        edit_id = st.session_state["prof_edit_id"]

        row = None
        if edit_id:
            one = safe_df(q("q_prof_by_id"), (int(edit_id),))
            if not one.empty:
                row = dict(one.iloc[0])
            else:
                st.session_state["prof_edit_id"] = None
                edit_id = None

        with st.form("prof_form", clear_on_submit=(edit_id is None)):
            c1, c2, c3 = st.columns(3)
            with c1:
                nome = st.text_input("Nome", value=(row["nome"] if row else ""))
            with c2:
                tipo = st.selectbox(
                    "Tipo",
                    ["PINTOR", "AJUDANTE", "TERCEIRO"],
                    index=(["PINTOR","AJUDANTE","TERCEIRO"].index(row["tipo"]) if row else 0),
                )
            with c3:
                tel = st.text_input("Telefone (opcional)", value=(row["telefone"] or "" if row else ""))

            b1, b2, _ = st.columns(3)
            with b1:
                salvar = st.form_submit_button("Salvar", type="primary", use_container_width=True)
            with b2:
                cancelar = st.form_submit_button("Cancelar edição", use_container_width=True)

            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome.")
                    st.stop()
                if edit_id is None:
                    safe_exec(q("ins_prof"), (nome.strip(), tipo, tel.strip() or None), "Profissional criado!")
                else:
                    safe_exec(q("upd_prof"), (nome.strip(), tipo, tel.strip() or None, int(edit_id)), "Profissional atualizado!")
                    st.session_state["prof_edit_id"] = None
                st.rerun()

            if cancelar:
                st.session_state["prof_edit_id"] = None
                st.rerun()

        st.divider()
        st.markdown("#### Lista")
        if df_p.empty:
            st.info("Nenhum profissional ainda.")
        else:
            for _, r in df_p.iterrows():
                rid = int(r["id"])
                colA, colB, colC, colD = st.columns([5, 2, 2, 2])
                with colA:
                    st.write(f"**{r['nome']}** — {r['tipo']}")
                    st.caption(r["telefone"] or "")
                with colB:
                    if st.button("Editar", key=f"p_ed_{rid}", use_container_width=True):
                        st.session_state["prof_edit_id"] = rid
                        st.rerun()
                with colC:
                    st.write("ATIVO" if bool(r["ativo"]) else "INATIVO")
                with colD:
                    if bool(r["ativo"]):
                        if st.button("Inativar", key=f"p_in_{rid}", use_container_width=True):
                            safe_exec(q("set_prof_ativo"), (False, rid))
                            st.rerun()
                    else:
                        if st.button("Ativar", key=f"p_at_{rid}", use_container_width=True):
                            safe_exec(q("set_prof_ativo"), (True, rid))
                            st.rerun()


def tela_obras():
    st.subheader("OBRAS")
    st.caption("Obra → Orçamento → Fases → Serviços (fluxo guiado).")

    df_obras = safe_df(q("q_obras_ativas"))
    df_cli = safe_df(q("q_clientes_ativos"))

    st.markdown("### 🏗️ Criar / Editar Obra")
    if "obra_edit_id" not in st.session_state:
        st.session_state["obra_edit_id"] = None
    if "obra_sel" not in st.session_state:
        st.session_state["obra_sel"] = None
    if "orc_sel" not in st.session_state:
        st.session_state["orc_sel"] = None

    # Form obra
    edit_id = st.session_state["obra_edit_id"]
    row = None
    if edit_id:
        one = safe_df(q("q_obra_by_id"), (int(edit_id),))
        if not one.empty:
            row = dict(one.iloc[0])
        else:
            st.session_state["obra_edit_id"] = None
            edit_id = None

    cli_ids = df_cli["id"].astype(int).tolist() if not df_cli.empty else []
    if not cli_ids:
        st.warning("Cadastre pelo menos 1 cliente em CADASTROS.")
        return

    with st.form("obra_form", clear_on_submit=(edit_id is None)):
        c1, c2, c3 = st.columns(3)
        with c1:
            default_cli = int(row["cliente_id"]) if row else cli_ids[0]
            idx = cli_ids.index(default_cli) if default_cli in cli_ids else 0
            cliente_id = st.selectbox(
                "Cliente",
                options=cli_ids,
                index=idx,
                format_func=lambda x: df_cli.loc[df_cli["id"] == x, "nome"].iloc[0],
            )
        with c2:
            titulo = st.text_input("Título da obra", value=(row["titulo"] if row else ""))
        with c3:
            status = st.selectbox(
                "Status",
                ["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"],
                index=(["AGUARDANDO","INICIADO","PAUSADO","CANCELADO","CONCLUIDO"].index(row["status"]) if row else 1),
            )

        end = st.text_input("Endereço (opcional)", value=(row["endereco_obra"] or "" if row else ""))

        b1, b2 = st.columns(2)
        salvar = b1.form_submit_button("Salvar Obra", type="primary", use_container_width=True)
        cancelar = b2.form_submit_button("Cancelar edição", use_container_width=True)

        if salvar:
            if not titulo.strip():
                st.warning("Informe o título.")
                st.stop()
            if edit_id is None:
                safe_exec(q("ins_obra"), (int(cliente_id), titulo.strip(), end.strip() or None, status), "Obra criada!")
            else:
                safe_exec(q("upd_obra"), (int(cliente_id), titulo.strip(), end.strip() or None, status, int(edit_id)), "Obra atualizada!")
                st.session_state["obra_edit_id"] = None
            st.rerun()

        if cancelar:
            st.session_state["obra_edit_id"] = None
            st.rerun()

    st.divider()
    st.markdown("### 📌 Selecionar Obra")
    if df_obras.empty:
        st.info("Nenhuma obra ativa ainda.")
        return

    obra_ids = df_obras["id"].astype(int).tolist()
    if st.session_state["obra_sel"] not in obra_ids:
        st.session_state["obra_sel"] = obra_ids[0]

    obra_sel = st.selectbox(
        "Obra selecionada",
        options=obra_ids,
        index=obra_ids.index(st.session_state["obra_sel"]),
        format_func=lambda x: f"#{x} • {df_obras.loc[df_obras['id']==x,'titulo'].iloc[0]} • {df_obras.loc[df_obras['id']==x,'status'].iloc[0]}",
        key="obra_sel_box",
    )
    st.session_state["obra_sel"] = int(obra_sel)

    # Ações obra (editar / ativar)
    st.markdown("#### Ações da obra")
    a1, a2, a3 = st.columns(3)
    if a1.button("Editar obra selecionada", use_container_width=True):
        st.session_state["obra_edit_id"] = int(obra_sel)
        st.rerun()
    if a2.button("Inativar obra selecionada", use_container_width=True):
        safe_exec(q("set_obra_ativo"), (False, int(obra_sel)), "Obra inativada.")
        st.rerun()
    if a3.button("Reativar obra selecionada", use_container_width=True):
        safe_exec(q("set_obra_ativo"), (True, int(obra_sel)), "Obra reativada.")
        st.rerun()

    st.divider()

    # -----------------------------------------------------
    # SUB-MÓDULO: ORÇAMENTOS / FASES / SERVIÇOS / RECEBIMENTOS
    # -----------------------------------------------------
    obra_id = int(st.session_state["obra_sel"])

    tabs = st.tabs(["Orçamentos", "Fases", "Serviços", "Recebimentos"])

    # -----------------
    # ORÇAMENTOS
    # -----------------
    with tabs[0]:
        st.markdown("### 📄 Orçamentos da obra")
        df_orc = safe_df(q("q_orcamentos_da_obra"), (obra_id,))

        # Criar orçamento
        with st.form("orc_new", clear_on_submit=True):
            c1, c2 = st.columns([5, 2])
            with c1:
                tit = st.text_input("Título do orçamento", value="Orçamento")
            with c2:
                st.caption("Status inicial")
                st.write("RASCUNHO")

            criar = st.form_submit_button("Criar orçamento", type="primary", use_container_width=True)
            if criar:
                if not tit.strip():
                    st.warning("Informe o título.")
                    st.stop()
                safe_exec(q("ins_orcamento"), (obra_id, tit.strip()), "Orçamento criado!")
                st.rerun()

        st.divider()

        if df_orc.empty:
            st.info("Nenhum orçamento ainda.")
        else:
            orc_ids = df_orc["id"].astype(int).tolist()
            if st.session_state["orc_sel"] not in orc_ids:
                st.session_state["orc_sel"] = orc_ids[0]

            orc_sel = st.selectbox(
                "Orçamento selecionado",
                options=orc_ids,
                index=orc_ids.index(st.session_state["orc_sel"]),
                format_func=lambda x: f"#{x} • {df_orc.loc[df_orc['id']==x,'titulo'].iloc[0]} • {df_orc.loc[df_orc['id']==x,'status'].iloc[0]}",
                key="orc_sel_box",
            )
            st.session_state["orc_sel"] = int(orc_sel)

            rr = dict(df_orc.loc[df_orc["id"] == int(orc_sel)].iloc[0])

            cA, cB, cC = st.columns([5, 2, 3])
            with cA:
                st.write(f"**#{int(rr['id'])} — {rr['titulo']}**")
                st.caption(badge_status_orc(rr["status"]))

            with cB:
                st.metric("Total (bruto)", brl(rr.get("valor_total", 0)))
                st.metric("Desconto", brl(rr.get("desconto_valor", 0)))
                st.metric("Total final", brl(rr.get("valor_total_final", 0)))

            with cC:
                travado_final = rr["status"] in ("APROVADO","REPROVADO","CANCELADO")

                desc = st.number_input(
                    "Desconto (R$)",
                    min_value=0.0,
                    step=50.0,
                    value=float(rr.get("desconto_valor") or 0),
                    disabled=travado_final,
                    key=f"orc_desc_{int(rr['id'])}",
                )
                if st.button("Salvar desconto", use_container_width=True, disabled=travado_final):
                    safe_exec(q("set_orc_desconto"), (float(desc), int(rr["id"])))
                    safe_exec(q("call_recalc_orc"), (int(rr["id"]),), "Recalculado.")
                    st.rerun()

                if st.button("Recalcular totais", use_container_width=True, disabled=travado_final):
                    safe_exec(q("call_recalc_orc"), (int(rr["id"]),), "Recalculado.")
                    st.rerun()

                # status editável só RASCUNHO <-> EMITIDO
                st.divider()
                st.caption("Status (somente RASCUNHO ⇄ EMITIDO)")
                stt_atual = rr["status"]
                op = ["RASCUNHO","EMITIDO"] if stt_atual in ("RASCUNHO","EMITIDO") else [stt_atual]
                novo = st.selectbox("Status", op, index=op.index(stt_atual), disabled=travado_final, key=f"orc_st_{int(rr['id'])}")

                if st.button("Salvar status", use_container_width=True, disabled=travado_final or (novo == stt_atual)):
                    safe_exec(q("set_orc_status"), (novo, int(rr["id"])), "Status atualizado.")
                    st.rerun()

                st.divider()
                # emitir e aprovar (aprovar é ação “forte”)
                if st.button("Emitir (marca como EMITIDO)", type="primary", use_container_width=True, disabled=travado_final):
                    safe_exec(q("set_orc_emitido"), (int(rr["id"]),), "Emitido.")
                    st.rerun()

                if st.button("Aprovar (libera apontamentos/financeiro)", use_container_width=True, disabled=travado_final):
                    safe_exec(q("set_orc_aprovado"), (int(rr["id"]),), "Aprovado.")
                    st.rerun()

                # reabrir: só se ainda estiver em RASCUNHO/EMITIDO
                pode_reabrir = rr["status"] in ("RASCUNHO","EMITIDO")
                if st.button("Reabrir (voltar para RASCUNHO)", use_container_width=True, disabled=(not pode_reabrir)):
                    safe_exec(q("set_orc_rascunho"), (int(rr["id"]),), "Reaberto.")
                    st.rerun()

    # -----------------
    # FASES
    # -----------------
    with tabs[1]:
        if not st.session_state.get("orc_sel"):
            st.info("Selecione um orçamento em Orçamentos.")
        else:
            orc_id = int(st.session_state["orc_sel"])
            st.markdown("### 🧱 Fases do orçamento")

            df_f = safe_df(q("q_fases_do_orcamento"), (orc_id,))
            with st.form("fase_new", clear_on_submit=True):
                c1, c2, c3 = st.columns([4, 1, 2])
                with c1:
                    nome = st.text_input("Nome da fase", value="FASE")
                with c2:
                    ordem = st.number_input("Ordem", min_value=1, step=1, value=(int(df_f["ordem"].max()) + 1 if not df_f.empty else 1))
                with c3:
                    stt = st.selectbox("Status", ["AGUARDANDO","INICIADO","PAUSADO","CONCLUIDO","CANCELADO"], index=0)

                criar = st.form_submit_button("Adicionar fase", type="primary", use_container_width=True)
                if criar:
                    if not nome.strip():
                        st.warning("Informe o nome.")
                        st.stop()
                    safe_exec(q("ins_fase"), (orc_id, obra_id, nome.strip(), int(ordem), stt), "Fase criada!")
                    st.rerun()

            st.divider()
            if df_f.empty:
                st.info("Nenhuma fase ainda.")
            else:
                st.dataframe(df_f, use_container_width=True, hide_index=True)

    # -----------------
    # SERVIÇOS
    # -----------------
    with tabs[2]:
        if not st.session_state.get("orc_sel"):
            st.info("Selecione um orçamento em Orçamentos.")
        else:
            orc_id = int(st.session_state["orc_sel"])
            st.markdown("### 🧰 Serviços")

            df_f = safe_df(q("q_fases_do_orcamento"), (orc_id,))
            if df_f.empty:
                st.warning("Crie fases antes de vincular serviços.")
            else:
                # Catálogo
                st.markdown("#### Catálogo (cadastro rápido)")
                with st.form("serv_cat", clear_on_submit=True):
                    c1, c2 = st.columns([4, 2])
                    with c1:
                        snome = st.text_input("Nome do serviço", value="")
                    with c2:
                        un = st.text_input("Unidade (ex: m2, diária)", value="m2")
                    add = st.form_submit_button("Adicionar ao catálogo", type="primary", use_container_width=True)
                    if add:
                        if not snome.strip():
                            st.warning("Informe o nome do serviço.")
                            st.stop()
                        safe_exec(q("ins_servico_catalogo"), (snome.strip(), un.strip() or "UN"), "Serviço criado!")
                        st.rerun()

                st.divider()

                # Vincular a uma fase
                st.markdown("#### Vincular serviços em uma fase")
                fase_ids = df_f["id"].astype(int).tolist()
                fase_sel = st.selectbox(
                    "Fase",
                    options=fase_ids,
                    format_func=lambda x: f"{int(df_f.loc[df_f['id']==x,'ordem'].iloc[0])} - {df_f.loc[df_f['id']==x,'nome_fase'].iloc[0]}",
                    key="fase_sel_serv",
                )

                df_cat = safe_df(q("q_servicos_catalogo"))
                if df_cat.empty:
                    st.info("Cadastre serviços no catálogo acima.")
                else:
                    serv_ids = df_cat["id"].astype(int).tolist()

                    with st.form("serv_vinc", clear_on_submit=True):
                        c1, c2, c3 = st.columns([4, 2, 2])
                        with c1:
                            serv_id = st.selectbox(
                                "Serviço",
                                options=serv_ids,
                                format_func=lambda x: df_cat.loc[df_cat["id"]==x, "nome"].iloc[0],
                            )
                        with c2:
                            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0, value=1.0)
                        with c3:
                            vunit = st.number_input("Valor unitário (R$)", min_value=0.0, step=10.0, value=0.0)

                        salvar = st.form_submit_button("Adicionar/Atualizar", type="primary", use_container_width=True)
                        if salvar:
                            safe_exec(q("upsert_serv_fase"), (orc_id, int(fase_sel), int(serv_id), float(qtd), float(vunit)))
                            safe_exec(q("call_recalc_orc"), (orc_id,), "Atualizado e recalculado.")
                            st.rerun()

                    st.divider()
                    df_link = safe_df(q("q_servicos_da_fase"), (orc_id, int(fase_sel)))
                    st.dataframe(df_link, use_container_width=True, hide_index=True)

    # -----------------
    # RECEBIMENTOS
    # -----------------
    with tabs[3]:
        if not st.session_state.get("orc_sel"):
            st.info("Selecione um orçamento em Orçamentos.")
        else:
            orc_id = int(st.session_state["orc_sel"])
            st.markdown("### 💳 Recebimentos do orçamento")

            df_f = safe_df(q("q_fases_do_orcamento"), (orc_id,))
            if df_f.empty:
                st.info("Crie fases primeiro.")
                return

            # Lista
            df_r = safe_df(q("q_recebimentos_do_orcamento"), (orc_id,))
            st.dataframe(df_r, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("#### Criar/Atualizar recebimento da fase")
            fase_ids = df_f["id"].astype(int).tolist()
            fase_sel = st.selectbox(
                "Fase",
                options=fase_ids,
                format_func=lambda x: f"{int(df_f.loc[df_f['id']==x,'ordem'].iloc[0])} - {df_f.loc[df_f['id']==x,'nome_fase'].iloc[0]}",
                key="fase_sel_rec",
            )

            with st.form("rec_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    vbase = st.number_input("Valor base", min_value=0.0, step=50.0, value=0.0)
                with c2:
                    acresc = st.number_input("Acréscimo", min_value=0.0, step=50.0, value=0.0)
                with c3:
                    venc = st.date_input("Vencimento", value=date.today() + timedelta(days=7))

                obs = st.text_input("Observação (opcional)", value="")
                salvar = st.form_submit_button("Salvar recebimento", type="primary", use_container_width=True)

                if salvar:
                    safe_exec(q("upsert_recebimento"), (int(fase_sel), orc_id, float(vbase), float(acresc), venc, obs.strip() or None))
                    st.success("Recebimento salvo.")
                    st.rerun()


def tela_financeiro():
    st.subheader("FINANCEIRO")
    st.caption("Pagamentos e Recebimentos (fluxo diário simples).")

    tabs = st.tabs(["Pagamentos", "Recebimentos"])

    # -----------------
    # PAGAMENTOS
    # -----------------
    with tabs[0]:
        st.markdown("### 💸 Pagamentos")

        # Gerar pagamentos semana
        colA, colB = st.columns([3, 2])
        with colA:
            segunda = st.date_input("Segunda da semana", value=monday_of_week(date.today()))
        with colB:
            st.write("")
            if st.button("Gerar pagamentos da semana", type="primary", use_container_width=True):
                safe_exec(q("call_gerar_pag_semana"), (segunda,), "Pagamentos gerados/atualizados!")
                st.rerun()

        st.divider()
        st.markdown("#### Pendentes")
        df_pend = safe_df(q("q_pagamentos_pendentes"))
        st.dataframe(df_pend, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### Marcar como pago / Estornar")
        data_pg = st.date_input("Data do pagamento", value=date.today(), key="dt_pg")

        if not df_pend.empty:
            ids = df_pend["id"].astype(int).tolist()
            pag_id = st.selectbox("Pagamento pendente", options=ids, key="sel_pag_pend")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Marcar como PAGO", type="primary", use_container_width=True):
                    safe_exec(q("call_marcar_pago"), (int(pag_id), "admin", data_pg), "Pagamento marcado como PAGO.")
                    st.rerun()
            with c2:
                st.write("")

        st.divider()
        st.markdown("#### Pagos (últimos 30 dias) + Estorno")
        df_pago = safe_df(q("q_pagamentos_pagos_30d"))
        st.dataframe(df_pago, use_container_width=True, hide_index=True)

        if not df_pago.empty:
            ids2 = df_pago["id"].astype(int).tolist()
            pag2 = st.selectbox("Pagamento PAGO", options=ids2, key="sel_pag_pago")
            motivo = st.text_input("Motivo do estorno", value="Correção", key="mot_estorno")

            if st.button("↩️ Estornar (volta para ABERTO)", use_container_width=True):
                safe_exec(q("call_estornar"), (int(pag2), "admin", motivo.strip() or None), "Estornado.")
                st.rerun()

    # -----------------
    # RECEBIMENTOS
    # -----------------
    with tabs[1]:
        st.markdown("### 💳 Recebimentos (visão geral)")
        # visão simples: últimos 200
        df = safe_df(q("q_recebimentos_ultimos"))
        st.dataframe(df, use_container_width=True, hide_index=True)
