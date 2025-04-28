# ui_streamlit.py — compliant UI
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, date, time

import cdss_loinc
from cdss_loinc import CDSSDatabase, parse_dt

db = CDSSDatabase()


def patient_list() -> list[str]:
    """Always current list of patients."""
    return sorted(db.df["Patient"].unique())

def loinc_choices() -> list[str]:
    """Codes + unique component names."""
    codes = db.df["LOINC-NUM"].unique().tolist()
    #comps = list(cdss_loinc.COMP2CODE.keys())
    #return sorted(set(codes + comps))
    return sorted(set(codes))

def valid_times(patient: str, code: str) -> list[str]:
    """Return ISO timestamps ('YYYY-MM-DDTHH:MM') of existing rows."""
    m = (db.df["Patient"] == patient) & (db.df["LOINC-NUM"] == code)
    return sorted(db.df.loc[m, "Valid start time"].dt.strftime("%Y-%m-%dT%H:%M").unique())



st.set_page_config(page_title="Mini-CDSS", layout="wide", page_icon="💉")
st.markdown("<style>section.main > div {max-width: 1200px;}</style>", unsafe_allow_html=True)
st.title("💉 Mini Clinical-Decision Support")

tab_hist, tab_upd, tab_del, tab_stat = st.tabs(["History", "Update", "Delete", "Status"])

# ═════════ HISTORY ═════════
with tab_hist:
    st.subheader("History query")
    c1, c2, c3 = st.columns(3)
    #patient = c1.text_input("Patient")
    patient = c1.selectbox( "Patient", options=patient_list(),index=None, placeholder="Start typing…")
    #code    = c1.text_input("LOINC code / component")
    code = c1.selectbox("LOINC code / component", options=loinc_choices(), index=None)
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
    # st.subheader("Update measurement")
    # patient_u = st.text_input("Patient", key="u_p")
    # code_u    = st.text_input("Code / component", key="u_c")
    # when_u    = st.text_input("Original Valid-time (YYYY-MM-DDTHH:MM or now)", key="u_t")
    # new_val   = st.text_input("New value", key="u_v")

    # if st.button("Apply update"):
    #     try:
    #         st.dataframe(db.update(patient_u, code_u, parse_dt(when_u), new_val))
    #         st.success("Row appended")
    #     except Exception as e:
    #         st.error(str(e))

    cols = st.columns(3)
    patient_u = cols[0].selectbox("Patient", patient_list(), index=None, key="u_p")
    code_u = cols[0].selectbox("Code / component", loinc_choices(), index=None, key="u_c")

    # container that will hold the selectbox once we have both keys
    time_container = cols[1].empty()
    new_val = cols[2].text_input("New value", key="u_v")

    # ------- dynamic time dropdown -------
    if patient_u and code_u:
        choices = ["now"] + valid_times(patient_u, cdss_loinc.CDSSDatabase._normalise_code(db, code_u))
        when_u = time_container.selectbox(
            "Original Valid-time",
            choices,
            index=0,   # default to "now"
            key="u_t",
            placeholder="Pick or type…"
        )
    else:
        when_u = None    # not ready yet

    if st.button("Apply update") and patient_u and code_u and when_u:
        try:
            ts = datetime.now() if when_u == "now" else cdss_loinc.parse_dt(when_u)
            st.dataframe(db.update(patient_u, code_u, ts, new_val))
            st.success("Row appended")
        except Exception as e:
            st.error(str(e))


# ═════════ DELETE ═════════
with tab_del:
    st.subheader("Delete measurement")
    # patient_d = st.text_input("Patient", key="d_p")
    # code_d    = st.text_input("Code / component", key="d_c")
    # day_d     = st.text_input("Date (YYYY-MM-DD or today)", key="d_day")
    # hh_opt    = st.selectbox("Hour (optional)", ["—"] + [f"{h:02}:00" for h in range(24)], key="d_hh")
    #
    # if st.button("Delete"):
    #     try:
    #         hh = time.fromisoformat(hh_opt) if hh_opt != "—" else None
    #         st.dataframe(db.delete(patient_d, code_d, parse_dt(day_d, date_only=True), hh))
    #         st.success("Deleted")
    #     except Exception as e:
    #         st.error(str(e))

    c1, c2, c3 = st.columns(3)

    patient_d = c1.selectbox("Patient", patient_list(), index=None, key="d_p")
    code_d = c1.selectbox("Code / component", loinc_choices(), index=None, key="d_c")

    date_box = c2.empty()
    hour_box = c3.empty()

    if patient_d and code_d:
        # full list of timestamps
        ts_list = valid_times(patient_d, cdss_loinc.CDSSDatabase._normalise_code(db, code_d))
        # split into unique dates and, later, hours
        dates = sorted({t.split('T')[0] for t in ts_list})
        sel_date = date_box.selectbox("Date", ["today"] + dates, index=0, key="d_day")

        if sel_date == "today":
            # deleting today's measurement → hour dropdown becomes blank
            sel_hour = hour_box.selectbox("Hour (optional)", ["—"], index=0, key="d_hh")
        else:
            # hours that exist on that date
            hours = [t.split('T')[1] for t in ts_list if t.startswith(sel_date)]
            sel_hour = hour_box.selectbox("Hour (optional)", ["—"] + hours, index=0, key="d_hh")
    else:
        sel_date = sel_hour = None

    if st.button("Delete") and patient_d and code_d and sel_date:
        try:
            day_obj = date.today() if sel_date == "today" else cdss_loinc.parse_dt(sel_date, date_only=True)
            hh_obj = None if sel_hour in (None, "—") else time.fromisoformat(sel_hour)
            st.dataframe(db.delete(patient_d, code_d, day_obj, hh_obj))
            st.success("Deleted")
        except Exception as e:
            st.error(str(e))




# ═════════ STATUS ═════════
with tab_stat:
    st.subheader("Current status (latest value per LOINC)")
    st.dataframe(db.status(), use_container_width=True)
