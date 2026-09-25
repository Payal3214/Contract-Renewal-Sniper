import os
import pandas as pd
import streamlit as st
from datetime import date

from models import Contract, RISK_COLORS
from file_readers import extract_text
from extractor import extract_contract
from risk_engine import assess_risk, sort_key
import db

st.set_page_config(
    page_title="Contract Renewal Sniper",
    page_icon="🎯",
    layout="wide",
)

db.init_db()

# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

st.sidebar.title("🎯 Contract Renewal Sniper")
st.sidebar.caption("Stop silently auto-renewing what you meant to cancel.")

page = st.sidebar.radio("Navigate", ["📊 Dashboard", "📤 Upload & Extract", "⚙️ Settings"])

st.sidebar.divider()
api_key_input = st.sidebar.text_input(
    "Anthropic API key (optional, for higher-accuracy extraction)",
    type="password",
    value=st.session_state.get("api_key", os.environ.get("ANTHROPIC_API_KEY", "")),
    help="If left blank, extraction runs on fast local regex heuristics only. "
         "Add a key to use Claude for more accurate clause extraction on messy contracts.",
)
st.session_state["api_key"] = api_key_input
use_llm = st.sidebar.checkbox("Use Claude for extraction", value=bool(api_key_input), disabled=not api_key_input)

st.sidebar.divider()
st.sidebar.caption("Data is stored locally in `contracts.db` (SQLite).")


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

def render_dashboard():
    contracts = db.get_all_contracts()

    if not contracts:
        st.info("No contracts yet. Head to **📤 Upload & Extract** to add your first vendor contract.")
        return

    contracts.sort(key=sort_key)

    rows = []
    for c in contracts:
        level, days_left, reason = assess_risk(c)
        rows.append({
            "id": c.id,
            "Vendor": c.vendor_name or "Unknown",
            "Risk": level,
            "Days Left": days_left if days_left is not None else "—",
            "Cancel-by Deadline": c.cancellation_deadline or "—",
            "Renewal/End Date": c.end_date or "—",
            "Auto-Renews": "Yes" if c.auto_renews else ("No" if c.auto_renews is False else "Unknown"),
            "Notice (days)": c.notice_period_days if c.notice_period_days is not None else "—",
            "Price": f"${c.price_amount:,.2f}/{c.price_period}" if c.price_amount else "—",
            "File": c.filename,
        })
    df = pd.DataFrame(rows)

    # --- Top metrics ---
    counts = df["Risk"].value_counts().to_dict()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("🔴 Critical (≤7d)", counts.get("CRITICAL", 0))
    m2.metric("🟠 High (≤30d)", counts.get("HIGH", 0))
    m3.metric("🟡 Medium (≤60d)", counts.get("MEDIUM", 0))
    m4.metric("🟤 Already Past", counts.get("PAST", 0))
    m5.metric("📄 Total Contracts", len(df))

    st.divider()

    # --- Filters ---
    fcol1, fcol2 = st.columns([2, 1])
    with fcol1:
        risk_filter = st.multiselect(
            "Filter by risk level",
            ["CRITICAL", "HIGH", "MEDIUM", "LOW", "PAST", "UNKNOWN"],
            default=[],
        )
    with fcol2:
        search = st.text_input("Search vendor / filename", "")

    filtered = df.copy()
    if risk_filter:
        filtered = filtered[filtered["Risk"].isin(risk_filter)]
    if search:
        s = search.lower()
        filtered = filtered[
            filtered["Vendor"].str.lower().str.contains(s) | filtered["File"].str.lower().str.contains(s)
        ]

    st.subheader("Action List")
    st.caption("Sorted by urgency — deal with the top of this list first.")

    for _, row in filtered.iterrows():
        c = next(x for x in contracts if x.id == row["id"])
        level, days_left, reason = assess_risk(c)
        color = RISK_COLORS.get(level, "#9e9e9e")

        with st.container(border=True):
            top1, top2, top3 = st.columns([3, 2, 1])
            with top1:
                st.markdown(
                    f"<span style='background-color:{color};color:white;padding:2px 10px;"
                    f"border-radius:12px;font-size:0.75em;font-weight:600'>{level}</span> "
                    f"&nbsp;**{c.vendor_name or 'Unknown Vendor'}**",
                    unsafe_allow_html=True,
                )
                st.caption(reason)
            with top2:
                st.write(f"📅 Renewal/End: **{c.end_date or '—'}**")
                st.write(f"✉️ Notice required: **{c.notice_period_days if c.notice_period_days is not None else '—'} days**")
            with top3:
                if c.price_amount:
                    st.write(f"💰 **${c.price_amount:,.2f}**")
                    if c.price_period:
                        st.caption(f"per {c.price_period}")
                if st.button("Details", key=f"detail_{c.id}"):
                    st.session_state["selected_contract_id"] = c.id
                    st.session_state["nav_override"] = "detail"

    if st.session_state.get("nav_override") == "detail":
        st.divider()
        render_detail(st.session_state.get("selected_contract_id"))

    st.divider()
    csv = filtered.drop(columns=["id"]).to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Export action list as CSV", csv, "contract_renewal_action_list.csv", "text/csv")


def render_detail(contract_id):
    c = db.get_contract(contract_id)
    if not c:
        st.warning("Contract not found.")
        return

    level, days_left, reason = assess_risk(c)
    st.subheader(f"📄 {c.vendor_name} — {c.filename}")
    st.markdown(f"**Risk:** `{level}`  &nbsp;|&nbsp; **{reason}**")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Dates")
        st.write(f"Start date: {c.start_date or '—'}")
        st.write(f"Renewal / end date: {c.end_date or '—'}")
        st.write(f"Notice period required: {c.notice_period_days if c.notice_period_days is not None else '—'} days")
        st.write(f"Cancellation deadline: {c.cancellation_deadline or '—'}")
        st.write(f"Auto-renews: {c.auto_renews}")
        if c.renewal_term_text:
            st.markdown("**Renewal clause (extracted):**")
            st.info(c.renewal_term_text)

    with col2:
        st.markdown("##### Pricing")
        st.write(f"Amount: {'$' + format(c.price_amount, ',.2f') if c.price_amount else '—'}")
        st.write(f"Period: {c.price_period or '—'}")
        if c.price_text:
            st.markdown("**Price clause (extracted):**")
            st.info(c.price_text)
        if c.notes:
            st.markdown("**Notes / flags:**")
            st.warning(c.notes)

    st.markdown("##### Status")
    new_status = st.selectbox(
        "Update contract status",
        ["active", "cancelled", "renewed", "archived"],
        index=["active", "cancelled", "renewed", "archived"].index(c.status if c.status in
              ["active", "cancelled", "renewed", "archived"] else "active"),
        key=f"status_{c.id}",
    )
    cbtn1, cbtn2, cbtn3 = st.columns(3)
    with cbtn1:
        if st.button("💾 Save status"):
            c.status = new_status
            db.update_contract(c.id, c)
            st.success("Updated.")
    with cbtn2:
        with st.expander("Raw text excerpt"):
            st.code(c.raw_text_excerpt or "(none captured)")
    with cbtn3:
        if st.button("🗑️ Delete contract", type="secondary"):
            db.delete_contract(c.id)
            st.session_state["nav_override"] = None
            st.success("Deleted.")
            st.rerun()


# --------------------------------------------------------------------------
# Upload & Extract
# --------------------------------------------------------------------------

def render_upload():
    st.subheader("📤 Upload vendor / SaaS contracts")
    st.caption("PDF, DOCX or TXT. Upload as many as you like — each is parsed independently.")

    files = st.file_uploader(
        "Drop contract files here",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
    )

    if files and st.button(f"🔍 Extract {len(files)} contract(s)", type="primary"):
        api_key = st.session_state.get("api_key")
        progress = st.progress(0.0, text="Starting extraction...")
        results = []
        for i, f in enumerate(files):
            progress.progress((i) / len(files), text=f"Reading {f.name}...")
            text = extract_text(f.name, f.read())
            if not text or text.strip() == "":
                st.warning(f"Could not extract any text from {f.name} — skipping.")
                continue
            progress.progress((i + 0.5) / len(files), text=f"Analyzing {f.name}...")
            contract = extract_contract(f.name, text, use_llm=use_llm, api_key=api_key)
            contract_id = db.add_contract(contract)
            contract.id = contract_id
            results.append(contract)
        progress.progress(1.0, text="Done.")

        st.success(f"Extracted and saved {len(results)} contract(s).")
        for c in results:
            level, days_left, reason = assess_risk(c)
            with st.container(border=True):
                st.markdown(f"**{c.vendor_name}** — `{level}`")
                st.caption(reason)

        st.info("Go to **📊 Dashboard** to see the full risk-sorted action list.")

    st.divider()
    st.markdown("##### Try it with sample contracts")
    st.caption("No files handy? Load two bundled sample contracts to see how it works.")
    if st.button("Load sample contracts"):
        api_key = st.session_state.get("api_key")
        sample_dir = os.path.join(os.path.dirname(__file__), "sample_data")
        loaded = 0
        for fname in os.listdir(sample_dir):
            path = os.path.join(sample_dir, fname)
            with open(path, "rb") as fh:
                text = extract_text(fname, fh.read())
            contract = extract_contract(fname, text, use_llm=use_llm, api_key=api_key)
            cid = db.add_contract(contract)
            contract.id = cid
            loaded += 1
        st.success(f"Loaded {loaded} sample contract(s). Check the Dashboard.")


def render_settings():
    st.subheader("⚙️ Settings")
    st.markdown(
        """
        **Extraction modes**
        - *Regex mode* (default): fast, free, runs fully locally using pattern matching
          for dates, `"X days' notice"` clauses, auto-renewal language, and dollar amounts.
        - *Claude mode* (optional): paste an Anthropic API key in the sidebar to send
          contract text to Claude for more accurate structured extraction on messy,
          inconsistently worded contracts. Falls back to regex automatically if the call fails.

        **Data storage**

        All extracted contracts are stored in a local SQLite file (`contracts.db`) next to
        the app. On Streamlit Community Cloud this resets on redeploy — for production use,
        swap `db.py` for a hosted Postgres/Supabase connection (the interface is a handful
        of functions, so this is a small change).

        **Danger zone**
        """
    )
    if st.button("🗑️ Delete ALL contracts", type="secondary"):
        for c in db.get_all_contracts():
            db.delete_contract(c.id)
        st.success("All contracts deleted.")


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

if page == "📊 Dashboard":
    st.title("📊 Renewal Risk Dashboard")
    render_dashboard()
elif page == "📤 Upload & Extract":
    st.title("📤 Upload & Extract")
    render_upload()
else:
    render_settings()
