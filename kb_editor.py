import re
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


def get_hematological_state(hgb: float, wbc: float, gender: str):
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

    return matrix[wbc_idx][hgb_idx]


##

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
                #rules[(gender, hemo, hema, grade)] = treatment.replace("•", "•")  # decode bullet if needed
                cleaned = treatment.encode("utf-8", "ignore").decode("utf-8")
                cleaned = re.sub(r'[\u05d2\u20ac\u00a2]+', "•", cleaned)  # fix bad bullet encoding
                rules[(gender, hemo, hema, grade)] = cleaned
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
    """Save knowledge base to JSON file and auto-export ontology files."""
    try:
        with open(KB_PATH, 'w') as f:
            json.dump(kb_data, f, indent=2)
        
        # Auto-export ontology files
        export_ontology_files(kb_data)
        
        return True
    except Exception as e:
        st.error(f"Error saving knowledge base: {e}")
        return False

def export_ontology_files(kb_data):
    """Export knowledge base to PlantUML ontology files."""
    
    # Get all classification tables to dynamically generate schema
    classification_tables = kb_data.get("classification_tables", {})
    
    # Generate schema file dynamically
    schema_content = """@startuml ontology_schema
hide circle
skinparam classAttributeIconSize 0
skinparam shadowing false
skinparam classFontStyle bold

' Core classes
class Patient {
  +hasGender: String
}

abstract class Observation {
  numericValue: Decimal [0..1]
  symbolicValue: String [0..1]
}

' Dynamic observation classes based on KB tables
"""
    
    # Add observation classes for each table
    for table_name in classification_tables.keys():
        if table_name == "hemoglobin_state":
            schema_content += "class HemoglobinObservation\n"
        elif table_name == "hematological_state":
            schema_content += "class WBCObservation\n"
        elif table_name == "systemic_toxicity":
            schema_content += "class FeverObservation\n"
            schema_content += "class ChillsObservation\n"
            schema_content += "class SkinLookObservation\n"
            schema_content += "class AllergenicObservation as \"AllergicStateObservation\"\n"
            schema_content += "class TherapyStatusObservation\n"
        else:
            # For new tables like "sugar-level", create generic observation class
            observation_name = table_name.replace("_", "").title() + "Observation"
            schema_content += f"class {observation_name}\n"
    
    # Add inheritance relationships
    schema_content += "\n' Observation inheritance\n"
    for table_name in classification_tables.keys():
        if table_name == "hemoglobin_state":
            schema_content += "HemoglobinObservation -up-|> Observation\n"
        elif table_name == "hematological_state":
            schema_content += "WBCObservation -up-|> Observation\n"
        elif table_name == "systemic_toxicity":
            schema_content += "FeverObservation -up-|> Observation\n"
            schema_content += "ChillsObservation -up-|> Observation\n"
            schema_content += "SkinLookObservation -up-|> Observation\n"
            schema_content += "\"AllergicStateObservation\" -up-|> Observation\n"
            schema_content += "TherapyStatusObservation -up-|> Observation\n"
        else:
            # For new tables
            observation_name = table_name.replace("_", "").title() + "Observation"
            schema_content += f"{observation_name} -up-|> Observation\n"
    
    # Add state classes
    schema_content += """
class State
class HemoglobinState
class HematologicalState
class SystemicToxicityGrade {
  aggregation: "MAX"  ' policy hint
}
"""
    
    # Add state classes for new tables
    for table_name in classification_tables.keys():
        if table_name not in ["hemoglobin_state", "hematological_state", "systemic_toxicity"]:
            state_name = table_name.replace("_", "").title() + "State"
            schema_content += f"class {state_name}\n"
    
    # Add state inheritance
    schema_content += "\n' State inheritance\n"
    schema_content += "HemoglobinState -up-|> State\n"
    schema_content += "HematologicalState -up-|> State\n"
    schema_content += "SystemicToxicityGrade -up-|> State\n"
    
    for table_name in classification_tables.keys():
        if table_name not in ["hemoglobin_state", "hematological_state", "systemic_toxicity"]:
            state_name = table_name.replace("_", "").title() + "State"
            schema_content += f"{state_name} -up-|> State\n"
    
    # Add rule classes
    schema_content += """
class RangeSpec {
  label: String
  minVal: Decimal
  maxVal: Decimal
}

class Partition {
  label: String
  minVal: Decimal [0..1]
  maxVal: Decimal [0..1]
}

class MatrixCell {
  label: String
}

class SymptomToGradeRule {
  label: String [0..1]
  minVal: Decimal [0..1]
  maxVal: Decimal [0..1]
}

' Associations
Patient "1" -- "0..*" Observation : hasObservation
Patient "1" -- "0..*" State : hasState

RangeSpec "1" --> "1" State : mapsToState
Partition "1" --> "1" Observation : partitionOf
MatrixCell "1" --> "1" Partition : hgbPartition
MatrixCell "1" --> "1" Partition : wbcPartition
MatrixCell "1" --> "1" State : mapsTo
SymptomToGradeRule "0..*" --> "1" TherapyStatusObservation : appliesIfTherapy
SymptomToGradeRule "1" --> "1" Observation : symptomObservation
SymptomToGradeRule "1" --> "1" SystemicToxicityGrade : yieldsGrade

note right of RangeSpec
  Used for value thresholds per gender.
  Logic (informal):
    if hasGender in {male|female}
    and numericValue in [minVal, maxVal)
    then assign mapsToState
end note

note right of MatrixCell
  Represents one cell in decision matrices (per gender).
  Given patient's parameter partitions, the cell's
  mapped State is assigned.
end note

note right of SymptomToGradeRule
  Gated by therapy (e.g., CCTG522).
  For numeric values, use minVal/maxVal intervals.
  For symbolic values, use 'label' to hold the symbolic value.
end note
@enduml"""

    # Generate instances file
    instances_content = "@startuml ontology_instances\nhide circle\nskinparam shadowing false\nskinparam objectFontStyle bold\n\n"
    
    # Process all classification tables dynamically
    for table_name, table_data in classification_tables.items():
        table_type = table_data.get("type", "")
        
        if table_name == "hemoglobin_state":
            # Handle hemoglobin ranges (1:1 type)
            for gender in ["female", "male"]:
                if gender in table_data.get("rules", {}):
                    instances_content += f"' =====================\n' Hemoglobin ranges ({gender})\n' =====================\n"
                    rules = table_data["rules"][gender]["ranges"]
                    for i, rule in enumerate(rules):
                        if rule.get("state"):  # Skip empty states
                            instances_content += f"object HB_{gender}_{i} <<RangeSpec>> {{\n"
                            instances_content += f"  label = \"Hb {gender} range {i}\"\n"
                            instances_content += f"  minVal = {rule['min']}\n"
                            instances_content += f"  maxVal = {rule['max']}\n"
                            instances_content += "}\n"
                            
                            # Create state object if not already defined
                            state_name = rule["state"].replace(" ", "_")
                            instances_content += f"object {state_name} <<HemoglobinState>>\n"
                            instances_content += f"HB_{gender}_{i} --> {state_name} : mapsToState\n\n"
        
        elif table_name == "hematological_state":
            # Handle hematological matrix (2:1_AND type)
            for gender in ["female", "male"]:
                if gender in table_data.get("rules", {}):
                    instances_content += f"' =====================\n' Hematological matrix ({gender})\n' =====================\n"
                    rules = table_data["rules"][gender]
                    
                    # Add partitions
                    for i, hgb_part in enumerate(rules.get("hgb_partitions", [])):
                        instances_content += f"object HGBpart_{gender}_{i} <<Partition>> {{ label = \"Hb {gender} {hgb_part}\"; "
                        if "+" in hgb_part:
                            min_val = hgb_part.replace("+", "")
                            instances_content += f"minVal={min_val} }}\n"
                        else:
                            min_val, max_val = hgb_part.split("-")
                            instances_content += f"minVal={min_val}; maxVal={max_val} }}\n"
                    
                    for i, wbc_part in enumerate(rules.get("wbc_partitions", [])):
                        instances_content += f"object WBCpart_{gender}_{i} <<Partition>> {{ label = \"WBC {gender} {wbc_part}\"; "
                        if "+" in wbc_part:
                            min_val = wbc_part.replace("+", "")
                            instances_content += f"minVal={min_val} }}\n"
                        else:
                            min_val, max_val = wbc_part.split("-")
                            instances_content += f"minVal={min_val}; maxVal={max_val} }}\n"
                    
                    # Add matrix cells
                    matrix = rules.get("matrix", [])
                    for i, row in enumerate(matrix):
                        for j, state in enumerate(row):
                            if state:  # Skip empty states
                                state_name = state.replace(" ", "_")
                                instances_content += f"object MATRIX_{gender}_{i}_{j} <<MatrixCell>> {{ label = \"Cell {gender} Hb{i}xWBC{j}\" }}\n"
                                instances_content += f"MATRIX_{gender}_{i}_{j} --> HGBpart_{gender}_{i} : hgbPartition\n"
                                instances_content += f"MATRIX_{gender}_{i}_{j} --> WBCpart_{gender}_{j} : wbcPartition\n"
                                instances_content += f"MATRIX_{gender}_{i}_{j} --> {state_name} : mapsTo\n\n"
        
        elif table_name == "systemic_toxicity":
            # Handle systemic toxicity rules (4:1_MAXIMAL_OR type)
            instances_content += "' =====================\n' Systemic toxicity rules (Therapy=CCTG522)\n' =====================\n"
            instances_content += "object CCTG522 <<TherapyStatusObservation>> { label=\"CCTG522\" }\n\n"
            
            # Add fever rules
            fever_rules = table_data.get("rules", {}).get("Fever", [])
            for i, rule in enumerate(fever_rules):
                instances_content += f"object FeverRule_{i} <<SymptomToGradeRule>> {{ minVal={rule.get('min', 0)}; maxVal={rule.get('max', 999)} }}\n"
                instances_content += f"FeverRule_{i} --> CCTG522 : appliesIfTherapy\n"
                instances_content += f"FeverRule_{i} --> GRADE_{rule.get('grade', 'I')} : yieldsGrade\n\n"
            
            # Add chills rules
            chills_rules = table_data.get("rules", {}).get("Chills", [])
            for i, rule in enumerate(chills_rules):
                instances_content += f"object ChillsObservationRule_{i} <<SymptomToGradeRule>> {{ label=\"{rule.get('value', 'None')}\" }}\n"
                instances_content += f"ChillsObservationRule_{i} --> CCTG522 : appliesIfTherapy\n"
                instances_content += f"ChillsObservationRule_{i} --> GRADE_{rule.get('grade', 'I')} : yieldsGrade\n\n"
            
            # Add skin look rules
            skin_rules = table_data.get("rules", {}).get("Skin-look", [])
            for i, rule in enumerate(skin_rules):
                instances_content += f"object SkinLookObservationRule_{i} <<SymptomToGradeRule>> {{ label=\"{rule.get('value', 'Erythema')}\" }}\n"
                instances_content += f"SkinLookObservationRule_{i} --> CCTG522 : appliesIfTherapy\n"
                instances_content += f"SkinLookObservationRule_{i} --> GRADE_{rule.get('grade', 'I')} : yieldsGrade\n\n"
            
            # Add allergic state rules
            allergic_rules = table_data.get("rules", {}).get("Allergic-state", [])
            for i, rule in enumerate(allergic_rules):
                instances_content += f"object AllergicStateObservationRule_{i} <<SymptomToGradeRule>> {{ label=\"{rule.get('value', 'Edema')}\" }}\n"
                instances_content += f"AllergicStateObservationRule_{i} --> CCTG522 : appliesIfTherapy\n"
                instances_content += f"AllergicStateObservationRule_{i} --> GRADE_{rule.get('grade', 'I')} : yieldsGrade\n\n"
        
        else:
            # Handle new tables (like "sugar-level") - assume 1:1 type by default
            table_display_name = table_name.replace("_", " ").title()
            instances_content += f"' =====================\n' {table_display_name} ranges\n' =====================\n"
            
            for gender in ["female", "male"]:
                if gender in table_data.get("rules", {}):
                    instances_content += f"' {gender.title()} ranges:\n"
                    rules = table_data["rules"][gender]["ranges"]
                    for i, rule in enumerate(rules):
                        if rule.get("state"):  # Skip empty states
                            # Create range spec object
                            range_prefix = table_name.upper().replace("_", "")
                            instances_content += f"object {range_prefix}_{gender}_{i} <<RangeSpec>> {{\n"
                            instances_content += f"  label = \"{table_display_name} {gender} range {i}\"\n"
                            instances_content += f"  minVal = {rule['min']}\n"
                            instances_content += f"  maxVal = {rule['max']}\n"
                            instances_content += "}\n"
                            
                            # Create state object
                            state_name = rule["state"].replace(" ", "_")
                            state_class = table_name.replace("_", "").title() + "State"
                            instances_content += f"object {state_name} <<{state_class}>>\n"
                            instances_content += f"{range_prefix}_{gender}_{i} --> {state_name} : mapsToState\n\n"
    
    instances_content += "@enduml"
    
    # Write files
    try:
        with open("ontology_schema.puml", "w", encoding="utf-8") as f:
            f.write(schema_content)
        
        with open("ontology_instances.puml", "w", encoding="utf-8") as f:
            f.write(instances_content)
        
        return True
    except Exception as e:
        st.error(f"Error exporting ontology files: {e}")
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
    
    col1, col2, col3 = st.columns(3)
    
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
    
    with col3:
        st.markdown("**🔗 Ontology Synchronization**")
        st.info("Keep your ontology files in sync with your knowledge base.")
        
        # Manual sync button
        if st.button("🔄 Sync Ontology Files", key="sync_ontology"):
            if export_ontology_files(kb_data):
                st.success("✅ Ontology files synchronized!")
            else:
                st.error("❌ Sync failed")
        
        # Show current ontology files status
        st.markdown("**📄 Current Ontology Files:**")
        if Path("ontology_schema.puml").exists():
            st.success("✅ `ontology_schema.puml` exists")
        else:
            st.warning("⚠️ `ontology_schema.puml` missing")
        
        if Path("ontology_instances.puml").exists():
            st.success("✅ `ontology_instances.puml` exists")
        else:
            st.warning("⚠️ `ontology_instances.puml` missing")
        
        # Download ontology files
        if Path("ontology_schema.puml").exists() and Path("ontology_instances.puml").exists():
            st.markdown("**📥 Download Ontology Files:**")
            
            with open("ontology_schema.puml", "r", encoding="utf-8") as f:
                schema_content = f.read()
            st.download_button(
                label="📄 Download Schema",
                data=schema_content,
                file_name="ontology_schema.puml",
                mime="text/plain",
                key="download_schema"
            )
            
            with open("ontology_instances.puml", "r", encoding="utf-8") as f:
                instances_content = f.read()
            st.download_button(
                label="📄 Download Instances",
                data=instances_content,
                file_name="ontology_instances.puml",
                mime="text/plain",
                key="download_instances"
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

def render_ontology_viewer(kb_data):
    """Render the ontology viewer to display PlantUML files in an organized way."""
    st.markdown("### 🔗 Ontology Viewer")
    st.info("View and manage your ontology files. These files are automatically synchronized with your knowledge base.")
    
    # Check if ontology files exist
    schema_exists = Path("ontology_schema.puml").exists()
    instances_exists = Path("ontology_instances.puml").exists()
    
    if not schema_exists or not instances_exists:
        st.warning("⚠️ Some ontology files are missing. Click the button below to generate them.")
        if st.button("🔄 Generate Ontology Files", key="generate_ontology_files"):
            if export_ontology_files(kb_data):
                st.success("✅ Ontology files generated successfully!")
                st.rerun()
            else:
                st.error("❌ Failed to generate ontology files")
        return
    
    # Create tabs for different ontology components
    schema_tab, instances_tab, summary_tab = st.tabs([
        "🏗️ Schema Structure", 
        "📊 Data Instances", 
        "📋 Summary"
    ])
    
    with schema_tab:
        st.markdown("#### 🏗️ Ontology Schema Structure")
        st.markdown("This file defines the conceptual structure and relationships of your clinical decision support system.")
        
        with open("ontology_schema.puml", "r", encoding="utf-8") as f:
            schema_content = f.read()
        
        # Display schema with syntax highlighting
        st.code(schema_content, language="plantuml")
        
        # Schema components breakdown - Dynamic based on KB tables
        st.markdown("**🔍 Schema Components:**")
        col1, col2 = st.columns(2)
        
        # Get all classification tables to build dynamic lists
        classification_tables = kb_data.get("classification_tables", {})
        
        # Debug: Show what tables are found
        st.info(f"📊 Found {len(classification_tables)} classification tables: {list(classification_tables.keys())}")
        
        # Build observation types list
        observation_types = []
        for table_name in classification_tables.keys():
            if table_name == "hemoglobin_state":
                observation_types.append("`HemoglobinObservation`")
            elif table_name == "hematological_state":
                observation_types.append("`WBCObservation`")
            elif table_name == "systemic_toxicity":
                observation_types.extend([
                    "`FeverObservation`",
                    "`ChillsObservation`",
                    "`SkinLookObservation`",
                    "`AllergicStateObservation`",
                    "`TherapyStatusObservation`"
                ])
            else:
                # For new tables like "sugar-level"
                observation_name = table_name.replace("_", "").title() + "Observation"
                observation_types.append(f"`{observation_name}`")
        
        # Build state types list
        state_types = []
        for table_name in classification_tables.keys():
            if table_name == "hemoglobin_state":
                state_types.append("`HemoglobinState`")
            elif table_name == "hematological_state":
                state_types.append("`HematologicalState`")
            elif table_name == "systemic_toxicity":
                state_types.append("`SystemicToxicityGrade`")
            else:
                # For new tables like "sugar-level"
                state_name = table_name.replace("_", "").title() + "State"
                state_types.append(f"`{state_name}`")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_state_types = []
        for state_type in state_types:
            if state_type not in seen:
                seen.add(state_type)
                unique_state_types.append(state_type)
        state_types = unique_state_types
        
        with col1:
            st.markdown("**Core Classes:**")
            st.markdown("- `Patient` - Patient information")
            st.markdown("- `Observation` - Abstract base for all observations")
            st.markdown("- `State` - Abstract base for all states")
            st.markdown("")
            st.markdown("**Observation Types:**")
            for obs_type in observation_types:
                st.markdown(f"- {obs_type}")
        
        with col2:
            st.markdown("**State Types:**")
            for state_type in state_types:
                st.markdown(f"- {state_type}")
            st.markdown("")
            st.markdown("**Rule Classes:**")
            st.markdown("- `RangeSpec` - Value ranges with thresholds")
            st.markdown("- `Partition` - Value partitions")
            st.markdown("- `MatrixCell` - Decision matrix cells")
            st.markdown("- `SymptomToGradeRule` - Symptom to grade mapping")
        
        # Download button
        st.download_button(
            label="📄 Download Schema File",
            data=schema_content,
            file_name="ontology_schema.puml",
            mime="text/plain",
            key="download_schema_viewer"
        )
    
    with instances_tab:
        st.markdown("#### 📊 Ontology Data Instances")
        st.markdown("This file contains the actual data instances that populate your ontology with clinical knowledge.")
        
        with open("ontology_instances.puml", "r", encoding="utf-8") as f:
            instances_content = f.read()
        
        # Display instances with syntax highlighting
        st.code(instances_content, language="plantuml")
        
        # Instances breakdown
        st.markdown("**🔍 Instance Components:**")
        
        # Extract and display all classification tables
        classification_tables = kb_data.get("classification_tables", {})
        
        for table_name, table_data in classification_tables.items():
            table_type = table_data.get("type", "")
            table_display_name = table_name.replace("_", " ").title()
            
            if table_name == "hemoglobin_state":
                st.markdown("**🩸 Hemoglobin Ranges:**")
                for gender in ["female", "male"]:
                    if gender in table_data.get("rules", {}):
                        st.markdown(f"**{gender.title()}:**")
                        rules = table_data["rules"][gender]["ranges"]
                        for i, rule in enumerate(rules):
                            if rule.get("state"):
                                st.markdown(f"  - Range {i+1}: {rule['min']} - {rule['max']} → {rule['state']}")
            
            elif table_name == "hematological_state":
                st.markdown("**🩺 Hematological Matrix:**")
                for gender in ["female", "male"]:
                    if gender in table_data.get("rules", {}):
                        st.markdown(f"**{gender.title()}:**")
                        rules = table_data["rules"][gender]
                        hgb_parts = rules.get("hgb_partitions", [])
                        wbc_parts = rules.get("wbc_partitions", [])
                        matrix = rules.get("matrix", [])
                        
                        if matrix:
                            # Create a nice table display
                            matrix_data = []
                            for i, row in enumerate(matrix):
                                for j, cell in enumerate(row):
                                    if cell:
                                        matrix_data.append({
                                            "Hb Partition": hgb_parts[i] if i < len(hgb_parts) else "N/A",
                                            "WBC Partition": wbc_parts[j] if j < len(wbc_parts) else "N/A",
                                            "State": cell
                                        })
                            
                            if matrix_data:
                                st.dataframe(matrix_data, use_container_width=True)
            
            elif table_name == "systemic_toxicity":
                st.markdown("**🌡️ Systemic Toxicity Rules (CCTG522):**")
                rules = table_data.get("rules", {})
                
                for symptom, symptom_rules in rules.items():
                    st.markdown(f"**{symptom}:**")
                    for i, rule in enumerate(symptom_rules):
                        if "range" in rule:
                            st.markdown(f"  - Range {i+1}: {rule['range'][0]} - {rule['range'][1]} → {rule.get('grade', 'N/A')}")
                        elif "value" in rule:
                            st.markdown(f"  - Value {i+1}: {rule['value']} → {rule.get('grade', 'N/A')}")
            
            else:
                # Handle new tables (like "sugar-level")
                st.markdown(f"**📊 {table_display_name} ({table_type}):**")
                for gender in ["female", "male"]:
                    if gender in table_data.get("rules", {}):
                        st.markdown(f"**{gender.title()}:**")
                        if table_type == "1:1":
                            rules = table_data["rules"][gender]["ranges"]
                            for i, rule in enumerate(rules):
                                if rule.get("state"):
                                    st.markdown(f"  - Range {i+1}: {rule['min']} - {rule['max']} → {rule['state']}")
                        elif table_type == "2:1_AND":
                            rules = table_data["rules"][gender]
                            # Handle matrix tables
                            st.markdown("  *Matrix-based classification*")
                        elif table_type == "4:1_MAXIMAL_OR":
                            rules = table_data["rules"][gender]
                            # Handle OR-based tables
                            st.markdown("  *OR-based classification*")
        
        # Download button
        st.download_button(
            label="📄 Download Instances File",
            data=instances_content,
            file_name="ontology_instances.puml",
            mime="text/plain",
            key="download_instances_viewer"
        )
    
    with summary_tab:
        st.markdown("#### 📋 Ontology Summary")
        
        # File status
        st.markdown("**📄 File Status:**")
        col1, col2 = st.columns(2)
        
        with col1:
            if schema_exists:
                st.success("✅ Schema file exists")
                schema_size = Path("ontology_schema.puml").stat().st_size
                st.info(f"Size: {schema_size} bytes")
            else:
                st.error("❌ Schema file missing")
        
        with col2:
            if instances_exists:
                st.success("✅ Instances file exists")
                instances_size = Path("ontology_instances.puml").stat().st_size
                st.info(f"Size: {instances_size} bytes")
            else:
                st.error("❌ Instances file missing")
        
        # Statistics
        st.markdown("**📊 Ontology Statistics:**")
        
        # Count hemoglobin ranges
        hgb_ranges = 0
        hgb_table = kb_data.get("classification_tables", {}).get("hemoglobin_state", {})
        if hgb_table:
            for gender in ["female", "male"]:
                if gender in hgb_table.get("rules", {}):
                    hgb_ranges += len([r for r in hgb_table["rules"][gender]["ranges"] if r.get("state")])
        
        # Count matrix cells
        matrix_cells = 0
        hema_table = kb_data.get("classification_tables", {}).get("hematological_state", {})
        if hema_table:
            for gender in ["female", "male"]:
                if gender in hema_table.get("rules", {}):
                    matrix = hema_table["rules"][gender].get("matrix", [])
                    matrix_cells += sum(len([cell for cell in row if cell]) for row in matrix)
        
        # Count toxicity rules
        toxicity_rules = 0
        sys_tox_table = kb_data.get("classification_tables", {}).get("systemic_toxicity", {})
        if sys_tox_table:
            rules = sys_tox_table.get("rules", {})
            toxicity_rules = sum(len(symptom_rules) for symptom_rules in rules.values())
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Hemoglobin Ranges", hgb_ranges)
        with col2:
            st.metric("Matrix Cells", matrix_cells)
        with col3:
            st.metric("Toxicity Rules", toxicity_rules)
        
        # Last modified
        if schema_exists and instances_exists:
            schema_time = Path("ontology_schema.puml").stat().st_mtime
            instances_time = Path("ontology_instances.puml").stat().st_mtime
            last_modified = max(schema_time, instances_time)
            
            from datetime import datetime
            st.markdown(f"**🕒 Last Modified:** {datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Actions
        st.markdown("**⚡ Actions:**")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Regenerate Ontology Files", key="regenerate_ontology"):
                if export_ontology_files(kb_data):
                    st.success("✅ Ontology files regenerated!")
                    st.rerun()
                else:
                    st.error("❌ Failed to regenerate")
        
        with col2:
            if st.button("📥 Download Both Files", key="download_both_ontology"):
                if schema_exists and instances_exists:
                    # Create a zip-like experience by offering both files
                    st.info("Use the download buttons in the individual tabs above to download each file separately.")
                else:
                    st.warning("Files not available for download")

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
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Classification Tables", 
        "🏥 Treatment Rules", 
        "⏰ Validity Periods",
        "📁 File Management",
        "📋 Overview",
        "🔗 Ontology Viewer"
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
    
    with tab6:
        render_ontology_viewer(kb_data)
    
    # Status information
    st.markdown("---")
    st.markdown("""
    ### 💡 Usage Tips:
    - **Classification Tables**: Define medical parameter classifications (1:1, 2:1 matrix, 4:1 maximal OR)
    - **Treatment Rules**: Set treatment protocols based on medical states and toxicity grades
    - **Validity Periods**: Configure how long test results remain valid
    - **File Management**: Import/export complete knowledge bases and sync ontology files
    - **Overview**: Get a summary of your entire knowledge base
    - **Ontology Viewer**: View and manage your PlantUML ontology files with organized components
    
    All changes are saved automatically to `knowledge_base.json` and ontology files are auto-synchronized.
    """) 