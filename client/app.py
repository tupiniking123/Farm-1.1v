"""
Streamlit client app (Windows friendly).
Run: streamlit run client/app.py
"""
from __future__ import annotations

import requests
import pandas as pd
import streamlit as st
from datetime import date

from db_local import connect, init_schema, get_setting, set_setting, fetch_all, fetch_one
from services import (
    create_farm_local, list_farms_local, list_categories,
    add_income, add_expense, soft_delete,
    upsert_inventory_item, add_inventory_movement,
    upsert_cattle, add_vaccination,
    df_income, df_expense, df_inventory_items, df_inventory_movements, df_cattle, df_vaccinations,
    compute_kpis, alerts, inventory_balance,
)
from analytics import monthly_income_expense, expense_by_category, inventory_balance_bar
from ui import apply_theme, sidebar_controls, table, download_csv_button
from sync_client import sync_now


st.set_page_config(page_title="Rural SaaS (Offline)", layout="wide")


def api_post(server_url: str, path: str, json: dict, token: str | None = None):
    url = server_url.rstrip("/") + path
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(url, json=json, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_get(server_url: str, path: str, params: dict | None = None, token: str | None = None):
    url = server_url.rstrip("/") + path
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def login_screen(conn):
    st.title("🔐 Login")
    st.caption("Você pode usar offline total ou conectar ao servidor para login + sync.")

    server_url = st.text_input("URL do servidor (opcional)", value=get_setting(conn, "server_url", "http://127.0.0.1:8000"))
    email = st.text_input("E-mail", value=get_setting(conn, "user_email", ""))
    password = st.text_input("Senha", type="password")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Registrar (servidor)", use_container_width=True):
            try:
                api_post(server_url, "/auth/register", {"email": email, "password": password})
                st.success("Conta criada! Agora faça login.")
                set_setting(conn, "server_url", server_url)
                set_setting(conn, "user_email", email)
            except Exception as e:
                st.error(f"Falha ao registrar: {e}")

    with col2:
        if st.button("Login (servidor)", use_container_width=True):
            try:
                data = api_post(server_url, "/auth/login", {"email": email, "password": password})
                st.session_state["token"] = data["access_token"]
                st.session_state["server_url"] = server_url
                st.session_state["user_email"] = email
                st.session_state["mode"] = "online"
                set_setting(conn, "server_url", server_url)
                set_setting(conn, "user_email", email)
                st.success("Logado!")
                st.rerun()
            except Exception as e:
                st.error(f"Falha no login: {e}")

    with col3:
        if st.button("Continuar offline", use_container_width=True):
            st.session_state["token"] = ""
            st.session_state["server_url"] = ""
            st.session_state["user_email"] = email or "offline@local"
            st.session_state["mode"] = "offline"
            set_setting(conn, "user_email", st.session_state["user_email"])
            st.info("Modo offline ativado.")
            st.rerun()


def ensure_session_from_settings(conn):
    if "mode" not in st.session_state:
        st.session_state["mode"] = "offline"
    st.session_state.setdefault("token", "")
    st.session_state.setdefault("server_url", get_setting(conn, "server_url", ""))
    st.session_state.setdefault("user_email", get_setting(conn, "user_email", ""))


def sync_farms_from_server(conn):
    """Fetch farms from /me and upsert locally (so you can use them offline too)."""
    token = st.session_state.get("token") or ""
    server_url = st.session_state.get("server_url") or ""
    if not token or not server_url:
        return
    try:
        me = api_get(server_url, "/me", token=token)
        farms = me.get("farms", [])
        # upsert farms locally
        from db_local import upsert_rows
        upsert_rows(conn, "farms", farms)
    except Exception as e:
        st.warning(f"Não foi possível carregar fazendas do servidor: {e}")


def page_dashboard(conn, farm_id: str, start: str, end: str):
    st.header("📊 Dashboard")

    k = compute_kpis(conn, farm_id, start, end)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Receita", f"{k['income']:.2f}")
    c2.metric("Despesa", f"{k['expense']:.2f}")
    c3.metric("Lucro Bruto", f"{k['gross_profit']:.2f}")
    c4.metric("Lucro Líquido", f"{k['net_profit']:.2f}")
    c5.metric("Margem (%)", f"{k['margin']:.1f}")

    df_inc = df_income(conn, farm_id, start, end)
    df_exp = df_expense(conn, farm_id, start, end)

    left, right = st.columns(2)
    with left:
        fig = monthly_income_expense(df_inc, df_exp)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados no período.")

    with right:
        fig2 = expense_by_category(df_exp)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem despesas no período.")

    st.subheader("🚨 Alertas")
    a = alerts(conn, farm_id)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Estoque baixo**")
        table(a["low_stock"], height=220)
        st.markdown("**Vencimentos (<= 30 dias)**")
        table(a["expiring"], height=220)
    with c2:
        st.markdown("**Vacinas próximas (<= 7 dias)**")
        table(a["vaccines_due"], height=220)
        st.markdown("**Anomalias (gasto > 1.5x média 3 meses)**")
        table(a["anomalies"], height=220)


def page_financeiro(conn, farm_id: str, start: str, end: str):
    st.header("💰 Financeiro")

    tabs = st.tabs(["Receitas", "Despesas", "Exportar CSV"])
    with tabs[0]:
        st.subheader("Nova Receita")
        with st.form("form_income", clear_on_submit=True):
            d = st.date_input("Data", value=date.today())
            desc = st.text_input("Descrição")
            amount = st.number_input("Valor", min_value=0.0, step=10.0)
            source = st.text_input("Fonte (opcional)", value="")
            ok = st.form_submit_button("Salvar")
        if ok:
            add_income(conn, farm_id, d.isoformat(), desc, amount, source)
            st.success("Receita salva!")

        st.subheader("Receitas no período")
        df = df_income(conn, farm_id, start, end)
        table(df, height=320)

    with tabs[1]:
        cats = list_categories(conn, farm_id)
        cat_map = {c["id"]: c["name"] for c in cats}
        st.subheader("Nova Despesa")
        with st.form("form_expense", clear_on_submit=True):
            d = st.date_input("Data", value=date.today(), key="exp_date")
            cat_id = st.selectbox("Categoria", options=[""] + list(cat_map.keys()), format_func=lambda x: cat_map.get(x, "Sem categoria"), index=0)
            desc = st.text_input("Descrição", key="exp_desc")
            amount = st.number_input("Valor", min_value=0.0, step=10.0, key="exp_amount")
            vendor = st.text_input("Fornecedor (opcional)", key="exp_vendor", value="")
            is_unplanned = st.checkbox("Imprevisto?", value=False, key="exp_unplanned")
            ok = st.form_submit_button("Salvar despesa")
        if ok:
            add_expense(conn, farm_id, d.isoformat(), cat_id or None, desc, amount, vendor, is_unplanned)
            st.success("Despesa salva!")

        st.subheader("Despesas no período")
        df = df_expense(conn, farm_id, start, end)
        table(df, height=320)

    with tabs[2]:
        st.subheader("Exportar")
        df_i = df_income(conn, farm_id, start, end)
        df_e = df_expense(conn, farm_id, start, end)
        download_csv_button(df_i, "income.csv", "Baixar Receitas (CSV)")
        download_csv_button(df_e, "expense.csv", "Baixar Despesas (CSV)")


def page_estoque(conn, farm_id: str, start: str, end: str):
    st.header("📦 Estoque")

    items = df_inventory_items(conn, farm_id)
    bal = inventory_balance(conn, farm_id)

    tabs = st.tabs(["Itens", "Movimentações", "Saldo/Alertas", "Exportar CSV"])

    with tabs[0]:
        st.subheader("Cadastrar/Editar Item")
        with st.form("form_item", clear_on_submit=True):
            name = st.text_input("Nome do item")
            type_ = st.selectbox("Tipo", ["FEED", "INPUT", "VACCINE"])
            unit = st.text_input("Unidade", value="kg")
            min_level = st.number_input("Nível mínimo", min_value=0.0, step=1.0)
            expires_at = st.date_input("Validade (opcional)", value=None)
            ok = st.form_submit_button("Salvar item")
        if ok:
            exp = expires_at.isoformat() if expires_at else None
            upsert_inventory_item(conn, farm_id, name, type_, unit, min_level, exp)
            st.success("Item salvo!")

        st.subheader("Itens")
        table(items, height=320)

    with tabs[1]:
        if items.empty:
            st.info("Cadastre itens para movimentar.")
        else:
            item_opts = items["id"].tolist()
            name_map = dict(zip(items["id"], items["name"]))
            st.subheader("Nova movimentação")
            with st.form("form_move", clear_on_submit=True):
                d = st.date_input("Data", value=date.today(), key="mov_date")
                item_id = st.selectbox("Item", options=item_opts, format_func=lambda x: name_map.get(x, x))
                movement_type = st.selectbox("Tipo", ["IN", "OUT"])
                qty = st.number_input("Quantidade", step=1.0)
                cost_total = st.number_input("Custo total (opcional)", min_value=0.0, step=10.0)
                note = st.text_input("Observação", value="")
                ok = st.form_submit_button("Salvar movimentação")
            if ok:
                add_inventory_movement(conn, farm_id, item_id, d.isoformat(), qty, cost_total, movement_type, note)
                st.success("Movimentação salva!")

        st.subheader("Movimentações no período")
        dfm = df_inventory_movements(conn, farm_id, start, end)
        table(dfm, height=320)

    with tabs[2]:
        st.subheader("Saldo")
        if not bal.empty:
            fig = inventory_balance_bar(bal)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        table(bal, height=320)

    with tabs[3]:
        st.subheader("Exportar")
        download_csv_button(items, "inventory_items.csv", "Baixar Itens (CSV)")
        dfm = df_inventory_movements(conn, farm_id, start, end)
        download_csv_button(dfm, "inventory_movements.csv", "Baixar Movimentações (CSV)")


def page_vacinacao(conn, farm_id: str, start: str, end: str):
    st.header("💉 Vacinação")

    cattle = df_cattle(conn, farm_id)
    items = df_inventory_items(conn, farm_id)
    vaccines = items[items["type"] == "VACCINE"] if not items.empty else pd.DataFrame()

    tabs = st.tabs(["Animais", "Registros", "Exportar CSV"])

    with tabs[0]:
        st.subheader("Cadastrar Animal")
        with st.form("form_cattle", clear_on_submit=True):
            tag = st.text_input("Brinco/Tag")
            birth = st.date_input("Nascimento (opcional)", value=None)
            notes = st.text_area("Notas", value="", height=80)
            ok = st.form_submit_button("Salvar animal")
        if ok:
            b = birth.isoformat() if birth else None
            upsert_cattle(conn, farm_id, tag, b, notes)
            st.success("Animal salvo!")

        st.subheader("Animais")
        table(cattle, height=320)

    with tabs[1]:
        if cattle.empty or vaccines.empty:
            st.info("Cadastre animais e itens de vacina (tipo VACCINE) para registrar.")
        else:
            cattle_opts = cattle["id"].tolist()
            cattle_map = dict(zip(cattle["id"], cattle["tag"]))
            vacc_opts = vaccines["id"].tolist()
            vacc_map = dict(zip(vaccines["id"], vaccines["name"]))

            st.subheader("Registrar vacinação")
            with st.form("form_vacc", clear_on_submit=True):
                d = st.date_input("Data", value=date.today(), key="vac_date")
                cattle_id = st.selectbox("Animal", options=cattle_opts, format_func=lambda x: cattle_map.get(x, x))
                vaccine_item_id = st.selectbox("Vacina", options=vacc_opts, format_func=lambda x: vacc_map.get(x, x))
                dose = st.text_input("Dose (opcional)", value="")
                cost = st.number_input("Custo (opcional)", min_value=0.0, step=1.0)
                next_due = st.date_input("Próxima dose (opcional)", value=None, key="vac_next")
                ok = st.form_submit_button("Salvar vacinação")
            if ok:
                nd = next_due.isoformat() if next_due else None
                add_vaccination(conn, farm_id, cattle_id, vaccine_item_id, d.isoformat(), dose, cost, nd)
                st.success("Vacinação registrada!")

        st.subheader("Registros no período")
        dfv = df_vaccinations(conn, farm_id, start, end)
        table(dfv, height=320)

    with tabs[2]:
        st.subheader("Exportar")
        download_csv_button(cattle, "cattle.csv", "Baixar Animais (CSV)")
        dfv = df_vaccinations(conn, farm_id, start, end)
        download_csv_button(dfv, "vaccinations.csv", "Baixar Vacinações (CSV)")


def page_cadastros(conn, farm_id: str):
    st.header("🧩 Cadastros")

    st.subheader("Fazendas (local)")
    farms = list_farms_local(conn)
    table(pd.DataFrame(farms), height=220)

    with st.form("form_new_farm", clear_on_submit=True):
        name = st.text_input("Nome da fazenda")
        currency = st.text_input("Moeda", value="BRL")
        tz = st.text_input("Timezone", value="America/Sao_Paulo")
        ok = st.form_submit_button("Criar fazenda (local)")
    if ok:
        fid = create_farm_local(conn, name, currency, tz)
        set_setting(conn, "active_farm_id", fid)
        st.success("Fazenda criada!")

    st.subheader("Categorias")
    cats = list_categories(conn, farm_id) if farm_id else []
    table(pd.DataFrame(cats), height=260)


def page_sync(conn, farm_id: str):
    st.header("🔄 Sincronização")

    server_url = st.session_state.get("server_url") or get_setting(conn, "server_url", "")
    token = st.session_state.get("token") or ""

    st.write("Servidor:", server_url or "—")
    st.write("Modo:", st.session_state.get("mode", "offline"))
    meta = fetch_one(conn, "SELECT * FROM local_meta WHERE id=1")
    st.write("Último sync:", meta.get("last_sync_at") if meta else "—")

    if not server_url or not token:
        st.info("Para sincronizar, faça login no servidor.")
        return
    if not farm_id:
        st.info("Selecione uma fazenda.")
        return

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Sincronizar agora (push/pull)", use_container_width=True):
            try:
                result = sync_now(conn, server_url, token, farm_id)
                st.success("Sync concluído!")
                st.json({"server_time": result["server_time"]})
            except Exception as e:
                st.error(f"Falha na sync: {e}")

    with col2:
        st.caption("Dica: sempre que quiser, clique para enviar/baixar mudanças.")


def page_online_farms(conn):
    """Only when online: create farm on server, invite/join."""
    server_url = st.session_state.get("server_url") or ""
    token = st.session_state.get("token") or ""
    if not server_url or not token:
        return

    st.subheader("🌐 Operações no servidor (multi-fazendas)")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Criar fazenda no servidor**")
        with st.form("form_server_farm", clear_on_submit=True):
            name = st.text_input("Nome", key="srv_farm_name")
            currency = st.text_input("Moeda", value="BRL", key="srv_farm_curr")
            tz = st.text_input("Timezone", value="America/Sao_Paulo", key="srv_farm_tz")
            ok = st.form_submit_button("Criar (server)")
        if ok:
            try:
                farm = api_post(server_url, "/farms", {"name": name, "currency": currency, "timezone": tz}, token=token)
                st.success("Fazenda criada no servidor!")
                # keep local copy
                from db_local import upsert_rows
                upsert_rows(conn, "farms", [farm])
            except Exception as e:
                st.error(f"Erro: {e}")

    with col2:
        st.markdown("**Entrar em fazenda (invite code)**")
        with st.form("form_join", clear_on_submit=True):
            code = st.text_input("Invite code")
            ok = st.form_submit_button("Entrar")
        if ok:
            try:
                data = api_post(server_url, "/farms/join", {"invite_code": code}, token=token)
                st.success("Entrou na fazenda!")
                from db_local import upsert_rows
                upsert_rows(conn, "farms", [data["farm"]])
            except Exception as e:
                st.error(f"Erro: {e}")

    st.markdown("**Gerar invite** (fazenda ativa)")
    farm_id = get_setting(conn, "active_farm_id", "")
    if farm_id:
        if st.button("Gerar invite code (fazenda ativa)"):
            try:
                data = api_post(server_url, f"/farms/{farm_id}/invite", {}, token=token)
                st.code(data["invite_code"])
            except Exception as e:
                st.error(f"Erro: {e}")


def main():
    with connect() as conn:
        init_schema(conn)
        ensure_session_from_settings(conn)
        apply_theme(conn)

        # gate: logged in online OR offline mode
        if st.session_state.get("mode") not in ("online", "offline"):
            st.session_state["mode"] = "offline"

        if st.session_state.get("mode") == "online" and not st.session_state.get("token"):
            # token missing, show login
            login_screen(conn)
            return

        # If token exists, consider online
        if st.session_state.get("token"):
            st.session_state["mode"] = "online"

        # If no token, offline
        if not st.session_state.get("token"):
            st.session_state["mode"] = "offline"

        # If totally fresh open, offer login
        if st.session_state.get("mode") == "offline" and not get_setting(conn, "user_email", ""):
            login_screen(conn)
            return

        # Load farms from server when online (best effort)
        if st.session_state.get("mode") == "online":
            sync_farms_from_server(conn)

        ctrl = sidebar_controls(conn)
        farm_id = ctrl["active_farm_id"]
        start, end = ctrl["start"], ctrl["end"]
        menu = ctrl["menu"]

        if not farm_id:
            st.warning("Crie/seleciona uma fazenda para continuar.")
            # show farm create on cadastros
            page_cadastros(conn, farm_id="")
            if st.session_state.get("mode") == "online":
                page_online_farms(conn)
            return

        if menu == "Dashboard":
            page_dashboard(conn, farm_id, start, end)
        elif menu == "Financeiro":
            page_financeiro(conn, farm_id, start, end)
        elif menu == "Estoque":
            page_estoque(conn, farm_id, start, end)
        elif menu == "Vacinação":
            page_vacinacao(conn, farm_id, start, end)
        elif menu == "Cadastros":
            page_cadastros(conn, farm_id)
            if st.session_state.get("mode") == "online":
                page_online_farms(conn)
        elif menu == "Sync":
            page_sync(conn, farm_id)


if __name__ == "__main__":
    main()
