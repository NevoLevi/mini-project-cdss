# ui_streamlit.py — Enhanced UI for Part 2
from __future__ import annotations

import re
import json

import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import cdss_loinc
from cdss_loinc import CDSSDatabase, parse_dt
import cdss_clean
from cdss_clean import CleanCDSSDatabase

db = CleanCDSSDatabase()
IL_TZ = ZoneInfo("Asia/Jerusalem")


def patient_list() -> list[str]:
    """Always current list of patients."""
    df = db.demographics_df
    if 'Patient_Name' in df.columns:
        return sorted(df["Patient_Name"].dropna().unique())
    elif {'First_name', 'Last_name'}.issubset(df.columns):
        names = (df['First_name'].str.title().str.strip() + ' ' + df['Last_name'].str.title().str.strip()).unique()
        return sorted(names)
    else:
        # Fallback to Patient_ID if name columns not available
        return sorted(df["Patient_ID"].unique())

def get_patient_id_from_name(patient_name: str) -> str:
    """Convert patient name to Patient_ID for database queries."""
    df = db.demographics_df
    if 'Patient_Name' in df.columns:
        match = df[df['Patient_Name'] == patient_name]
        if not match.empty:
            return match.iloc[0]['Patient_ID']
    if {'First_name', 'Last_name'}.issubset(df.columns):
        # Split provided name and attempt match
        try:
            first, last = patient_name.split(' ', 1)
        except ValueError:
            first, last = patient_name, ''
        match = df[(df['First_name'].str.strip().str.title() == first.title()) & (df['Last_name'].str.strip().str.title() == last.title())]
        if not match.empty:
            return match.iloc[0]['Patient_ID']
    # If no match, assume it's already a Patient_ID
    return patient_name

def loinc_choices() -> list[str]:
    """Codes + unique component names."""
    codes = db.lab_results_df["LOINC_Code"].unique().tolist()
    return sorted(set(codes))

def loinc_choices_for(patient: str | None) -> list[str]:
    """Return codes/components seen for *that* patient."""
    if not patient:
        return []                         # no patient yet → empty dropdown

    # Convert patient name to Patient_ID if needed
    patient_id = get_patient_id_from_name(patient)
    
    # codes that actually appear for this patient
    codes = db.lab_results_df.loc[db.lab_results_df["Patient_ID"] == patient_id, "LOINC_Code"].unique().tolist()
    return sorted(set(codes))




_HHMM_RGX = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")   # 00:00–23:59

def parse_hhmm(txt: str | None) -> time | None:
    """Return `time` if txt is valid HH:MM; else raise ValueError."""
    if not txt:            # empty → caller will default later
        return None
    if not _HHMM_RGX.match(txt):
        raise ValueError("Use HH:MM  (e.g., 08:30, 17:05)")
    return time.fromisoformat(txt)

def _set_now(prefix):
    now = datetime.now(IL_TZ).replace(second=0, microsecond=0)
    st.session_state[f"{prefix}_date"] = now.date()
    # Use the correct key naming based on the context
    if prefix == "context":
        st.session_state["context_time"] = now.strftime("%H:%M")
    else:
        st.session_state[f"{prefix}_time_str"] = now.strftime("%H:%M")


st.set_page_config(
    page_title="Clinical Decision Support System",
    layout="wide",
    page_icon="🏥",
    initial_sidebar_state="collapsed"
)

# Modern CSS styling
st.markdown("""
<style>
    /* Main container styling */
    .main > div {
        padding-top: 1rem;
        max-width: 1400px;
    }
    
    /* Custom header styling */
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem 2rem 3rem 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
    }
    
    .header-title {
        color: white;
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
        text-align: center;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    
    .header-subtitle {
        color: rgba(255,255,255,0.9);
        font-size: 1.1rem;
        text-align: center;
        margin-top: 0.5rem;
        font-weight: 300;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 0.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0px 24px;
        background-color: white;
        border-radius: 8px;
        color: #495057;
        font-weight: 500;
        border: 1px solid #e9ecef;
        transition: all 0.3s ease;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
        border: 1px solid transparent;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    
    /* Card styling */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);
        border: 1px solid #e9ecef;
        margin: 0.5rem 0;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
    }
    
    /* Success/Warning/Error styling */
    .status-success {
        background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
        color: white;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    
    .status-warning {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        color: white;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    
    .status-info {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        color: white;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 500;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.2);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 8px;
        border: 1px solid #dee2e6;
    }
    
    /* Input styling */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #e9ecef;
        transition: border-color 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    .stSelectbox > div > div > div {
        border-radius: 8px;
        border: 2px solid #e9ecef;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Progress indicators */
    .progress-container {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #667eea;
    }
    
    /* Professional spacing */
    .section-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent 0%, #dee2e6 50%, transparent 100%);
        margin: 2rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Professional header
st.markdown("""
<div class="header-container">
    <h1 class="header-title">🏥 Clinical Decision Support System</h1>
    <p class="header-subtitle">Advanced Medical Analytics & Treatment Recommendations Platform</p>
</div>
""", unsafe_allow_html=True)

# Enhanced tabs for Part 2 requirements
tab_dashboard, tab_context_queries, tab_kb_editor, tab_recommendations, tab_intervals, tab_hist, tab_upd, tab_del = st.tabs([
    "🏥 Clinical Dashboard", "🔍 Smart Queries", "📚 Knowledge Base", 
    "💊 Recommendation Board", "📊 State Analysis", "📋 Patient History", "✏️ Update Records", "🗑️ Delete Records"
])

# Enhanced Dashboard Tab
with tab_dashboard:
    st.markdown("""
    <div class="section-divider"></div>
    """, unsafe_allow_html=True)
    
    # Professional header section
    st.markdown("""
    <div class="metric-card">
        <h2 style="color: #495057; margin-bottom: 0.5rem;">🏥 Clinical Dashboard</h2>
        <p style="color: #6c757d; margin: 0;"><strong>Purpose:</strong> Real-time snapshot of ALL patients' clinical states at any specific time point - enables comprehensive hospital-wide status monitoring and rapid identification of critical patients requiring immediate attention.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Control panel with modern styling
    st.markdown("#### ⚙️ Dashboard Controls")
    dash_c1, dash_c2, dash_c3 = st.columns([2, 2, 1])
    
    with dash_c1:
        query_date = st.date_input("📅 Snapshot Date", key="dash_date")
        query_time_str = st.text_input("🕐 Time (HH:MM)", value="00:00", key="dash_time", placeholder="Enter time in 24-hour format")
    
    with dash_c2:
        auto_refresh = st.checkbox("🔄 Auto-refresh (30s)", help="Automatically refresh dashboard every 30 seconds")
        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    
    with dash_c3:
        st.markdown("<div style='height: 1.8em;'></div>", unsafe_allow_html=True)
        refresh_clicked = st.button("🔄 Refresh Now", type="primary", use_container_width=True)

    # Always show dashboard data (refresh makes it update, but show by default)
    # parse time or default to midnight
    qt = parse_hhmm(query_time_str) or time(0, 0)
    query_dt = datetime.combine(query_date, qt)
    
    # Use session state caching for dashboard data to improve performance
    cache_key = f"dashboard_{query_dt.strftime('%Y%m%d_%H%M')}"
    
    if refresh_clicked or auto_refresh or cache_key not in st.session_state:
        # Only fetch data when refresh is clicked or data is not cached
        df_states = db.get_all_patient_states_at_time(query_dt)
        st.session_state[cache_key] = df_states
        # Clear old cache entries (keep only last 5)
        cache_keys = [k for k in st.session_state.keys() if k.startswith('dashboard_')]
        if len(cache_keys) > 5:
            for old_key in cache_keys[:-5]:
                del st.session_state[old_key]
    else:
        # Use cached data
        df_states = st.session_state[cache_key]
    
    if not df_states.empty:
        # Status indicator
        st.markdown(f"""
        <div class="status-success">
            <strong>📅 System Status:</strong> Displaying {len(df_states)} patient records as of {query_dt.strftime('%Y-%m-%d %H:%M')}
        </div>
        """, unsafe_allow_html=True)
        
        # Enhanced summary statistics with modern cards - MOVED TO TOP
        st.markdown("#### 📈 Clinical Summary")
        
        # Create a hash for caching purposes
        df_hash = str(hash(tuple(df_states.values.tobytes() if not df_states.empty else b'')))
        
        # Cache summary calculations for better performance
        @st.cache_data(ttl=60)
        def calculate_summary_stats(df_hash):
            """Calculate summary statistics with caching"""
            total_patients = len(df_states)
            anemia_count = len(df_states[df_states['Hemoglobin-state'].str.contains('Anemia', na=False)])
            high_toxicity = len(df_states[df_states['Systemic-Toxicity'].str.contains('Grade [34]', na=False, regex=True)])
            need_treatment = len(df_states[~df_states['Recommendation'].str.contains('No specific|N/A', na=False, regex=True)])
            normal_count = len(df_states[df_states['Hemoglobin-state'].str.contains('Normal', na=False)])
            
            return {
                'total': total_patients,
                'anemia': anemia_count,
                'high_toxicity': high_toxicity, 
                'need_treatment': need_treatment,
                'normal': normal_count
            }
        
        # Get cached stats
        stats = calculate_summary_stats(df_hash)
        
        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
        
        with summary_col1:
            anemia_pct = (stats['anemia'] / stats['total'] * 100) if stats['total'] > 0 else 0
            
            st.markdown(f"""
            <div class="metric-card">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <h3 style="color: #dc3545; margin: 0; font-size: 2rem;">{stats['anemia']}</h3>
                        <p style="color: #6c757d; margin: 0; font-size: 0.9rem;">Anemia Cases</p>
                        <small style="color: #28a745;">{anemia_pct:.1f}% of patients</small>
                    </div>
                    <div style="font-size: 2.5rem; color: #dc3545;">🩸</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with summary_col2:
            toxicity_pct = (stats['high_toxicity'] / stats['total'] * 100) if stats['total'] > 0 else 0
            
            st.markdown(f"""
            <div class="metric-card">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <h3 style="color: #fd7e14; margin: 0; font-size: 2rem;">{stats['high_toxicity']}</h3>
                        <p style="color: #6c757d; margin: 0; font-size: 0.9rem;">High Toxicity</p>
                        <small style="color: #6c757d;">Grade III/IV ({toxicity_pct:.1f}%)</small>
                    </div>
                    <div style="font-size: 2.5rem; color: #fd7e14;">⚠️</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with summary_col3:
            treatment_pct = (stats['need_treatment'] / stats['total'] * 100) if stats['total'] > 0 else 0
            
            st.markdown(f"""
            <div class="metric-card">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <h3 style="color: #198754; margin: 0; font-size: 2rem;">{stats['need_treatment']}</h3>
                        <p style="color: #6c757d; margin: 0; font-size: 0.9rem;">Active Treatment</p>
                        <small style="color: #198754;">{treatment_pct:.1f}% of patients</small>
                    </div>
                    <div style="font-size: 2.5rem; color: #198754;">💊</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with summary_col4:
            normal_pct = (stats['normal'] / stats['total'] * 100) if stats['total'] > 0 else 0
            
            st.markdown(f"""
            <div class="metric-card">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <h3 style="color: #20c997; margin: 0; font-size: 2rem;">{stats['normal']}</h3>
                        <p style="color: #6c757d; margin: 0; font-size: 0.9rem;">Normal Status</p>
                        <small style="color: #20c997;">Healthy ({normal_pct:.1f}%)</small>
                    </div>
                    <div style="font-size: 2.5rem; color: #20c997;">✅</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Modern patient overview section
        st.markdown("#### 👥 Patient Status Overview")
        
        # Sort patients: non-normal conditions first, then normal - OPTIMIZED
        @st.cache_data(ttl=60)  # Cache for 60 seconds
        def get_sorted_patient_indices(df_states_hash):
            """Optimized patient sorting with caching"""
            def sort_priority(row):
                # Simplified priority logic for better performance
                hemoglobin_state = str(row.get('Hemoglobin-state', ''))
                systemic_toxicity = str(row.get('Systemic-Toxicity', ''))
                
                # Critical conditions (priority 0)
                if 'Grade IV' in systemic_toxicity:
                    return (0, row['Patient'])
                # High priority conditions (priority 1)
                elif 'Anemia' in hemoglobin_state or 'Grade III' in systemic_toxicity:
                    return (1, row['Patient'])
                # Medium priority conditions (priority 2)
                elif 'Grade II' in systemic_toxicity:
                    return (2, row['Patient'])
                # Normal conditions (priority 3)
                else:
                    return (3, row['Patient'])
            
            # Sort and return indices
            return df_states.apply(sort_priority, axis=1).sort_values().index
        
        # Create a hash for caching and get sorted dataframe
        sorted_indices = get_sorted_patient_indices(df_hash)
        sorted_df_states = df_states.loc[sorted_indices]
        
        # Add pagination for better performance
        total_patients = len(sorted_df_states)
        patients_per_page = 10  # Show 10 patients per page
        
        if total_patients > patients_per_page:
            # Add pagination controls
            col_prev, col_info, col_next = st.columns([1, 2, 1])
            
            if 'patient_page' not in st.session_state:
                st.session_state.patient_page = 0
            
            max_page = (total_patients - 1) // patients_per_page
            
            with col_prev:
                if st.button("◀️ Previous", disabled=st.session_state.patient_page == 0):
                    st.session_state.patient_page = max(0, st.session_state.patient_page - 1)
                    st.rerun()
            
            with col_info:
                start_idx = st.session_state.patient_page * patients_per_page + 1
                end_idx = min((st.session_state.patient_page + 1) * patients_per_page, total_patients)
                st.markdown(f"<div style='text-align: center; padding: 0.5rem;'>Showing patients {start_idx}-{end_idx} of {total_patients}</div>", unsafe_allow_html=True)
            
            with col_next:
                if st.button("Next ▶️", disabled=st.session_state.patient_page >= max_page):
                    st.session_state.patient_page = min(max_page, st.session_state.patient_page + 1)
                    st.rerun()
            
            # Get patients for current page
            start_idx = st.session_state.patient_page * patients_per_page
            end_idx = start_idx + patients_per_page
            page_df_states = sorted_df_states.iloc[start_idx:end_idx]
        else:
            page_df_states = sorted_df_states
        
        # Create modern card-based display with paginated patients
        for i, (_, patient_row) in enumerate(page_df_states.iterrows(), 1):
            # Adjust numbering for pagination
            if total_patients > patients_per_page:
                display_number = st.session_state.patient_page * patients_per_page + i
            else:
                display_number = i
                
            patient_id = patient_row['Patient']
            patient_name = patient_row.get('Patient_Name', f'Patient {patient_id}')
            
            # Determine border color based on toxicity grade
            toxicity_val = str(patient_row.get('Systemic-Toxicity', '')).upper()
            if any(g in toxicity_val for g in ["GRADE 4", "GRADE IV", "4"]):
                border_color = "#fd7e14"  # deep orange
            elif any(g in toxicity_val for g in ["GRADE 3", "GRADE III", "3"]):
                border_color = "#ffa94d"  # lighter orange
            else:
                border_color = "#e9ecef"  # default light gray

            # Patient status card with dynamic styling
            st.markdown(f"""
            <div class="metric-card" style="border-left: 6px solid {border_color};">
                <h4 style="color: #495057; margin-bottom: 1rem; display: flex; align-items: center;">
                    <span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; 
                         padding: 0.2rem 0.6rem; border-radius: 50%; margin-right: 0.8rem; font-size: 0.9rem;">
                        {display_number}
                    </span>
                    👤 {patient_name} <small style="color: #6c757d; margin-left: 0.5rem;">(ID: {patient_id})</small>
                </h4>
            </div>
            """, unsafe_allow_html=True)
            
            # Patient details in columns
            col1, col2, col3, col4 = st.columns([1, 1, 1, 1])




            #
            # # ═════════ DEBUG WINDOW ═════════
            # with st.expander("🛠 Debug log"):
            #     if "debug_lines" not in st.session_state:
            #         st.session_state.debug_lines = []
            #
            #     for line in st.session_state.debug_lines:
            #         st.code(line, language="text")
            #
            #
            # #DEBUG ##
            # st.session_state.debug_lines.append(f"{query_dt}")
            # st.session_state.debug_lines.append(df_states.to_string(index=False))








            with col1:
                st.markdown("**👤 Demographics**")
                st.metric("Gender", patient_row.get('Gender', 'N/A'))
            
            with col2:
                st.markdown("**📋 Latest Measurements**")
                
                # Simplified measurements display - avoid individual database calls
                with st.expander("🔬 View All Measurements", expanded=False):
                    # Use data already available in the patient_row instead of making new DB calls
                    hgb_level = patient_row.get('Hemoglobin-level', 'N/A')
                    wbc_level = patient_row.get('WBC-level', 'N/A')
                    
                    if hgb_level and str(hgb_level).lower() not in ['nan', 'none', '', 'n/a']:
                        st.text(f"🩸 Hemoglobin: {hgb_level} g/dL")
                    else:
                        st.text("🩸 Hemoglobin: No valid values")
                    
                    if wbc_level and str(wbc_level).lower() not in ['nan', 'none', '', 'n/a']:
                        if isinstance(wbc_level, (int, float)):
                            st.text(f"🔬 WBC Count: {wbc_level:,.0f} cells/μL")
                        else:
                            st.text(f"🔬 WBC Count: {wbc_level} cells/μL")
                    else:
                        st.text("🔬 WBC Count: No valid values")

                    # Show basic clinical observations from patient row data
                    st.text("🌡️ Temperature: Check patient history")
                    st.text("👁️ Skin Look: Check clinical observations")
                    st.text("🥶 Chills: Check clinical observations") 
                    st.text("⚠️ Allergic State: Check clinical observations")
            
            with col3:
                st.markdown("**🔬 Clinical Status**")
                
                # Hemoglobin status with color coding - MOVED HERE
                hemoglobin_state = patient_row.get('Hemoglobin-state', 'N/A')
                if "Anemia" in str(hemoglobin_state):
                    st.markdown(f"""
                    <div class="status-warning">
                        <strong>🩸 Hemoglobin:</strong> {hemoglobin_state}
                    </div>
                    """, unsafe_allow_html=True)
                elif "Normal" in str(hemoglobin_state):
                    st.markdown(f"""
                    <div class="status-success">
                        <strong>🩸 Hemoglobin:</strong> {hemoglobin_state}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="status-info">
                        <strong>🩸 Hemoglobin:</strong> {hemoglobin_state}
                    </div>
                    """, unsafe_allow_html=True)
                
                # Hematological state
                hematological_state = patient_row.get('Hematological-state', 'N/A')
                if any(word in str(hematological_state) for word in ["Anemia", "Leukemia", "Pancytopenia"]):
                    st.markdown(f"""
                    <div class="status-warning">
                        <strong>🔬 Hematology:</strong> {hematological_state}
                    </div>
                    """, unsafe_allow_html=True)
                elif "Normal" in str(hematological_state):
                    st.markdown(f"""
                    <div class="status-success">
                        <strong>🔬 Hematology:</strong> {hematological_state}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="status-info">
                        <strong>🔬 Hematology:</strong> {hematological_state}
                    </div>
                    """, unsafe_allow_html=True)
                
                # Systemic toxicity
                systemic_toxicity = patient_row.get('Systemic-Toxicity', 'N/A')
                if any(g in str(systemic_toxicity) for g in ["IV", "4", "III", "3"]):
                    st.markdown(f"""
                    <div class="status-warning">
                        <strong>⚠️ Toxicity:</strong> {systemic_toxicity}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="status-success">
                        <strong>⚠️ Toxicity:</strong> {systemic_toxicity}
                    </div>
                    """, unsafe_allow_html=True)
            
            with col4:
                st.markdown("**💊 Treatment Status**")
                recommendation = patient_row.get('Recommendation', 'N/A')
                if recommendation and recommendation not in ["N/A", "No specific treatment"]:
                    st.markdown("""
                    <div class="status-success">
                        <strong>✅ Active Treatment</strong>
                    </div>
                    """, unsafe_allow_html=True)
                    with st.expander("📋 View Treatment Plan", expanded=False):
                        st.markdown(f"**Recommendation:**")
                        st.text(recommendation.replace('\\n', '\n'))
                else:
                    st.markdown("""
                    <div class="status-info">
                        <strong>ℹ️ Monitoring</strong><br/>
                        <small>No active treatment required</small>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Add subtle divider between patients
            st.markdown("""
            <div style="height: 1px; background: #e9ecef; margin: 1.5rem 0;"></div>
            """, unsafe_allow_html=True)
    # else:
    #     st.markdown("""
    #     <div class="status-info">
    #         <strong>ℹ️ No Patient Data:</strong> No patient states found for the selected date and time.
    #         <br><small>Try selecting a different date or time, or check if data exists for this period.</small>
    #     </div>
    #     """, unsafe_allow_html=True)

# Context-Based Queries Tab
with tab_context_queries:
    st.markdown("""
    <div class="section-divider"></div>
    """, unsafe_allow_html=True)
    
    # Professional header section
    st.markdown("""
    <div class="metric-card">
        <h2 style="color: #495057; margin-bottom: 0.5rem;">🔍 Smart Clinical Queries</h2>
        <p style="color: #6c757d; margin: 0;">Advanced patient search based on clinical states and temporal conditions</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Enhanced time selection controls
    st.markdown("#### ⚙️ Query Parameters")
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        query_date = st.date_input("📅 Query Date", value=date(2025, 6, 12), key="context_date", help="Select the date for temporal query")
    
    with col2:
        # Use session state value if available, otherwise default to 20:00
        default_time = st.session_state.get("context_time", "20:00")
        query_time_str = st.text_input("🕐 Query Time (HH:MM)", value=default_time, key="context_time", placeholder="Enter time in 24-hour format")
    
    with col3:
        st.markdown("<div style='height: 1.8em;'></div>", unsafe_allow_html=True)
        st.button("🕐 Use Current Time", on_click=lambda: _set_now("context"), key="context_now", use_container_width=True)
    
    # Parse time or use current
    try:
        query_time = datetime.strptime(query_time_str, "%H:%M").time()
        query_datetime = datetime.combine(query_date, query_time)
    except:
        query_datetime = datetime.combine(query_date, time(20, 0))
    
    # Status display
    st.markdown(f"""
    <div class="status-info">
        <strong>🕐 Query Timestamp:</strong> {query_datetime.strftime('%Y-%m-%d %H:%M')} - System will search for patient states at this exact time point
    </div>
    """, unsafe_allow_html=True)
    
    # Query type selection
    st.markdown("#### 🎯 Query Configuration")
    col_query_type, col_range_config = st.columns([1, 2])
    
    with col_query_type:
        query_type = st.radio(
            "📊 Query Type",
            ["🕐 Point-in-Time Snapshot", "📅 Time Range Analysis"],
            help="Choose between a single time point or a time range analysis"
        )
    
    with col_range_config:
        if query_type == "📅 Time Range Analysis":
            st.markdown("**Time Range Configuration:**")
            col_start, col_end = st.columns(2)
            
            with col_start:
                start_date = st.date_input("Start Date", value=date(2025, 6, 1), key="range_start_date")
                start_time_str = st.text_input("Start Time (HH:MM)", value="00:00", key="range_start_time")
            
            with col_end:
                end_date = st.date_input("End Date", value=date(2025, 6, 13), key="range_end_date")
                end_time_str = st.text_input("End Time (HH:MM)", value="23:59", key="range_end_time")
    
    # Enhanced query criteria selection
    st.markdown("#### 🎯 Clinical Criteria Selection")
    context_columns = ['Hemoglobin_State', 'Hematological_State', 'Systemic_Toxicity', 'Therapy_Status', 'Gender']
    
    col_context, col_value = st.columns([1, 1])
    with col_context:
        context = st.selectbox("🔬 Medical Context", context_columns, key="context_select", help="Choose the clinical parameter to query")
    
    # Get current states for all patients at the specified time
    all_patients = db.demographics_df['Patient_ID'].tolist()
    states_at_time = {}
    for patient in all_patients:
        try:
            patient_states = db.get_patient_states(patient, query_datetime)
            states_at_time[patient] = patient_states.get(context)
        except:
            states_at_time[patient] = None
    
    # Get all possible values for the selected context (not just what's available at this time)
    def get_all_possible_values(context_type):
        if context_type == 'Hemoglobin_State':
            return ['Severe Anemia', 'Moderate Anemia', 'Mild Anemia', 'Normal Hemoglobin', 'Polycytemia']
        elif context_type == 'Hematological_State':
            return ['Pancytopenia', 'Anemia', 'Suspected Leukemia', 'Leukopenia', 'Normal', 'Leukemoid reaction', 'Polycytemia', 'Suspected Polycytemia Vera']
        elif context_type == 'Systemic_Toxicity':
            return ['Grade 1', 'Grade 2', 'Grade 3', 'Grade 4']
        elif context_type == 'Therapy_Status':
            return ['CCTG522', 'Other']
        elif context_type == 'Gender':
            return ['Male', 'Female']
        else:
            return []
    
    options = get_all_possible_values(context)
    
    with col_value:
        if not options:
            st.warning(f"No predefined values available for {context}")
            target_value = None
        else:
            target_value = st.selectbox("🎯 Target Value", options, key="target_value", help="Choose the specific value to search for")
    
    # Enhanced query execution button
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
    with col_btn2:
        query_button = st.button("🔍 Execute Clinical Query", type="primary", use_container_width=True)
    
    if query_button and target_value:
        matching_patients = []
        patient_time_matches = {}  # Initialize for both query types
        
        if query_type == "🕐 Point-in-Time Snapshot":
            # Find patients matching the criteria at the specified time
            for patient in all_patients:
                try:
                    patient_state_value = states_at_time.get(patient)
                    if str(patient_state_value) == target_value:
                        matching_patients.append(patient)
                except:
                    continue
            
            query_description = f"at {query_datetime.strftime('%Y-%m-%d %H:%M')}"
        
        else:  # Time Range Analysis
            # Show spinner for long-running time range analysis
            with st.spinner("This may take a while..."):
                # Parse time range
                try:
                    start_time = datetime.strptime(start_time_str, "%H:%M").time() if start_time_str else time(0, 0)
                    end_time = datetime.strptime(end_time_str, "%H:%M").time() if end_time_str else time(23, 59)
                    start_datetime = datetime.combine(start_date, start_time)
                    end_datetime = datetime.combine(end_date, end_time)
                except:
                    start_datetime = datetime.combine(start_date, time(0, 0))
                    end_datetime = datetime.combine(end_date, time(23, 59))
                
                # Find patients matching criteria during the time range
                # Sample time points within the range (every 6 hours for efficiency)
                current_time = start_datetime
                time_delta = timedelta(hours=6)
                
                while current_time <= end_datetime:
                    for patient in all_patients:
                        try:
                            # Get patient ID for database query
                            patient_id = get_patient_id_from_name(patient)
                            patient_states = db.get_patient_states(patient_id, current_time)
                            patient_state_value = patient_states.get(context)
                            
                            if str(patient_state_value) == target_value:
                                if patient not in matching_patients:
                                    matching_patients.append(patient)
                                    patient_time_matches[patient] = []
                                patient_time_matches[patient].append(current_time)
                        except Exception as e:
                            # Debug: you can uncomment this to see what's happening
                            # st.write(f"Error for {patient} at {current_time}: {e}")
                            continue
                    
                    current_time += time_delta
                
                query_description = f"during {start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%Y-%m-%d %H:%M')}"
        
        if matching_patients:
            # Enhanced results header
            st.markdown(f"""
            <div class="status-success">
                <strong>✅ Query Results:</strong> Found {len(matching_patients)} patients matching criteria: 
                <code>{context} = '{target_value}'</code> {query_description}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("#### 👥 Matching Patients")
            
            # Show detailed information for each patient
            for i, patient_id in enumerate(matching_patients, 1):
                # Get patient name for display
                patient_name = "Unknown"
                if 'Patient_Name' in db.demographics_df.columns:
                    name_match = db.demographics_df[db.demographics_df['Patient_ID'] == patient_id]
                    if not name_match.empty:
                        patient_name = name_match.iloc[0]['Patient_Name']
                
                # Modern patient card
                st.markdown(f"""
                <div class="metric-card">
                    <h4 style="color: #495057; margin-bottom: 1rem; display: flex; align-items: center;">
                        <span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; 
                             padding: 0.2rem 0.6rem; border-radius: 50%; margin-right: 0.8rem; font-size: 0.9rem;">
                            {i}
                        </span>
                        📋 {patient_name}
                    </h4>
                </div>
                """, unsafe_allow_html=True)
                
                with st.container():
                    col1, col2 = st.columns([2, 3])
                    
                    with col1:
                        st.markdown("**Demographics:**")
                        demographics = db.get_patient_demographics(patient_id)
                        st.text(f"Gender: {demographics.get('Gender', 'Unknown')}")
                        st.text(f"Age: {demographics.get('Age', 'Unknown')}")
                        
                        st.markdown(f"**Measurements at {query_datetime.strftime('%Y-%m-%d %H:%M')}:**")
                        states = db.get_patient_states(patient_id, query_datetime)
                        if states.get('Hemoglobin_Level'):
                            st.text(f"Hemoglobin: {states['Hemoglobin_Level']} g/dL")
                        if states.get('WBC_Level'):
                            st.text(f"WBC: {states['WBC_Level']:,.0f} cells/μL")
                        if states.get('Temperature'):
                            st.text(f"Temperature: {states['Temperature']}°C")
                            
                        st.markdown("**Clinical Status:**")
                        # Show therapy status - if not CCTG522, show "Other"
                        therapy_status = states.get('Therapy_Status')
                        if therapy_status == 'CCTG522':
                            st.text(f"Therapy: {therapy_status}")
                        elif therapy_status:
                            st.text(f"Therapy: Other")
                        else:
                            st.text("Therapy: Other")
                            
                        if states.get('Chills'):
                            st.text(f"Chills: {states['Chills']}")
                        if states.get('Skin_Appearance'):
                            st.text(f"Skin: {states['Skin_Appearance']}")
                        if states.get('Allergic_Reaction'):
                            st.text(f"Allergic: {states['Allergic_Reaction']}")
                    
                    with col2:
                        st.markdown("**Medical States:**")
                        if query_type == "🕐 Point-in-Time Snapshot":
                            # Show states at the specific time
                            if states.get('Hemoglobin_State'):
                                st.text(f"🩸 Hemoglobin State: {states['Hemoglobin_State']}")
                            if states.get('Hematological_State'):
                                st.text(f"🔬 Hematological State: {states['Hematological_State']}")
                            if states.get('Systemic_Toxicity'):
                                st.text(f"⚠️ Systemic Toxicity: {states['Systemic_Toxicity']}")
                            else:
                                st.text(f"⚠️ Systemic Toxicity: None (not on CCTG522)")
                            
                            st.markdown("**Treatment Recommendation:**")
                            recommendation = db.get_treatment_recommendation(patient_id, query_datetime)
                            st.text_area("Recommendation", value=recommendation, height=100, key=f"rec_{patient_id}", label_visibility="collapsed")
                        else:
                            # Show time range analysis
                            st.markdown(f"**Time Points Matched: {len(patient_time_matches.get(patient_id, []))}**")
                            if patient_id in patient_time_matches:
                                first_match = min(patient_time_matches[patient_id])
                                last_match = max(patient_time_matches[patient_id])
                                st.text(f"First match: {first_match.strftime('%Y-%m-%d %H:%M')}")
                                st.text(f"Last match: {last_match.strftime('%Y-%m-%d %H:%M')}")
                                
                                # Show state at the most recent match
                                recent_states = db.get_patient_states(patient_id, last_match)
                                if recent_states.get('Hemoglobin_State'):
                                    st.text(f"🩸 Recent Hemoglobin State: {recent_states['Hemoglobin_State']}")
                                if recent_states.get('Hematological_State'):
                                    st.text(f"🔬 Recent Hematological State: {recent_states['Hematological_State']}")
                                if recent_states.get('Systemic_Toxicity'):
                                    st.text(f"⚠️ Recent Systemic Toxicity: {recent_states['Systemic_Toxicity']}")
                        
                        # Show latest measurements with timestamps (as of today)
                        st.markdown("**Latest Measurements (as of today):**")
                        current_time = datetime.now()
                        hgb_val, hgb_unit = db.get_latest_lab_value(patient_id, '30313-1', current_time)
                        wbc_val, wbc_unit = db.get_latest_lab_value(patient_id, '26464-8', current_time)
                        temp_val, temp_unit = db.get_latest_lab_value(patient_id, '39106-0', current_time)
                        
                        if hgb_val:
                            st.text(f"Latest Hemoglobin: {hgb_val} {hgb_unit}")
                        if wbc_val:
                            st.text(f"Latest WBC: {wbc_val:,.0f} {wbc_unit}")
                        if temp_val:
                            st.text(f"Latest Temperature: {temp_val} {temp_unit}")
        else:
            st.markdown(f"""
            <div class="status-info">
                <strong>ℹ️ No Results:</strong> No patients found matching criteria: 
                <code>{context} = '{target_value}'</code> {query_description}
                <br><small>Try adjusting your search criteria or selecting a different time point/range.</small>
            </div>
            """, unsafe_allow_html=True)

# Knowledge Base Editor Tab
with tab_kb_editor:
    from kb_editor import render_kb_editor
    render_kb_editor()

# Treatment Board Tab
with tab_recommendations:
    st.markdown("""
    <div class="section-divider"></div>
    """, unsafe_allow_html=True)
    
    # Professional header section
    st.markdown("""
    <div class="metric-card">
        <h2 style="color: #495057; margin-bottom: 0.5rem;">💊 Recommendation Board</h2>
        <p style="color: #6c757d; margin: 0;">Comprehensive treatment overview organized by priority and patient status</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Time selection for recommendations board
    st.markdown("#### ⚙️ Board Time Configuration")
    rec_col1, rec_col2, rec_col3 = st.columns([2, 2, 1])
    
    with rec_col1:
        # Default to current date
        current_date = datetime.now().date()
        rec_date = st.date_input("📅 Recommendation Date", value=current_date, key="rec_date", help="Select the date for recommendations snapshot")
    
    with rec_col2:
        # Default to current time
        current_time = datetime.now().strftime("%H:%M")
        default_rec_time = st.session_state.get("rec_time", current_time)
        rec_time_str = st.text_input("🕐 Time (HH:MM)", value=default_rec_time, key="rec_time", placeholder="Enter time in 24-hour format")
    
    with rec_col3:
        st.markdown("<div style='height: 1.8em;'></div>", unsafe_allow_html=True)
        st.button("🕐 Use Current Time", on_click=lambda: _set_now("rec"), key="rec_now", use_container_width=True)
    
    # Parse time or use current
    try:
        rec_time = datetime.strptime(rec_time_str, "%H:%M").time()
        rec_datetime = datetime.combine(rec_date, rec_time)
    except:
        rec_datetime = datetime.combine(rec_date, time(20, 0))
    
    # Status display
    st.markdown(f"""
    <div class="status-info">
        <strong>🕐 Board Timestamp:</strong> {rec_datetime.strftime('%Y-%m-%d %H:%M')} - Showing treatment recommendations at this specific time point
    </div>
    """, unsafe_allow_html=True)
    
    # Generate Recommendations Button
    st.markdown("#### 🚀 Generate Treatment Recommendations")
    col_gen1, col_gen2, col_gen3 = st.columns([1, 2, 1])
    
    with col_gen2:
        generate_recs = st.button("🚀 Generate Recommendations for All Patients", 
                                type="primary", 
                                use_container_width=True,
                                help="Generate treatment recommendations for all patients at the specified time")
    
    # Auto-reset recommendations when date/time changes
    current_datetime_key = f"{rec_date}_{rec_time_str}"
    if 'last_rec_datetime' not in st.session_state:
        st.session_state['last_rec_datetime'] = current_datetime_key
        st.session_state['show_all_recommendations'] = True  # Show by default
    elif st.session_state['last_rec_datetime'] != current_datetime_key:
        st.session_state['last_rec_datetime'] = current_datetime_key
        st.session_state['show_all_recommendations'] = False  # Reset when date changes
    
    if generate_recs:
        st.session_state['show_all_recommendations'] = True
    
    if st.session_state.get('show_all_recommendations', False):
        
        # Get ALL patients, not just those with states at this time
        all_patient_names = patient_list()
        all_patients = [get_patient_id_from_name(name) for name in all_patient_names]
        
        # Generate recommendations for all patients
        all_recommendations = []
        for patient_id in all_patients:
            try:
                # Get patient demographics
                demographics = db.get_patient_demographics(patient_id)
                patient_name = demographics.get('Patient_Name', f'ID: {patient_id}')
                
                # Get patient states at the specified time
                states = db.get_patient_states(patient_id, rec_datetime)
                
                # Get treatment recommendation
                recommendation = db.get_treatment_recommendation(patient_id, rec_datetime)
                
                all_recommendations.append({
                    'Patient': patient_id,
                    'Patient_Name': patient_name,
                    'Hemoglobin-state': states.get('Hemoglobin_State', 'Unknown'),
                    'Hematological_State': states.get('Hematological_State', 'Unknown'),
                    'Systemic-Toxicity': states.get('Systemic_Toxicity', 'None'),
                    'Recommendation': recommendation,
                    'Demographics': demographics,
                    'States': states
                })
            except Exception as e:
                # Handle any errors gracefully
                all_recommendations.append({
                    'Patient': patient_id,
                    'Patient_Name': f'ID: {patient_id}',
                    'Hemoglobin-state': 'Error',
                    'Hematological_State': 'Error',
                    'Systemic-Toxicity': 'Error',
                    'Recommendation': f'Error generating recommendation: {str(e)}',
                    'Demographics': {},
                    'States': {}
                })
        
        # Convert to DataFrame for easier processing
        df_board_states = pd.DataFrame(all_recommendations)
        
        st.markdown(f"#### 📋 Treatment Recommendations for All {len(all_patients)} Patients")
    else:
        # Show instruction to generate recommendations
        st.markdown("""
        <div class="status-info">
            <strong>💡 Ready to Generate:</strong> Click the "Generate Recommendations" button above to analyze all patients and display comprehensive treatment recommendations.
            <br><small>This will process all patients in the database and show their current status and treatment protocols.</small>
        </div>
        """, unsafe_allow_html=True)
        df_board_states = pd.DataFrame()  # Empty dataframe
    
    if not df_board_states.empty:        
        # Priority sorting based on treatment recommendations
        def sort_priority_board(row):
            recommendation = str(row.get('Recommendation', ''))
            
            # Check if patient has an actual treatment protocol (not just monitoring)
            has_treatment = (
                recommendation and 
                'No treatment recommendation' not in recommendation and
                'Insufficient data' not in recommendation and
                'No specific treatment' not in recommendation and
                'patient not on CCTG522' not in recommendation and
                '• ' in recommendation  # Actual treatment protocols start with bullet points
            )
            
            if has_treatment:
                # Patients with treatment protocols - Yellow priority
                return (0, row['Patient_Name'])  # Yellow - Active Treatment
            else:
                # Patients without specific treatment protocols - monitoring only
                return (1, row['Patient_Name'])  # Green - Continue Monitoring
        
        df_board_states['priority'] = df_board_states.apply(sort_priority_board, axis=1)
        sorted_board = df_board_states.sort_values('priority')
        
        # Group patients by priority for better organization
        treatment_patients = sorted_board[sorted_board['priority'].apply(lambda x: x[0] == 0)]
        monitoring_patients = sorted_board[sorted_board['priority'].apply(lambda x: x[0] == 1)]
        
        # 🟡 PATIENTS WITH TREATMENT PROTOCOLS (Yellow)
        if not treatment_patients.empty:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #ffc107 0%, #e0a800 100%); 
                        color: #212529; padding: 1.5rem; border-radius: 12px; margin: 1.5rem 0;">
                <h3 style="margin: 0; color: #212529; font-size: 1.4rem;">💊 Active Treatment Protocols</h3>
                <p style="margin: 0.5rem 0 0 0; opacity: 0.8; font-size: 1rem;">Patients requiring specific medical interventions based on treatment rules</p>
            </div>
            """, unsafe_allow_html=True)
            
            for _, patient_row in treatment_patients.iterrows():
                demographics = patient_row.get('Demographics', {})
                patient_id = patient_row.get('Patient')
                patient_name = patient_row.get('Patient_Name', f"ID: {patient_id}")
                recommendation = patient_row.get('Recommendation', 'N/A')
                states = patient_row.get('States', {})
                
                # Create expandable patient card
                with st.expander(f"💊 {patient_name}", expanded=False):
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        st.markdown("**👤 Patient Information**")
                        st.write(f"**Gender:** {demographics.get('Gender', 'Unknown')}")
                        st.write(f"**Age:** {demographics.get('Age', 'Unknown')}")
                        
                        st.markdown("**🔬 Current Lab Values**")
                        if states.get('Hemoglobin_Level'):
                            st.write(f"**Hemoglobin:** {states['Hemoglobin_Level']} g/dL")
                        if states.get('WBC_Level'):
                            st.write(f"**WBC:** {states['WBC_Level']:,.0f} cells/μL")
                        if states.get('Temperature'):
                            st.write(f"**Temperature:** {states['Temperature']}°C")
                    
                    with col2:
                        st.markdown("**📊 Clinical States**")
                        if states.get('Hemoglobin_State'):
                            st.write(f"**Hemoglobin State:** {states['Hemoglobin_State']}")
                        if states.get('Hematological_State'):
                            st.write(f"**Hematological State:** {states['Hematological_State']}")
                        if states.get('Systemic_Toxicity'):
                            st.write(f"**Systemic Toxicity:** {states['Systemic_Toxicity']}")
                        if states.get('Therapy_Status'):
                            st.write(f"**Therapy Status:** {states['Therapy_Status']}")
                    
                    # Treatment Protocol Section
                    st.markdown("---")
                    st.markdown("**🏥 Treatment Protocol**")
                    if recommendation and "No treatment recommendation" not in recommendation:
                        st.success("✅ Active treatment protocol assigned")
                        st.text_area("Treatment Details:", value=recommendation.replace('\\n', '\n'), height=120, key=f"treatment_{patient_row['Patient']}")
                    else:
                        st.warning(f"⚠️ {recommendation}")
        

        
        # 🟢 MONITORING PATIENTS (Green)
        if not monitoring_patients.empty:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%); 
                        color: white; padding: 1.5rem; border-radius: 12px; margin: 1.5rem 0;">
                <h3 style="margin: 0; color: white; font-size: 1.4rem;">📊 Standard Monitoring</h3>
                <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 1rem;">Patients requiring routine observation without specific treatment protocols</p>
            </div>
            """, unsafe_allow_html=True)
            
            for _, patient_row in monitoring_patients.iterrows():
                demographics = patient_row.get('Demographics', {})
                patient_id = patient_row.get('Patient')
                patient_name = patient_row.get('Patient_Name', f"ID: {patient_id}")
                recommendation = patient_row.get('Recommendation', 'N/A')
                states = patient_row.get('States', {})
                
                # Create expandable patient card for monitoring patients
                with st.expander(f"📊 {patient_name}", expanded=False):
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        st.markdown("**👤 Patient Information**")
                        st.write(f"**Gender:** {demographics.get('Gender', 'Unknown')}")
                        st.write(f"**Age:** {demographics.get('Age', 'Unknown')}")
                        
                        st.markdown("**🔬 Current Lab Values**")
                        if states.get('Hemoglobin_Level'):
                            st.write(f"**Hemoglobin:** {states['Hemoglobin_Level']} g/dL")
                        if states.get('WBC_Level'):
                            st.write(f"**WBC:** {states['WBC_Level']:,.0f} cells/μL")
                        if states.get('Temperature'):
                            st.write(f"**Temperature:** {states['Temperature']}°C")
                    
                    with col2:
                        st.markdown("**📊 Clinical States**")
                        if states.get('Hemoglobin_State'):
                            st.write(f"**Hemoglobin State:** {states['Hemoglobin_State']}")
                        if states.get('Hematological_State'):
                            st.write(f"**Hematological State:** {states['Hematological_State']}")
                        if states.get('Systemic_Toxicity'):
                            st.write(f"**Systemic Toxicity:** {states['Systemic_Toxicity']}")
                        else:
                            st.write("**Systemic Toxicity:** None")
                        if states.get('Therapy_Status'):
                            st.write(f"**Therapy Status:** {states['Therapy_Status']}")
                    
                    # Monitoring Status Section
                    st.markdown("---")
                    st.markdown("**📋 Monitoring Status**")
                    st.info("✅ Continue standard monitoring - No immediate treatment required")
                    if recommendation:
                        st.write(f"**Note:** {recommendation}")

    # else:
    #     st.markdown("""
    #     <div class="status-info">
    #         <strong>ℹ️ No Patient Data:</strong> No patient states found for the selected date and time.
    #         <br><small>Try selecting a different date or time, or check if data exists for this period.</small>
    #     </div>
    #     """, unsafe_allow_html=True)

with tab_intervals:
    st.markdown("""
    <div class="section-divider"></div>
    """, unsafe_allow_html=True)
    
    # Professional header section
    st.markdown("""
    <div class="metric-card">
        <h2 style="color: #495057; margin-bottom: 0.5rem;">📊 State Analysis & Intervals</h2>
        <p style="color: #6c757d; margin: 0;">Analyze temporal patterns and find time intervals when patients were in specific medical states</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("#### 🎯 Analysis Parameters")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        patient_interval = st.selectbox("👤 Select Patient", patient_list(), index=None, key="patient_interval", 
                                      help="Choose the patient for temporal analysis")
    
    with col2:
        state_type = st.selectbox("🔬 Clinical State Type", 
                                 ["Hemoglobin_State", "Hematological_State", "Systemic_Toxicity"], 
                                 key="state_type_interval",
                                 help="Select the type of clinical state to analyze")
    
    # State value selection based on type
    if state_type == "Hemoglobin_State":
        target_state = st.selectbox("🎯 Target Hemoglobin State", [
            "Severe Anemia", "Moderate Anemia", "Mild Anemia", 
            "Normal Hemoglobin", "Polycytemia"
        ], key="target_state_interval", help="Select the specific hemoglobin state to track")
    elif state_type == "Hematological_State":
        target_state = st.selectbox("🎯 Target Hematological State", [
            "Pancytopenia", "Anemia", "Suspected Leukemia",
            "Leukopenia", "Normal", "Leukemoid reaction", "Suspected Polycytemia Vera"
        ], key="target_state_interval", help="Select the specific hematological condition to track")
    else:  # Systemic_Toxicity
        target_state = st.selectbox("🎯 Target Toxicity Grade", [
            "GRADE 1", "GRADE 2", "GRADE 3", "GRADE 4"
        ], key="target_state_interval", help="Select the toxicity grade to analyze")

    # Enhanced analysis button
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
    with col_btn2:
        analyze_button = st.button("🔍 Analyze State Intervals", type="primary", use_container_width=True)

    if analyze_button:
        if patient_interval and state_type and target_state:
            patient_id = get_patient_id_from_name(patient_interval)
            intervals = db.get_state_intervals(patient_id, state_type, target_state)
            if intervals:
                # Enhanced results display
                st.markdown(f"""
                <div class="status-success">
                    <strong>✅ Analysis Complete:</strong> Found {len(intervals)} time intervals where {patient_interval} was in state 
                    <code>{target_state}</code>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("#### 📊 Temporal Analysis Results")
                
                for i, interval in enumerate(intervals, 1):
                    start = interval['start']
                    end = interval['end']
                    duration = end - start
                    
                    # Modern interval card with enhanced visibility
                    st.markdown(f"""
                    <div class="metric-card">
                        <h4 style="color: #495057; margin-bottom: 1.5rem; display: flex; align-items: center;">
                            <span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; 
                                 padding: 0.3rem 0.8rem; border-radius: 50%; margin-right: 1rem; font-size: 1rem;">
                                {i}
                            </span>
                            📅 Interval {i}
                        </h4>
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2rem; margin-top: 1.5rem;">
                            <div style="text-align: center; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
                                <strong style="color: #28a745; font-size: 1.1rem;">🕐 Start Time</strong><br/>
                                <code style="font-size: 1.2rem; font-weight: bold; color: #495057;">{start.strftime('%Y-%m-%d %H:%M')}</code>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
                                <strong style="color: #dc3545; font-size: 1.1rem;">🕐 End Time</strong><br/>
                                <code style="font-size: 1.2rem; font-weight: bold; color: #495057;">{end.strftime('%Y-%m-%d %H:%M')}</code>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
                                <strong style="color: #fd7e14; font-size: 1.1rem;">⏱️ Duration</strong><br/>
                                <code style="font-size: 1.2rem; font-weight: bold; color: #495057;">{duration}</code>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="status-info">
                    <strong>ℹ️ No Intervals Found:</strong> Patient {patient_interval} was never in state 
                    <code>{target_state}</code> during the recorded time period.
                    <br><small>Try selecting a different state or patient.</small>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.warning("Please select a patient, state type, and target state.")

# ═════════ HISTORY ═════════
with tab_hist:
    st.markdown("""
    <div class="section-divider"></div>
    """, unsafe_allow_html=True)
    
    # Professional header section
    st.markdown("""
    <div class="metric-card">
        <h2 style="color: #495057; margin-bottom: 0.5rem;">📋 Patient History Analytics</h2>
        <p style="color: #6c757d; margin: 0;">Query historical measurements with advanced bi-temporal support and trend analysis</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("#### 🎯 Query Parameters")
    c1, c2, col_hours = st.columns([2, 2, 3])

    # Enhanced patient & measurement selection
    with c1:
        st.markdown("**👤 Patient & Measurement:**")
        patient = st.selectbox("Patient", patient_list(), index=None,
                               placeholder="Start typing patient name…", help="Select patient for historical analysis")
        code = st.selectbox("📊 LOINC Code / Component",
                            loinc_choices_for(patient), index=None, help="Choose the measurement type to analyze")

    with c2:
        st.markdown("**📅 Date Range:**")
        f_date = st.date_input("From Date", date(2025, 4, 17), help="Start date for historical query")
        t_date = st.date_input("To Date", date(2025, 4, 25), help="End date for historical query")
        
        st.markdown("**🕐 Temporal Query (Optional):**")
        query_date = st.date_input("As of Date", value=None, help="Query data as it appeared on this date")
    
    with col_hours:
        st.markdown("**⏰ Time Parameters:**")
        query_time_str = st.text_input("As of Time (HH:MM)", placeholder="00:00", key="query_time", 
                                     help="Time for temporal query (optional)")
        
        st.markdown("**🕐 Time Range (Optional):**")

        # hour-range widgets side-by-side
        h1, h2 = st.columns(2)
        from_hhmm = h1.text_input("From HH:MM", placeholder="00:00", key="hh_from", help="Start time of day")
        to_hhmm = h2.text_input("To HH:MM", placeholder="23:59", key="hh_to", help="End time of day")

    # Enhanced query button
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
    with col_btn2:
        history_button = st.button("📊 Run History Analysis", type="primary", use_container_width=True)

    if history_button and patient and code:
        try:
            patient_id = get_patient_id_from_name(patient)
            
            # validate / default hour-range
            t_min = parse_hhmm(from_hhmm) or time(0, 0)
            t_max = parse_hhmm(to_hhmm) or time(23, 59)

            # build full datetimes
            start_dt = datetime.combine(f_date, t_min)
            end_dt = datetime.combine(t_date, t_max)

            query_dt = None
            if query_date:
                query_t = parse_hhmm(query_time_str) or time(0, 0)
                query_dt = datetime.combine(query_date, query_t)

            res = db.history(
                patient_id, code,
                start_dt,
                end_dt,
                hh=None,
                query_time=query_dt
            )

            # Enhanced results display
            st.markdown(f"""
            <div class="status-success">
                <strong>📊 Analysis Complete:</strong> Found {len(res)} measurements for patient {patient}
                <br><small>Measurement type: {code} | Date range: {f_date} to {t_date}</small>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("#### 📊 Historical Data Table")
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

        except ValueError as e:
            st.warning(str(e))

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

    st.subheader("✏️ Update Measurement")
    st.markdown("*Update existing measurements with bi-temporal versioning*")

    # two‐column layout
    c1, c2 = st.columns(2)

    # Column 1: patient, code, and new value
    patient_u = c1.selectbox(
        "Patient", patient_list(), key="u_p"
    )
    code_u = c1.selectbox(
        "LOINC code / component",
        loinc_choices_for(patient_u),
        key="u_c",
        disabled=not patient_u
    )
    new_val = c1.text_input(
        "New value", key="u_v"
    )

    # Column 2: date picker and time+now button in one row
    when_date = c2.date_input("Measurement date", key="upd_date")

    col_time, col_now = c2.columns([3, 1])
    when_time_str = col_time.text_input("Measurement time (HH:MM)", placeholder="HH:MM", key="upd_time_str")

    with col_now:
        st.markdown("<div style='height: 1.8em;'></div>", unsafe_allow_html=True)  # vertical spacer
        st.button("Now", on_click=lambda: _set_now("upd"), key="update_now_btn")
    
    c2.markdown("---")
    tr_date = c2.date_input("Transaction date (Optional)", value=None, key="tr_date")
    tr_time_str = c2.text_input("Transaction time (HH:MM, Optional)", placeholder="HH:MM", key="tr_time_str")


    # Use the global _set_now function


    if st.button("✏️ Apply Update") and patient_u and code_u and new_val:
        try:
            patient_id = get_patient_id_from_name(patient_u)
            
            # get measurement valid-time
            when_time = parse_hhmm(when_time_str) or time(0, 0)
            valid_dt = datetime.combine(when_date, when_time)

            tr_dt = None
            if tr_date:
                tr_time = parse_hhmm(tr_time_str) or time(0, 0)
                tr_dt = datetime.combine(tr_date, tr_time)

            res = db.update(
                patient_id, code_u, valid_dt, new_val,
                transaction_time=tr_dt
            )
            st.dataframe(res, use_container_width=True)
            st.success("✅ Measurement updated successfully")
            st.rerun()

        except ValueError as e:
            st.warning(str(e))

# ═════════ DELETE ═════════
with tab_del:
    st.subheader("🗑️ Delete Measurement")
    st.markdown("*Mark measurements as deleted with proper bi-temporal handling*")

    # ── Two‐column layout ─────────────────────────────────────────
    c1, c2 = st.columns(2)

    # Column 1: patient & LOINC selector
    patient_d = c1.selectbox(
        "Patient", patient_list(), key="d_p"
    )
    code_d = c1.selectbox(
        "LOINC code / component",
        loinc_choices_for(patient_d),
        key="d_c",
        disabled=not patient_d
    )

    # Column 2: date and time+now
    day_date = c2.date_input("Measurement date", key="d_date")

    col_time_d, col_now_d = c2.columns([3, 1])
    day_time_str = col_time_d.text_input("Measurement time (HH:MM)", placeholder="HH:MM", key="d_time_str")

    with col_now_d:
        st.markdown("<div style='height: 1.8em;'></div>", unsafe_allow_html=True)
        st.button("Now", on_click=lambda: _set_now("d"), key="delete_now_btn")

    # ── Action button ─────────────────────────────────────────
    if st.button("🗑️ Delete Measurement", key="delete_action_btn"):
        try:
            patient_id = get_patient_id_from_name(patient_d)
            
            hh = None
            if st.session_state.d_time_str:
                hh = parse_hhmm(st.session_state.d_time_str)
            deleted = db.delete(
                patient_id,
                code_d,
                st.session_state.d_date,
                hh
            )
            st.success("✅ Measurement deleted successfully")
            st.dataframe(deleted)
        except Exception as e:
            st.error(str(e))






# with tab_del:
#     st.subheader("Delete measurement")
#     patient_d = st.selectbox("Patient", patient_list(), index=None, key="d_p",
#                              placeholder="Start typing…")
#
#     code_d = st.selectbox(
#         "Code / component",
#         loinc_choices_for(patient_d),
#         index=None, key="d_c",
#         placeholder="Pick a patient first…" if not patient_d else "Start typing…",
#         disabled=patient_d is None
#     )
#
#     day_d = st.text_input("Date (YYYY-MM-DD or today)", key="d_day")
#     hh_opt = st.selectbox(
#         "Hour (optional)", ["—"] + [f"{h:02}:00" for h in range(24)], key="d_hh"
#     )
#
#     if st.button("Delete"):
#         try:
#             day_obj = cdss_loinc.parse_dt(day_d, date_only=True)
#             hh_obj = None if hh_opt == "—" else time.fromisoformat(hh_opt)
#             st.dataframe(db.delete(patient_d, code_d, day_obj, hh_obj))
#             st.success("Deleted")
#         except Exception as e:
#             st.error(str(e))



# # ═════════ STATUS ═════════
# with tab_stat:
#     st.subheader("Current status (latest value per LOINC)")
#     st.dataframe(db.status(), use_container_width=True)
