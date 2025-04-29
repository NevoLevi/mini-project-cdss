# ui_streamlit.py — compliant UI
from __future__ import annotations

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

def loinc_choices_for(patient: str | None) -> list[str]:
    """Return codes/components seen for *that* patient."""
    if not patient:
        return []                         # no patient yet → empty dropdown

    # codes that actually appear for this patient
    codes = db.df.loc[db.df["Patient"] == patient, "LOINC-NUM"].unique().tolist()

    # # component aliases that map uniquely to one of those codes
    # comps = [
    #     comp for comp, code in cdss_loinc.COMP2CODE.items()
    #     if code in codes
    # ]
    #return sorted(set(codes + comps))
    return sorted(set(codes))



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
    code = c1.selectbox("LOINC code / component", options=loinc_choices_for(patient), index=None)
    f_date  = c2.date_input("From", date(2025, 4, 17))
    t_date  = c2.date_input("To",   date(2025, 4, 25))

    #hour    = c3.selectbox("Hour (optional)", ["—"] + [f"{h:02}:00" for h in range(24)])
    # NEW: hour-range (optional)
    from_hhmm = c3.text_input("From HH:MM (optional)", placeholder="00:00")
    to_hhmm   = c3.text_input("To HH:MM (optional)",   placeholder="23:59")

    if st.button("Run") and patient and code:
        try:
            # ───── parse / default hour-range ─────
            t_min = time.fromisoformat(from_hhmm) if from_hhmm else time(0, 0)
            t_max = time.fromisoformat(to_hhmm) if to_hhmm else time(23, 59)

            # build full datetimes
            start_dt = datetime.combine(f_date, t_min)
            end_dt = datetime.combine(t_date, t_max)

            # hour argument no longer needed → pass None
            res = db.history(
                patient, code,
                start_dt,
                end_dt,
                hh=None
            )

            st.success(f"{len(res)} rows")
            st.dataframe(res, use_container_width=True)

            if not res.empty:
                # unified datetime axis
                x_axis = alt.Axis(format="%Y-%m-%d %H:%M", labelAngle=-45,
                                  title="Timestamp")
                numeric = pd.to_numeric(res["Value"], errors="coerce")
                plot_df = res.copy()

                if numeric.notna().any():
                    plot_df["ValueNum"] = numeric
                    chart = (
                        alt.Chart(plot_df)
                        .mark_line(point=True)
                        .encode(
                            x=alt.X("Valid start time:T", axis=x_axis),
                            y=alt.Y("ValueNum:Q",
                                    title=f"{plot_df['Unit'].iloc[0]}"),
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

        except ValueError as e:  # bad HH:MM format or other issues
            st.error(str(e))


    # if st.button("Run") and patient and code:
    #     try:
    #         hh = time.fromisoformat(hour) if hour != "—" else None
    #         res = db.history(
    #             patient, code,
    #             datetime.combine(f_date, time.min),
    #             datetime.combine(t_date, time.max),
    #             hh
    #         )
    #         st.success(f"{len(res)} rows")
    #         st.dataframe(res, use_container_width=True)
    #
    #         if not res.empty:
    #             # unified datetime axis
    #             x_axis = alt.Axis(format="%Y-%m-%d %H:%M", labelAngle=-45, title="Timestamp")
    #             numeric = pd.to_numeric(res["Value"], errors="coerce")
    #             plot_df = res.copy()
    #
    #             if numeric.notna().any():
    #                 plot_df["ValueNum"] = numeric
    #                 chart = (
    #                     alt.Chart(plot_df)
    #                     .mark_line(point=True)
    #                     .encode(
    #                         x=alt.X("Valid start time:T", axis=x_axis),
    #                         y=alt.Y("ValueNum:Q", title=f"{plot_df['Unit'].iloc[0]}"),
    #                         tooltip=["Valid start time:T", "ValueNum"]
    #                     )
    #                 )
    #             else:
    #                 cats = sorted(
    #                     db.df[db.df["LOINC-NUM"] == plot_df["LOINC-NUM"].iloc[0]]
    #                     ["Value"].astype(str).unique()
    #                 )
    #                 plot_df["cat"] = plot_df["Value"].astype(str)
    #                 chart = (
    #                     alt.Chart(plot_df)
    #                     .mark_circle(size=100)
    #                     .encode(
    #                         x=alt.X("Valid start time:T", axis=x_axis),
    #                         y=alt.Y("cat:N", sort=cats, title="Category"),
    #                         tooltip=["Valid start time:T", "cat"]
    #                     )
    #                     .properties(height=max(300, len(cats) * 75))
    #                 )
    #
    #             st.altair_chart(chart, use_container_width=True)
    #
    #     except Exception as e:
    #         st.error(str(e))

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

    st.subheader("Update measurement")
    patient_u = st.selectbox("Patient", patient_list(), index=None, key="u_p",
                             placeholder="Start typing…")

    code_u = st.selectbox(
        "Code / component",
        loinc_choices_for(patient_u),
        index=None, key="u_c",
        placeholder="Pick a patient first…" if not patient_u else "Start typing…",
        disabled=patient_u is None
    )

    when_u = st.text_input(
        "Original Valid-time (YYYY-MM-DDTHH:MM or now)",
        key="u_t"
    )
    new_val = st.text_input("New value", key="u_v")

    if st.button("Apply update"):
        try:
            ts = cdss_loinc.parse_dt(when_u)          # handles “now”
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

    patient_d = st.selectbox("Patient", patient_list(), index=None, key="d_p",
                             placeholder="Start typing…")

    code_d = st.selectbox(
        "Code / component",
        loinc_choices_for(patient_d),
        index=None, key="d_c",
        placeholder="Pick a patient first…" if not patient_d else "Start typing…",
        disabled=patient_d is None
    )

    day_d = st.text_input("Date (YYYY-MM-DD or today)", key="d_day")
    hh_opt = st.selectbox(
        "Hour (optional)", ["—"] + [f"{h:02}:00" for h in range(24)], key="d_hh"
    )

    if st.button("Delete"):
        try:
            day_obj = cdss_loinc.parse_dt(day_d, date_only=True)
            hh_obj = None if hh_opt == "—" else time.fromisoformat(hh_opt)
            st.dataframe(db.delete(patient_d, code_d, day_obj, hh_obj))
            st.success("Deleted")
        except Exception as e:
            st.error(str(e))



# ═════════ STATUS ═════════
with tab_stat:
    st.subheader("Current status (latest value per LOINC)")
    st.dataframe(db.status(), use_container_width=True)
