import streamlit as st
from workflows.system_cycle import run_full_operations_cycle
from agents.analyst_agent import run_analysis_cycle
from agents.procurement_agent import run_procurement_cycle
from agents.logistics_agent import run_logistics_cycle

st.set_page_config(page_title="AI Operations Command Center", layout="wide")

st.title("AI Operations Command Center")
st.caption("Agent-Based Manufacturing Intelligence System")

st.markdown("---")

# ==============================
# BUTTON SECTION
# ==============================

col1, col2 = st.columns(2)

with col1:
    run_analyst = st.button("Run Analyst Agent")
    run_procurement = st.button("Run Procurement Agent")

with col2:
    run_logistics = st.button("Run Logistics Agent")
    run_full = st.button("Run Full System (Phase 2)")

st.markdown("---")

# ==============================
# ANALYST AGENT
# ==============================

if run_analyst:
    with st.spinner("Analyzing production logs..."):
        result = run_analysis_cycle()

    st.success("Analyst Agent Complete")

    st.header("📊 KPI Summary")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Production Growth (7 Days)", f"{result['trend_percent']}%")

    with col2:
        st.metric("Scrap Rate", f"{result['scrap_rate']}%")

    st.header("🧠 Executive Summary")
    st.markdown(result["summary"])


# ==============================
# PROCUREMENT AGENT
# ==============================

if run_procurement:
    with st.spinner("Evaluating inventory levels..."):
        result = run_procurement_cycle()

    st.success("Procurement Agent Complete")

    st.header("📦 Procurement Actions")

    if isinstance(result, str):
        st.info(result)
    else:
        for vendor, email_text in result.items():
            with st.expander(f"Purchase Order → {vendor}"):
                st.markdown(email_text)


# ==============================
# LOGISTICS AGENT
# ==============================

if run_logistics:
    with st.spinner("Evaluating shipment risks..."):
        result = run_logistics_cycle()

    st.success("Logistics Agent Complete")

    st.header("🚚 Logistics Risk Assessment")
    st.markdown(result)


# ==============================
# FULL SYSTEM (PHASE 2)
# ==============================

if run_full:
    with st.spinner("Running AI Operations Cycle..."):
        result = run_full_operations_cycle()

    st.success("AI Operations Cycle Complete")

    # ==============================
    # KPI DASHBOARD
    # ==============================

    st.header("📊 Executive KPI Overview")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Production Growth (7 Days)",
            value=f"{result['trend_percent']}%",
            delta=f"{result['trend_percent']}%"
        )

    with col2:
        scrap = result["scrap_rate"]
        st.metric(
            label="Scrap Rate",
            value=f"{scrap}%",
            delta="Review Required" if scrap > 3.5 else "Stable"
        )

    with col3:
        roi_value = result.get("roi", {}).get("total_savings", 0)
        st.metric(
            label="AI Estimated Value Created",
            value=f"${roi_value:,.2f}"
        )

    st.markdown("---")

    # ==============================
    # ANALYST OUTPUT
    # ==============================

    st.header("🧠 Analyst Executive Summary")
    st.markdown(result["analyst_summary"])

    st.markdown("---")

    # ==============================
    # PROCUREMENT OUTPUT
    # ==============================

    st.header("📦 Procurement Actions")

    for vendor, email_text in result["procurement_output"].items():
        with st.expander(f"View Purchase Order → {vendor}"):
            st.markdown(email_text)

    st.markdown("---")

    # ==============================
    # LOGISTICS OUTPUT
    # ==============================

    st.header("🚚 Logistics Risk Assessment")
    st.markdown(result["logistics_output"])

    st.markdown("---")

    # ==============================
    # ROI PANEL
    # ==============================

    st.subheader("💰 Strategic Impact")

    st.info(f"""
AI-driven reorder adjustments and risk mitigation strategies optimized operational continuity.

Estimated Value Created: **${roi_value:,.2f}**
""")