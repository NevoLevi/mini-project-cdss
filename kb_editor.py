from datetime import timedelta

import streamlit as st
import json
from pathlib import Path

# Constants
KB_PATH = "knowledge_base.json"


#

def get_validity_for(loinc_code: str):
    """Return {'before_good': timedelta, 'after_good': timedelta} for a LOINC code."""
    with open(KB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    vp = data.get("validity_periods", {})
    raw = vp.get(loinc_code)

    if not raw:
        # default fallback: 4h before, 8h after
        return {
            "before_good": timedelta(hours=4),
            "after_good": timedelta(hours=8)
        }

    return {
        "before_good": parse_duration(raw["before_good"]),
        "after_good": parse_duration(raw["after_good"])
    }

def parse_duration(s: str) -> timedelta:
    """Convert 'X days, HH:MM:SS' or 'HH:MM:SS' to timedelta."""
    try:
        if "days" in s:
            days = int(str(s).split(' ')[0])
            return timedelta(days=days)
        else:
            days = 0
            time_part = s
            h, m, sec = map(int, time_part.split(":"))
            return timedelta(days=days, hours=h, minutes=m, seconds=sec)

    except:
        return timedelta(days=3)


def get_hemoglobin_state(hgb_level: float, gender: str):
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    gender = gender.lower()
    table = kb["classification_tables"]["hemoglobin_state"]

    try:
        rules = table["rules"][gender]["ranges"]
    except KeyError:
        raise ValueError(f"No hemoglobin rules defined for gender: {gender}")

    for rule in rules:
        if rule["min"] <= hgb_level < rule["max"]:
            return rule["state"]

    return None  # No matching range found


def partition_index(value: float, bins: list[str]):
    for i, rng in enumerate(bins):
        if "+" in rng:
            min_val = float(rng.replace("+", ""))
            if value >= min_val:
                return i
        else:
            min_val, max_val = map(float, rng.split("-"))
            if min_val <= value < max_val:
                return i
    return None


def get_hematological_state(hgb: float, wbc: float, gender: str, kb: dict = None):
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    gender = gender.lower()
    table = kb["classification_tables"]["hematological_state"]

    try:
        rules = table["rules"][gender]
        hgb_bins = rules["hgb_partitions"]
        wbc_bins = rules["wbc_partitions"]
        matrix = rules["matrix"]
    except KeyError:
        raise ValueError(f"No hematological rules defined for gender: {gender}")

    # Determine hgb row
    hgb_idx = partition_index(hgb, hgb_bins)
    wbc_idx = partition_index(wbc, wbc_bins)

    if hgb_idx is None or wbc_idx is None:
        return None

    return matrix[hgb_idx][wbc_idx]




def get_systemic_toxicity(states: dict):
    """Calculate systemic toxicity using 4:1_MAXIMAL_OR rule from the KB."""
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    sys_tox = kb["classification_tables"]["systemic_toxicity"]

    # Only apply rule if the condition matches
    if states.get("Therapy_Status") != "CCTG522":
        return None

    def parse_grade(grade_str) -> int:
        """Convert 'GRADE I'...'GRADE IV' (Roman numerals) to integers."""
        roman_map = {
            "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
            "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10
        }

        if not grade_str or not isinstance(grade_str, str):
            return 0

        parts = grade_str.strip().upper().split()
        if len(parts) == 2 and parts[0] == "GRADE":
            return roman_map.get(parts[1], 0)

        return 0


    rules = sys_tox["rules"]

    # Mapping: KB input → state key
    field_aliases = {
        "Fever": "Temperature",
        "Chills": "Chills",
        "Skin-look": "Skin_Appearance",
        "Allergic-state": "Allergic_Reaction"
    }

    grades = []

    for kb_input in sys_tox["inputs"]:
        state_key = field_aliases.get(kb_input)
        if not state_key:
            continue

        value = states.get(state_key)
        if value is None:
            continue

        field_rules = rules.get(kb_input)
        if not field_rules:
            continue

        for rule in field_rules:
            if "range" in rule:
                try:
                    v = float(value)
                    if rule["range"][0] <= v < rule["range"][1]:
                        grades.append(parse_grade(rule["grade"]))
                        break
                except:
                    continue
            elif "value" in rule:
                if str(value).strip().lower() == str(rule["value"]).strip().lower() or str(rule["value"]).strip().lower() in str(value).strip().lower() :
                    grades.append(parse_grade(rule["grade"]))
                    break

    if not grades:
        return None

    return f"Grade {max(grades)}"


def build_treatment_rules_from_kb():
    """Convert JSON treatment rules to a structured dictionary with 4-tuple keys."""
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    raw = kb.get("treatments", {})
    rules = {}

    for gender_key, recs in raw.items():
        gender = gender_key.capitalize()  # "male" → "Male"
        for combo_key, treatment in recs.items():
            try:
                hemo, hema, grade = [s.strip() for s in combo_key.split("+")]
                rules[(gender, hemo, hema, grade)] = treatment.replace("•", "•")  # decode bullet if needed
            except ValueError:
                print(f"⚠️ Skipping invalid treatment key: {combo_key}")

    return rules


def load_kb():
    """Load knowledge base from JSON file."""
    try:
        with open(KB_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"Knowledge base file '{KB_PATH}' not found!")
        return {}
    except json.JSONDecodeError as e:
        st.error(f"Error parsing knowledge base JSON: {e}")
        return {}

def save_kb(kb_data):
    """Save knowledge base to JSON file."""
    try:
        with open(KB_PATH, 'w') as f:
            json.dump(kb_data, f, indent=2)
        return True
    except Exception as e:
        st.error(f"Error saving knowledge base: {e}")
        return False

def render_classification_tables_editor(kb_data):
    """Render the editor for classification tables with full CRUD."""
    st.markdown("### Classification Tables Editor")
    tables = list(kb_data.get("classification_tables", {}).keys())
    
    # Add/Delete Tables
    col_add, col_del = st.columns([3,1])
    with col_add:
        new_name = st.text_input("➕ New Table Name", key="new_ct_name")
        if st.button("Add Table") and new_name:
            if new_name in tables:
                st.warning("Table already exists.")
            else:
                kb_data["classification_tables"][new_name] = {"type":"1:1","inputs":[],"output":"","rules":{}}
                save_kb(kb_data)
                st.success(f"Table '{new_name}' added.")
                st.rerun()
    
    with col_del:
        if tables:
            del_table = st.selectbox("Delete Table", [""]+tables, key="del_ct_select")
            if st.button("Delete Table") and del_table:
                del kb_data["classification_tables"][del_table]
                save_kb(kb_data)
                st.success(f"Table '{del_table}' deleted.")
                st.rerun()
    
    if not tables:
        st.info("No classification tables to edit.")
        return
    
    selected = st.selectbox("Select Table to Edit", tables, key="ct_editor_select")
    table = kb_data["classification_tables"][selected]
    st.markdown(f"#### Editing `{selected}` ({table.get('type')})")
    
    # 1:1 table editor
    if table.get('type') == '1:1':
        inputs = table.get('inputs', [])
        output = table.get('output','')
        
        # Edit basic properties
        new_inputs = st.text_input("Input Variables (comma-separated)", value=','.join(inputs), key="ct1_inputs")
        new_output = st.text_input("Output Variable", value=output, key="ct1_output")
        
        rules = table.get('rules', {})
        genders = list(rules.keys()) if rules else ['male', 'female']
        
        # Add gender if missing
        if not rules:
            for gender in ['male', 'female']:
                rules[gender] = {'ranges': []}
        
        gender = st.selectbox("Gender", genders, key="ct1_gender")
        if gender not in rules:
            rules[gender] = {'ranges': []}
            
        rlist = rules[gender].get('ranges', [])
        
        # Initialize session state for deletions
        del_key = f"ct1_del_{selected}_{gender}"
        if del_key not in st.session_state:
            st.session_state[del_key] = set()
        
        new_ranges = []
        st.markdown(f"**{gender.title()} Ranges:**")
        
        for i, rule in enumerate(rlist):
            if i not in st.session_state[del_key]:
                c1, c2, c3, c4 = st.columns([2,2,3,1])
                mn = c1.number_input(f"Min {i+1}", value=float(rule.get('min', 0)), key=f"ct1_min_{selected}_{gender}_{i}")
                mx = c2.number_input(f"Max {i+1}", value=float(rule.get('max', 0)), key=f"ct1_max_{selected}_{gender}_{i}")
                stt = c3.text_input(f"State {i+1}", value=rule.get('state', ''), key=f"ct1_state_{selected}_{gender}_{i}")
                if c4.button("🗑️", key=f"ct1_delbtn_{selected}_{gender}_{i}"):
                    st.session_state[del_key].add(i)
                    st.rerun()
                else:
                    new_ranges.append({"min": mn, "max": mx, "state": stt})
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("➕ Add New Range", key=f"ct1_add_{selected}_{gender}"):
                # Persist new empty range directly to KB and reload
                rlist.append({"min": 0, "max": 0, "state": ""})
                table['rules'][gender]['ranges'] = rlist
                save_kb(kb_data)
                st.rerun()
        
        with col2:
            if st.button("💾 Update Table", key=f"ct1_upd_{selected}", type="primary"):
                table['inputs'] = [x.strip() for x in new_inputs.split(',') if x.strip()]
                table['output'] = new_output
                table['rules'][gender]['ranges'] = new_ranges
                save_kb(kb_data)
                st.success("Table updated.")
                st.rerun()
    
    # 2:1_AND matrix editor
    elif table.get('type') == '2:1_AND':
        rules = table.get('rules', {})
        genders = list(rules.keys()) if rules else ['male', 'female']
        
        # Add genders if missing
        if not rules:
            for gender in ['male', 'female']:
                rules[gender] = {
                    'hgb_partitions': [],
                    'wbc_partitions': [],
                    'matrix': []
                }
        
        gender = st.selectbox("Gender", genders, key="ct2_gender")
        if gender not in rules:
            rules[gender] = {'hgb_partitions': [], 'wbc_partitions': [], 'matrix': []}
        
        hgb_parts = rules[gender].get('hgb_partitions', [])
        wbc_parts = rules[gender].get('wbc_partitions', [])
        matrix = rules[gender].get('matrix', [])
        
        # Edit HGB partitions
        st.markdown("**HGB Partitions**")
        hgb_del_key = f"ct2_hgb_del_{selected}_{gender}"
        if hgb_del_key not in st.session_state:
            st.session_state[hgb_del_key] = set()
        
        new_hgb = []
        for i, p in enumerate(hgb_parts):
            if i not in st.session_state[hgb_del_key]:
                c1, c2 = st.columns([4, 1])
                val = c1.text_input(f"HGB Partition {i+1}", value=p, key=f"ct2_hgb_{selected}_{gender}_{i}")
                if c2.button("🗑️", key=f"ct2_hgb_delbtn_{selected}_{gender}_{i}"):
                    st.session_state[hgb_del_key].add(i)
                    st.rerun()
                else:
                    new_hgb.append(val)
        
        if st.button("➕ Add HGB Partition", key=f"ct2_hgb_add_{selected}_{gender}"):
            hgb_parts.append("")
            rules[gender]['hgb_partitions'] = hgb_parts
            save_kb(kb_data)
            st.rerun()
        
        # Edit WBC partitions
        st.markdown("**WBC Partitions**")
        wbc_del_key = f"ct2_wbc_del_{selected}_{gender}"
        if wbc_del_key not in st.session_state:
            st.session_state[wbc_del_key] = set()
        
        new_wbc = []
        for i, p in enumerate(wbc_parts):
            if i not in st.session_state[wbc_del_key]:
                c1, c2 = st.columns([4, 1])
                val = c1.text_input(f"WBC Partition {i+1}", value=p, key=f"ct2_wbc_{selected}_{gender}_{i}")
                if c2.button("🗑️", key=f"ct2_wbc_delbtn_{selected}_{gender}_{i}"):
                    st.session_state[wbc_del_key].add(i)
                    st.rerun()
                else:
                    new_wbc.append(val)
        
        if st.button("➕ Add WBC Partition", key=f"ct2_wbc_add_{selected}_{gender}"):
            wbc_parts.append("")
            rules[gender]['wbc_partitions'] = wbc_parts
            save_kb(kb_data)
            st.rerun()
        
        # Edit matrix
        st.markdown("**Matrix States**")
        if matrix:
            new_mat = []
            for i, row in enumerate(matrix):
                new_row = []
                cols = st.columns(len(row))
                for j, cell in enumerate(row):
                    val = cols[j].text_input(f"Cell ({i+1},{j+1})", value=cell, key=f"ct2_mat_{selected}_{gender}_{i}_{j}")
                    new_row.append(val)
                new_mat.append(new_row)
        else:
            st.info("Matrix is empty. Please add partitions first.")
            new_mat = matrix
        
        if st.button("💾 Update Matrix", key=f"ct2_mat_upd_{selected}_{gender}", type="primary"):
            rules[gender]['hgb_partitions'] = new_hgb
            rules[gender]['wbc_partitions'] = new_wbc
            rules[gender]['matrix'] = new_mat
            table['rules'] = rules
            save_kb(kb_data)
            st.success("Matrix updated.")
            st.rerun()
    
    # 4:1_MAXIMAL_OR editor
    elif table.get('type') == '4:1_MAXIMAL_OR':
        st.markdown("**Maximal OR Table Editor**")
        rules = table.get('rules', {})
        
        for param, rl in rules.items():
            with st.expander(f"Edit {param} Rules"):
                del_key = f"ct4_del_{selected}_{param}"
                if del_key not in st.session_state:
                    st.session_state[del_key] = set()
                
                new_rl = []
                for i, r in enumerate(rl):
                    if i not in st.session_state[del_key]:
                        cols = st.columns([2, 2, 2, 1])
                        
                        if 'range' in r:
                            mn = cols[0].number_input("Min", value=float(r['range'][0]), key=f"ct4_{param}_{i}_min")
                            mx = cols[1].number_input("Max", value=float(r['range'][1]), key=f"ct4_{param}_{i}_max")
                            gr = cols[2].text_input("Grade", value=r.get('grade', ''), key=f"ct4_{param}_{i}_grade")
                            if cols[3].button("🗑️", key=f"ct4_delbtn_{selected}_{param}_{i}"):
                                st.session_state[del_key].add(i)
                                st.rerun()
                            new_rl.append({'range': [mn, mx], 'grade': gr})
                        else:
                            val = cols[0].text_input("Value", value=r.get('value', ''), key=f"ct4_{param}_{i}_val")
                            gr = cols[1].text_input("Grade", value=r.get('grade', ''), key=f"ct4_{param}_{i}_grade")
                            if cols[2].button("🗑️", key=f"ct4_delbtn_{selected}_{param}_{i}"):
                                st.session_state[del_key].add(i)
                                st.rerun()
                            new_rl.append({'value': val, 'grade': gr})
                
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button(f"➕ Add {param} Rule", key=f"ct4_add_{selected}_{param}"):
                        # Insert placeholder directly into KB, then reload
                        if rl and 'range' in rl[0]:
                            rl.append({'range': [0, 0], 'grade': ''})
                        else:
                            rl.append({'value': '', 'grade': ''})
                        table['rules'][param] = rl
                        save_kb(kb_data)
                        st.rerun()
                
                with col2:
                    if st.button(f"💾 Update {param}", key=f"ct4_upd_{selected}_{param}", type="primary"):
                        table['rules'][param] = new_rl
                        save_kb(kb_data)
                        st.success(f"{param} rules updated.")
                        st.rerun()
    else:
        st.error("Unknown table type.")

def render_treatments_editor(kb_data):
    """Render the editor for treatment rules with full CRUD."""
    st.markdown("### Treatment Rules Editor")
    treatments = kb_data.get("treatments", {})
    
    # Gender selection
    genders = list(treatments.keys())
    if not genders:
        st.info("No treatment rules found. Please check your knowledge base.")
        return
    
    selected_gender = st.selectbox("Select Gender", genders, key="treatment_gender_select")
    gender_treatments = treatments[selected_gender]
    
    st.markdown(f"#### Editing Treatment Rules for: `{selected_gender.title()}`")
    
    # Display current rules with edit/delete options
    del_key = f"treatment_del_{selected_gender}"
    if del_key not in st.session_state:
        st.session_state[del_key] = set()
    
    st.markdown("**Current Treatment Rules:**")
    
    # Track updated rules
    updated_rules = {}
    
    for i, (condition, treatment) in enumerate(gender_treatments.items()):
        if i not in st.session_state[del_key]:
            with st.expander(f"Rule {i+1}: {condition[:50]}..." if len(condition) > 50 else f"Rule {i+1}: {condition}"):
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    # Edit condition
                    new_condition = st.text_input(
                        "Condition (Hemoglobin + Hematological + Toxicity)", 
                        value=condition, 
                        key=f"treatment_cond_{selected_gender}_{i}",
                        help="Format: 'Hemoglobin State + Hematological State + Toxicity Grade'"
                    )
                    
                    # Edit treatment
                    new_treatment = st.text_area(
                        "Treatment Protocol", 
                        value=treatment, 
                        height=100,
                        key=f"treatment_text_{selected_gender}_{i}",
                        help="Use bullet points (•) for multiple instructions"
                    )
                    
                    updated_rules[new_condition] = new_treatment
                
                with col2:
                    if st.button("🗑️ Delete", key=f"treatment_del_btn_{selected_gender}_{i}", type="secondary"):
                        st.session_state[del_key].add(i)
                        st.rerun()
    
    # Add new rule section
    st.markdown("**Add New Treatment Rule:**")
    col1, col2, col3 = st.columns([3, 3, 1])
    
    with col1:
        new_condition = st.text_input(
            "New Condition", 
            placeholder="e.g., Severe Anemia + Pancytopenia + GRADE I",
            key=f"new_treatment_cond_{selected_gender}"
        )
    
    with col2:
        new_treatment = st.text_area(
            "New Treatment Protocol",
            placeholder="• Measure BP once a week\n• Give medication...",
            height=100,
            key=f"new_treatment_text_{selected_gender}"
        )
    
    with col3:
        if st.button("➕ Add Rule", key=f"add_treatment_{selected_gender}"):
            if new_condition and new_treatment:
                kb_data["treatments"][selected_gender][new_condition] = new_treatment
                save_kb(kb_data)
                st.success("Rule added!")
                st.rerun()
            else:
                st.warning("Please fill both condition and treatment fields.")
    
    # Update button
    if st.button(f"💾 Update All {selected_gender.title()} Rules", key=f"update_treatments_{selected_gender}", type="primary"):
        kb_data["treatments"][selected_gender] = updated_rules
        save_kb(kb_data)
        # Clear delete tracking
        st.session_state[del_key] = set()
        st.success(f"Treatment rules for {selected_gender} updated successfully!")
        st.rerun()

def render_validity_periods_editor(kb_data):
    """Render the editor for validity periods with full CRUD."""
    st.markdown("### Validity Periods Editor")
    validity_periods = kb_data.get("validity_periods", {})
    
    # Add new validity period
    st.markdown("**Add New Validity Period:**")
    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
    
    with col1:
        new_code = st.text_input("Code", placeholder="e.g., 30313-1", key="new_validity_code")
    
    with col2:
        new_name = st.text_input("Name", placeholder="e.g., Hemoglobin", key="new_validity_name")
    
    with col3:
        new_before_days = st.number_input("Days Before Good", min_value=0, value=7, step=1, key="new_before_days")
    
    with col4:
        new_after_days = st.number_input("Days After Good", min_value=0, value=7, step=1, key="new_after_days")
    
    with col5:
        if st.button("➕ Add", key="add_validity_period"):
            if new_code and new_name:
                if new_code in validity_periods:
                    st.warning("Code already exists!")
                else:
                    validity_periods[new_code] = {
                        "name": new_name,
                        "before_good": f"{int(new_before_days)} days",
                        "after_good": f"{int(new_after_days)} days"
                    }
                    save_kb(kb_data)
                    st.success(f"Validity period for {new_name} added!")
                    st.rerun()
            else:
                st.warning("Please fill all fields.")
    
    # Edit existing validity periods
    st.markdown("**Current Validity Periods:**")
    
    if not validity_periods:
        st.info("No validity periods defined.")
        return
    
    # Track deletions
    del_key = "validity_periods_del"
    if del_key not in st.session_state:
        st.session_state[del_key] = set()
    
    updated_periods = {}
    
    for i, (code, period_data) in enumerate(validity_periods.items()):
        if i not in st.session_state[del_key]:
            with st.expander(f"{period_data.get('name', 'Unknown')} ({code})"):
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
                
                with col1:
                    st.text_input(
                        "Code", 
                        value=code, 
                        key=f"validity_code_{i}",
                        disabled=True,
                        help="Code cannot be changed to maintain data integrity"
                    )
                
                with col2:
                    updated_name = st.text_input(
                        "Name", 
                        value=period_data.get("name", ""), 
                        key=f"validity_name_{i}"
                    )
                
                with col3:
                    before_str = period_data.get("before_good", "0 days")
                    try:
                        before_days_int = int(str(before_str).split(' ')[0])
                    except:
                        before_days_int = 0
                    updated_before_days = st.number_input("Days Before Good", min_value=0, value=before_days_int, step=1, key=f"validity_before_{i}")
                
                with col4:
                    after_str = period_data.get("after_good", "0 days")
                    try:
                        after_days_int = int(str(after_str).split(' ')[0])
                    except:
                        after_days_int = 0
                    updated_after_days = st.number_input("Days After Good", min_value=0, value=after_days_int, step=1, key=f"validity_after_{i}")
                
                with col5:
                    if st.button("🗑️", key=f"validity_del_{i}", type="secondary"):
                        st.session_state[del_key].add(i)
                        st.rerun()
                
                # Store updated data
                updated_periods[code] = {
                    "name": updated_name,
                    "before_good": f"{int(updated_before_days)} days",
                    "after_good": f"{int(updated_after_days)} days"
                }
    
    # Update button
    if st.button("💾 Update Validity Periods", key="update_validity_periods", type="primary"):
        kb_data["validity_periods"] = updated_periods
        save_kb(kb_data)
        # Clear delete tracking
        st.session_state[del_key] = set()
        st.success("Validity periods updated successfully!")
        st.rerun()

def render_file_management(kb_data):
    """Render file management section for import/export."""
    st.markdown("### Knowledge Base File Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📥 Import Knowledge Base**")
        uploaded_file = st.file_uploader(
            "Upload KB JSON file", 
            type=['json'],
            key="kb_upload",
            help="Upload a knowledge base JSON file to replace current KB"
        )
        
        if uploaded_file is not None:
            try:
                uploaded_kb = json.loads(uploaded_file.read().decode('utf-8'))
                
                # Preview the uploaded KB
                st.markdown("**Preview of uploaded KB:**")
                st.json(uploaded_kb, expanded=False)
                
                if st.button("🔄 Replace Current KB", key="replace_kb", type="primary"):
                    save_kb(uploaded_kb)
                    st.success("Knowledge base replaced successfully!")
                    st.rerun()
                    
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON file: {e}")
            except Exception as e:
                st.error(f"Error reading file: {e}")
    
    with col2:
        st.markdown("**📤 Export Knowledge Base**")
        
        # Toggle to show full KB preview
        if st.checkbox("👁️ Preview Current KB JSON", key="show_kb_json"):
            st.json(kb_data, expanded=False)
        else:
            # Compact summary view
            st.markdown("**Current KB structure:**")
            kb_summary = {
                "classification_tables": len(kb_data.get("classification_tables", {})),
                "treatments": {gender: len(rules) for gender, rules in kb_data.get("treatments", {}).items()},
                "validity_periods": len(kb_data.get("validity_periods", {}))
            }
            st.json(kb_summary, expanded=True)
        
        # Download button
        kb_json = json.dumps(kb_data, indent=2)
        st.download_button(
            label="💾 Download KB as JSON",
            data=kb_json,
            file_name="knowledge_base.json",
            mime="application/json",
            key="download_kb"
        )

def render_kb_overview(kb_data):
    """Render overview of the entire knowledge base."""
    st.markdown("### Knowledge Base Overview")
    
    # Classification Tables Summary
    st.markdown("#### 📊 Classification Tables")
    tables = kb_data.get("classification_tables", {})
    if tables:
        for table_name, table_data in tables.items():
            with st.expander(f"{table_name} ({table_data.get('type', 'Unknown')})"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Inputs:** {', '.join(table_data.get('inputs', []))}")
                    st.write(f"**Output:** {table_data.get('output', 'None')}")
                with col2:
                    if table_data.get('type') == '1:1':
                        total_ranges = sum(len(gender_rules.get('ranges', [])) for gender_rules in table_data.get('rules', {}).values())
                        st.write(f"**Total Ranges:** {total_ranges}")
                    elif table_data.get('type') == '2:1_AND':
                        total_cells = sum(len(gender_rules.get('matrix', [])) * len(gender_rules.get('matrix', [[]])[0] if gender_rules.get('matrix') else []) for gender_rules in table_data.get('rules', {}).values())
                        st.write(f"**Matrix Cells:** {total_cells}")
                    elif table_data.get('type') == '4:1_MAXIMAL_OR':
                        total_rules = sum(len(param_rules) for param_rules in table_data.get('rules', {}).values())
                        st.write(f"**Total Rules:** {total_rules}")
    else:
        st.info("No classification tables defined.")
    
    # Treatments Summary
    st.markdown("#### 🏥 Treatment Rules")
    treatments = kb_data.get("treatments", {})
    if treatments:
        for gender, rules in treatments.items():
            st.write(f"**{gender.title()}:** {len(rules)} treatment rules")
    else:
        st.info("No treatment rules defined.")
    
    # Validity Periods Summary
    st.markdown("#### ⏰ Validity Periods")
    periods = kb_data.get("validity_periods", {})
    if periods:
        st.write(f"**Total observations:** {len(periods)}")
        for code, period in periods.items():
            st.write(f"• {period.get('name', 'Unknown')} ({code}): {period.get('before_good', 'N/A')} / {period.get('after_good', 'N/A')}")
    else:
        st.info("No validity periods defined.")

def render_kb_editor():
    """Main function to render the complete Knowledge Base Editor."""
    st.markdown("""
    <style>
    .kb-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 1rem;
    }
    .section-header {
        background-color: #f0f2f6;
        padding: 0.5rem;
        border-radius: 5px;
        border-left: 4px solid #667eea;
        margin: 1rem 0;
    }
    </style>
    
    <div class="kb-header">
        <h1>🧠 Knowledge Base Editor</h1>
        <p>Comprehensive editor for medical classification tables, treatment rules, and validity periods.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Load knowledge base
    kb_data = load_kb()
    if not kb_data:
        st.error("❌ Failed to load knowledge base. Please check the file.")
        return
    
    # Create tabs for different sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Classification Tables", 
        "🏥 Treatment Rules", 
        "⏰ Validity Periods",
        "📁 File Management",
        "📋 Overview"
    ])
    
    with tab1:
        render_classification_tables_editor(kb_data)
    
    with tab2:
        render_treatments_editor(kb_data)
    
    with tab3:
        render_validity_periods_editor(kb_data)
    
    with tab4:
        render_file_management(kb_data)
    
    with tab5:
        render_kb_overview(kb_data)
    
    # Status information
    st.markdown("---")
    st.markdown("""
    ### 💡 Usage Tips:
    - **Classification Tables**: Define medical parameter classifications (1:1, 2:1 matrix, 4:1 maximal OR)
    - **Treatment Rules**: Set treatment protocols based on medical states and toxicity grades
    - **Validity Periods**: Configure how long test results remain valid
    - **File Management**: Import/export complete knowledge bases
    - **Overview**: Get a summary of your entire knowledge base
    
    All changes are saved automatically to `knowledge_base.json`.
    """) 