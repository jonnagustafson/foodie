"""Foodie – ICA Receipt Analyzer.

A Streamlit app for uploading ICA grocery receipts and exploring food habits
over time. Receipts are parsed locally; no external services are required.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit_authenticator as stauth

from core.analyzer import (
    compute_monthly_summary,
    compute_spending_by_category,
    compute_summary_metrics,
    compute_top_items,
)
from core.categories import all_categories, categorize_item
from integrations.pdf_parser import parse_ica_receipt
from integrations.storage import (
    load_items,
    load_receipts,
    load_savings,
    receipt_already_saved,
    save_receipt,
    update_item_category,
)


def _build_authenticator() -> stauth.Authenticate | None:
    """Return an Authenticate instance if auth env vars are configured, else None."""
    username = os.environ.get("AUTH_USERNAME", "")
    if not username:
        return None
    credentials: dict = {
        "usernames": {
            username: {
                "name": os.environ.get("AUTH_NAME", username),
                "password": os.environ.get("AUTH_PASSWORD_HASH", ""),
                "logged_in": False,
            }
        }
    }
    return stauth.Authenticate(
        credentials,
        cookie_name=os.environ.get("AUTH_COOKIE_NAME", "foodie_auth"),
        cookie_key=os.environ.get("AUTH_COOKIE_KEY", ""),
        cookie_expiry_days=30,
        auto_hash=False,
    )


def main() -> None:
    """Run the Foodie Streamlit application."""
    st.set_page_config(
        page_title="Foodie – Kvittoanalys",
        page_icon="🛒",
        layout="wide",
    )

    authenticator = _build_authenticator()

    if authenticator is not None:
        authenticator.login(
            location="main",
            max_login_attempts=5,
            fields={
                "Form name": "Logga in på Foodie",
                "Username": "Användarnamn",
                "Password": "Lösenord",
                "Login": "Logga in",
            },
        )
        status = st.session_state.get("authentication_status")
        if status is False:
            st.error("Felaktigt användarnamn eller lösenord.")
            return
        if status is None:
            return

    st.sidebar.title("🛒 Foodie")
    st.sidebar.caption("Analysera dina matvanor via ICA-kvitton")

    if authenticator is not None:
        authenticator.logout(button_name="Logga ut", location="sidebar")

    page = st.sidebar.radio(
        "Navigering",
        ["Ladda upp kvitto", "Analys & Trender"],
        label_visibility="collapsed",
    )

    if page == "Ladda upp kvitto":
        _render_upload_page()
    else:
        _render_dashboard_page()


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


def _category_select_column() -> st.column_config.SelectboxColumn:
    return st.column_config.SelectboxColumn("Kategori", options=all_categories(), required=True)


# ---------------------------------------------------------------------------
# Upload page
# ---------------------------------------------------------------------------


def _render_upload_page() -> None:
    st.title("Ladda upp kvitto")
    st.write(
        "Ladda upp ett PDF-kvitto från ICA-appen eller ICAs webb för att spara det i din historik."
    )

    _MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB

    uploaded = st.file_uploader("Välj PDF-kvitto", type=["pdf"])
    if uploaded is None:
        return

    if uploaded.size > _MAX_PDF_BYTES:
        st.error("Filen är för stor (max 20 MB).")
        return

    if receipt_already_saved(uploaded.name):
        st.warning(f"Kvittot **{uploaded.name}** är redan sparat.")
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    try:
        parsed = parse_ica_receipt(tmp_path)
    except Exception:
        st.error("Kunde inte läsa kvittot. Kontrollera att det är ett digitalt ICA-kvitto i PDF-format.")
        return
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Enrich items with categories (business logic layer)
    for item in parsed["items"]:
        item["category"] = categorize_item(item["name"])

    st.subheader("Förhandsgranskning")
    col1, col2, col3 = st.columns(3)
    col1.metric("Datum", parsed["date"])
    col2.metric("Butik", parsed["store"])
    col3.metric("Summa", f"{parsed['total']:.2f} kr")

    items_df = pd.DataFrame(parsed["items"])[["name", "quantity", "price", "category"]]
    edited_df = st.data_editor(
        items_df.rename(
            columns={
                "name": "Vara",
                "quantity": "Antal",
                "price": "Pris (kr)",
                "category": "Kategori",
            }
        ),
        column_config={
            "Vara": st.column_config.TextColumn("Vara", disabled=True),
            "Antal": st.column_config.NumberColumn("Antal", disabled=True),
            "Pris (kr)": st.column_config.NumberColumn("Pris (kr)", disabled=True),
            "Kategori": _category_select_column(),
        },
        use_container_width=True,
        hide_index=True,
        key="upload_category_editor",
    )

    if parsed.get("savings"):
        st.caption("Rabatter på kvittot")
        savings_df = pd.DataFrame(parsed["savings"])[["name", "amount"]].rename(
            columns={"name": "Rabatt", "amount": "Belopp (kr)"}
        )
        st.dataframe(savings_df, use_container_width=True, hide_index=True)

    if st.button("Spara kvitto", type="primary"):
        for i, item in enumerate(parsed["items"]):
            item["category"] = edited_df.iloc[i]["Kategori"]
        receipt_id = save_receipt(parsed, uploaded.name)
        st.success(f"Kvitto sparat! (ID: {receipt_id})")
        st.balloons()


# ---------------------------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------------------------


def _render_dashboard_page() -> None:
    st.title("Analys & Trender")

    items_df = load_items()
    receipts_df = load_receipts()
    savings_df = load_savings()

    if items_df.empty:
        st.info(
            "Inga kvitton uppladdade ännu. Gå till **Ladda upp kvitto** för att komma igång."
        )
        return

    # --- Date range filter ---
    dates = sorted(items_df["date"].unique())
    col1, col2 = st.columns(2)
    start_date = col1.selectbox("Från", dates, index=0)
    end_date = col2.selectbox("Till", dates, index=len(dates) - 1)

    filtered = items_df[
        (items_df["date"] >= start_date) & (items_df["date"] <= end_date)
    ]

    if filtered.empty:
        st.warning("Inga data för valt datumintervall.")
        return

    # --- Summary metrics ---
    metrics = compute_summary_metrics(filtered)
    filtered_savings = savings_df[
        (savings_df["date"] >= start_date) & (savings_df["date"] <= end_date)
    ] if not savings_df.empty else savings_df
    total_savings = filtered_savings["amount"].sum() if not filtered_savings.empty else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total utgift", f"{metrics['total_spent']:.0f} kr")
    col2.metric("Totalt sparat", f"{abs(total_savings):.0f} kr")
    col3.metric("Antal kvitton", metrics["num_receipts"])
    col4.metric("Artikelrader", metrics["num_items"])

    st.divider()

    # --- Charts: category pie + top items bar ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Utgifter per kategori")
        cat_df = compute_spending_by_category(filtered)
        if not cat_df.empty:
            fig = px.pie(
                cat_df,
                values="total",
                names="category",
                hole=0.4,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Topp 10 varor")
        top_df = compute_top_items(filtered)
        if not top_df.empty:
            fig = px.bar(
                top_df.sort_values("count"),
                x="count",
                y="name",
                orientation="h",
                labels={"count": "Antal köp", "name": ""},
            )
            fig.update_layout(margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

    # --- Monthly spending trend ---
    st.subheader("Utgifter per månad")
    monthly_df = compute_monthly_summary(filtered)
    if not monthly_df.empty:
        fig = px.bar(
            monthly_df,
            x="month",
            y="total",
            labels={"month": "Månad", "total": "Utgift (kr)"},
            text_auto=".0f",
            category_orders={"month": list(monthly_df["month"])},
        )
        fig.update_layout(
            margin=dict(t=20, b=20),
            xaxis_type="category",
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Category editor ---
    with st.expander("Redigera kategorier"):
        edit_source = filtered[["id", "date", "name", "category"]].reset_index(drop=True)
        edited_categories = st.data_editor(
            edit_source[["date", "name", "category"]].rename(
                columns={"date": "Datum", "name": "Vara", "category": "Kategori"}
            ),
            column_config={
                "Datum": st.column_config.TextColumn("Datum", disabled=True),
                "Vara": st.column_config.TextColumn("Vara", disabled=True),
                "Kategori": _category_select_column(),
            },
            use_container_width=True,
            hide_index=True,
            key="category_editor",
        )
        if st.button("Spara kategorier"):
            changes = st.session_state.get("category_editor", {}).get("edited_rows", {})
            for row_idx, changed_fields in changes.items():
                if "Kategori" in changed_fields:
                    item_id = edit_source.iloc[row_idx]["id"]
                    update_item_category(item_id, changed_fields["Kategori"])
            if changes:
                st.success(f"{len(changes)} kategori(er) uppdaterade.")
                st.rerun()
            else:
                st.info("Inga ändringar att spara.")

    # --- Receipt history table ---
    st.subheader("Kvittohistorik")
    if not receipts_df.empty:
        mask = (receipts_df["date"] >= start_date) & (
            receipts_df["date"] <= end_date
        )
        display_df = receipts_df[mask][
            ["date", "store", "total", "filename"]
        ].rename(
            columns={
                "date": "Datum",
                "store": "Butik",
                "total": "Summa (kr)",
                "filename": "Fil",
            }
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
