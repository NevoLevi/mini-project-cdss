# ui_streamlit.py — compliant UI
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, date, time
from cdss_loinc import CDSSDatabase, parse_dt

db = CDSSDatabase()

st.set_page_config(page_title="Mini-CDSS", layout="wide", page_icon="💉")
st.markdown("<style>section.main > div {max-width: 1200px;}</style>", unsafe_allow_html=True)
st.title("💉 Mini Clinical-Decision Support")

tab_hist, tab_upd, tab_del, tab_stat = st.tabs(["History", "Update", "Delete", "Status"])

# ═════════ HISTORY ═════════
with tab_hist:
    st.subheader("History query")
    c1, c2, c3 = st.columns(3)
    patient = c1.text_input("Patient")
    code    = c1.text_input("LOINC code / component")
    f_date  = c2.date_input("From", date(2018, 5, 17))
    t_date  = c2.date_input("To",   date(2018, 5, 18))
    hour    = c3.selectbox("Hour (optional)", ["—"] + [f"{h:02}:00" for h in range(24)])

    if st.button("Run"):
        try:
            hh = time.fromisoformat(hour) if hour != "—" else None
            res = db.history(
                patient, code,
                datetime.combine(f_date, time.min),
                datetime.combine(t_date, time.max),
                hh
            )
            st.success(f"{len(res)} rows")
            st.dataframe(res, use_container_width=True)

            if not res.empty:
                # unified datetime axis
                x_axis = alt.Axis(format="%Y-%m-%d %H:%M", labelAngle=-45, title="Timestamp")
                numeric = pd.to_numeric(res["Value"], errors="coerce")
                plot_df = res.copy()

                if numeric.notna().any():
                    plot_df["ValueNum"] = numeric
                    chart = (
                        alt.Chart(plot_df)
                        .mark_line(point=True)
                        .encode(
                            x=alt.X("Valid start time:T", axis=x_axis),
                            y=alt.Y("ValueNum:Q", title=f"{plot_df['Unit'].iloc[0]}"),
                            tooltip=["Valid start time:T", "ValueNum"]
                        )
                    )
                else:
                    cats = sorted(
                        db.df[db.df["LOINC-NUM"] == plot_df["LOINC-NUM"].iloc[0]]
                        ["Value"].astype(str).unique()
                    )
                    plot_df["cat"] = plot_df["Value"].astype(str)
                    chart = (
                        alt.Chart(plot_df)
                        .mark_circle(size=100)
                        .encode(
                            x=alt.X("Valid start time:T", axis=x_axis),
                            y=alt.Y("cat:N", sort=cats, title="Category"),
                            tooltip=["Valid start time:T", "cat"]
                        )
                        .properties(height=max(300, len(cats) * 75))
                    )

                st.altair_chart(chart, use_container_width=True)

        except Exception as e:
            st.error(str(e))

# ═════════ UPDATE ═════════
with tab_upd:
    st.subheader("Update measurement")
    patient_u = st.text_input("Patient", key="u_p")
    code_u    = st.text_input("Code / component", key="u_c")
    when_u    = st.text_input("Original Valid-time (YYYY-MM-DDTHH:MM or now)", key="u_t")
    new_val   = st.text_input("New value", key="u_v")

    if st.button("Apply update"):
        try:
            st.dataframe(db.update(patient_u, code_u, parse_dt(when_u), new_val))
            st.success("Row appended")
        except Exception as e:
            st.error(str(e))

# ═════════ DELETE ═════════
with tab_del:
    st.subheader("Delete measurement")
    patient_d = st.text_input("Patient", key="d_p")
    code_d    = st.text_input("Code / component", key="d_c")
    day_d     = st.text_input("Date (YYYY-MM-DD or today)", key="d_day")
    hh_opt    = st.selectbox("Hour (optional)", ["—"] + [f"{h:02}:00" for h in range(24)], key="d_hh")

    if st.button("Delete"):
        try:
            hh = time.fromisoformat(hh_opt) if hh_opt != "—" else None
            st.dataframe(db.delete(patient_d, code_d, parse_dt(day_d, date_only=True), hh))
            st.success("Deleted")
        except Exception as e:
            st.error(str(e))

# ═════════ STATUS ═════════
with tab_stat:
    st.subheader("Current status (latest value per LOINC)")
    st.dataframe(db.status(), use_container_width=True)
