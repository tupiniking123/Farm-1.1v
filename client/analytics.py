"""
analytics.py
Dashboards (Plotly) + small helpers.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px


def monthly_income_expense(df_inc: pd.DataFrame, df_exp: pd.DataFrame):
    if df_inc.empty and df_exp.empty:
        return None

    inc = df_inc.copy()
    exp = df_exp.copy()
    if not inc.empty:
        inc["month"] = pd.to_datetime(inc["date"]).dt.to_period("M").astype(str)
        inc_g = inc.groupby("month", as_index=False)["amount"].sum().rename(columns={"amount": "income"})
    else:
        inc_g = pd.DataFrame(columns=["month", "income"])

    if not exp.empty:
        exp["month"] = pd.to_datetime(exp["date"]).dt.to_period("M").astype(str)
        exp_g = exp.groupby("month", as_index=False)["amount"].sum().rename(columns={"amount": "expense"})
    else:
        exp_g = pd.DataFrame(columns=["month", "expense"])

    df = pd.merge(inc_g, exp_g, on="month", how="outer").fillna(0).sort_values("month")
    df_long = df.melt(id_vars=["month"], value_vars=["income", "expense"], var_name="type", value_name="amount")
    fig = px.line(df_long, x="month", y="amount", color="type", markers=True, title="Receita x Despesa (Mensal)")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=45, b=10))
    return fig


def expense_by_category(df_exp: pd.DataFrame):
    if df_exp.empty:
        return None
    df = df_exp.copy()
    df["category"] = df["category_name"].fillna("Sem categoria")
    g = df.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    fig = px.pie(g, values="amount", names="category", title="Despesas por Categoria")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=45, b=10))
    return fig


def inventory_balance_bar(df_balance: pd.DataFrame):
    if df_balance.empty:
        return None
    df = df_balance.copy()
    fig = px.bar(df, x="name", y="balance", color="type", title="Saldo de Estoque")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=45, b=10), xaxis_title="")
    return fig
